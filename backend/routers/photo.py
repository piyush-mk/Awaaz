"""Photo APIs.

  POST /api/photo/parse                  legacy shelf photo -> ParsedItem[] (response shape unchanged)
  POST /api/photo/parchi                 handwritten list -> counter CartLine[] + unmatched (F12)
  POST /api/photo/shelf-audit            one or many frames (multipart `images`) -> expected vs counted
                                         per product, variance at cost (the "losses" view);
                                         stored as PendingAction(kind='shelf_audit')
  POST /api/photo/shelf-audit/{id}/confirm   write audit StockMove adjustments (optional count edits)
  POST /api/photo/shelf-audit/{id}/cancel

Chain is Sarvam gemma4 -> OpenRouter -> fixture (see services/vision.py).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import PendingAction, Product, StockMove
from schemas import CartLine, ParsedItem, VoiceParseResponse
from services import catalog, events, parchi as parchi_svc, stock_ops, vision
from services.clock import now_local
from services.price_guard import inr
from services.types import ProviderError, Result

router = APIRouter()

MAX_FRAMES = 40
FRAME_CONCURRENCY = 3


async def _read_image(image: UploadFile) -> tuple[bytes, str]:
    data = await image.read()
    if not data:
        raise HTTPException(400, "Empty image upload")
    return data, image.content_type or "image/jpeg"


# ---------------------------------------------------------------------------
# legacy shelf photo -> restock items
# ---------------------------------------------------------------------------


@router.post("/parse", response_model=VoiceParseResponse)
async def parse_photo(image: UploadFile = File(...), db: Session = Depends(get_db)):
    """POST a shelf photo; feed the result into POST /api/inventory/restock."""
    data, mime = await _read_image(image)
    try:
        result = await vision.extract_json_from_image(data, mime, "shelf")
    except ProviderError as exc:
        raise HTTPException(502, f"Photo parse failed: {exc}") from exc
    index = catalog.load_index(db)
    merged: dict[int, ParsedItem] = {}
    extras: dict[str, ParsedItem] = {}
    for row in result.data:
        product, _ = index.find_in_phrase(row["name"])
        qty = float(row["quantity"])
        if product is None:
            key = catalog.normalize(row["name"])
            if key in extras:
                extras[key].quantity += qty
            else:
                extras[key] = ParsedItem(product_id=0, name=row["name"], name_hi="", quantity=qty,
                                         unit="unit", price=0.0, gst_rate=0.0)
        elif product.id in merged:
            merged[product.id].quantity += qty
        else:
            merged[product.id] = ParsedItem(
                product_id=product.id, name=product.name, name_hi=product.name_hi or "", quantity=qty,
                unit=product.unit or "", price=product.price, gst_rate=product.gst_rate or 0.0)
    names = ", ".join(r["name"] for r in result.data) or "none"
    return VoiceParseResponse(
        transcript=f"Detected: {names}" if result.source != "fixture" else "[Photo - Demo mode]",
        items=list(merged.values()) + list(extras.values()), demo_mode=result.source == "fixture",
        source=result.source, latency_ms=result.latency_ms)


# ---------------------------------------------------------------------------
# F12: parchi -> cart lines
# ---------------------------------------------------------------------------


class ParchiOut(BaseModel):
    lines: List[CartLine]
    unmatched: List[Dict[str, Any]]
    items_read: List[Dict[str, Any]]
    total: float
    message_hi: str
    source: str
    latency_ms: int
    demo_mode: bool


@router.post("/parchi", response_model=ParchiOut)
async def parse_parchi(image: UploadFile = File(...), db: Session = Depends(get_db)):
    """Handwritten shopping list -> cart lines (same CartLine shape as the counter) + items not in the catalog.
    The app pushes `lines` into the cart; `unmatched` can be offered as missed sales."""
    data, mime = await _read_image(image)
    try:
        result = await vision.extract_json_from_image(data, mime, "parchi")
    except ProviderError as exc:
        raise HTTPException(502, f"Parchi scan failed: {exc}") from exc
    lines, unmatched = parchi_svc.parse_rows(result.data, catalog.load_index(db))
    total = round(sum(ln.line_total for ln in lines), 2)
    msg = f"Parchi mein {len(lines)} item mile, kul {inr(total)}."
    if unmatched:
        msg += " " + ", ".join(u["name"] for u in unmatched[:3]) + " dukaan mein nahi hai."
    return ParchiOut(lines=lines, unmatched=unmatched, items_read=result.data, total=total, message_hi=msg,
                     source=result.source, latency_ms=result.latency_ms, demo_mode=result.source == "fixture")


# ---------------------------------------------------------------------------
# shelf audit
# ---------------------------------------------------------------------------


def aggregate_frames(frames: List[List[dict]], index: catalog.CatalogIndex) -> dict:
    """Merge per-frame shelf detections. Within one frame the same product is summed (several
    labels for one product); ACROSS frames the maximum wins, because a shelf walk shows the same
    items in overlapping frames and summing would double count.
    Returns {"counts": {product_id: n}, "unmatched": {display_name: n}, "per_frame": [...]}."""
    counts: Dict[int, float] = {}
    unmatched: Dict[str, List] = {}  # normalised -> [display, n]
    per_frame = []
    for i, rows in enumerate(frames):
        f_counts: Dict[int, float] = {}
        f_unmatched: Dict[str, List] = {}
        for row in rows:
            product, _ = index.find_in_phrase(row["name"])
            n = float(row["quantity"])
            if product is not None:
                f_counts[product.id] = f_counts.get(product.id, 0.0) + n
            else:
                slot = f_unmatched.setdefault(catalog.normalize(row["name"]), [row["name"], 0.0])
                slot[1] += n
        for pid, n in f_counts.items():
            counts[pid] = max(counts.get(pid, 0.0), n)
        for key, (display, n) in f_unmatched.items():
            slot = unmatched.setdefault(key, [display, 0.0])
            slot[1] = max(slot[1], n)
        per_frame.append({"index": i, "detected": {str(k): v for k, v in f_counts.items()},
                          "unmatched": {v[0]: v[1] for v in f_unmatched.values()}})
    return {"counts": counts, "unmatched": {v[0]: v[1] for v in unmatched.values()}, "per_frame": per_frame}


def _unit_cost(product: Product) -> float:
    return float(product.cost_price if product.cost_price is not None else product.price or 0.0)


def build_audit(db: Session, agg: dict) -> dict:
    """Expected (book) vs counted per product plus the money value of the variance at cost."""
    book = stock_ops.stock_map(db)
    rows, skipped = [], []
    for pid in sorted(agg["counts"]):
        product = db.get(Product, pid)
        if product is None:
            continue
        counted = float(agg["counts"][pid])
        if product.sell_mode == "loose":
            skipped.append({"product_id": pid, "name": product.name,
                            "reason": "loose item: weigh it, do not count by photo"})
            continue
        expected = float(book.get(pid, 0.0))
        variance = round(counted - expected, 3)
        cost = _unit_cost(product)
        rows.append({
            "product_id": pid, "name": product.name, "name_hi": product.name_hi or "", "unit": product.unit,
            "expected": expected, "counted": counted, "variance": variance, "cost_price": cost,
            "variance_value": round(variance * cost, 2),
            "status": "ok" if abs(variance) < 1e-9 else ("short" if variance < 0 else "excess")})
    short = [r for r in rows if r["status"] == "short"]
    over = [r for r in rows if r["status"] == "excess"]
    loss = round(sum(r["variance_value"] for r in short), 2)       # negative number
    gain = round(sum(r["variance_value"] for r in over), 2)
    audit = {
        "scope": "shelf", "rows": rows, "skipped": skipped,
        "unmatched": [{"name": k, "counted": v} for k, v in agg["unmatched"].items()],
        "totals": {"products": len(rows), "short": len(short), "excess": len(over),
                   "ok": len(rows) - len(short) - len(over), "loss_value": loss, "gain_value": gain,
                   "total_variance_value": round(loss + gain, 2)},
        "per_frame": agg["per_frame"],
        "note": "Shelf count vs book stock. Stock kept in the godown will show as short.",
    }
    audit["message_hi"] = _audit_message(audit)
    return audit


def _audit_message(audit: dict) -> str:
    t = audit["totals"]
    if not audit["rows"]:
        return "Photo mein koi pehchana hua saaman nahi mila."
    if t["short"] == 0:
        return f"{t['products']} item ginay, sab book stock se mel khate hain."
    worst = min((r for r in audit["rows"] if r["status"] == "short"), key=lambda r: r["variance_value"])
    return (f"{t['products']} item ginay, {t['short']} mein stock kam hai. Sabse zyada {worst['name']}: "
            f"{worst['expected']:g} hona chahiye tha, {worst['counted']:g} mila. "
            f"Kul nuksaan {inr(-t['loss_value'])} (cost par).")


@router.post("/shelf-audit")
async def shelf_audit(images: Optional[List[UploadFile]] = File(None), image: Optional[UploadFile] = File(None),
                      db: Session = Depends(get_db)):
    """Shelf photo(s) -> audit proposal. Send many frames of one shelf walk as multipart `images`
    (a single `image` also works); per product the MAX count across frames is used."""
    uploads = list(images or []) + ([image] if image is not None else [])
    if not uploads:
        raise HTTPException(422, "Send at least one photo as multipart field 'images'")
    if len(uploads) > MAX_FRAMES:
        raise HTTPException(422, f"At most {MAX_FRAMES} frames per audit")
    blobs = [await _read_image(u) for u in uploads]

    sem = asyncio.Semaphore(FRAME_CONCURRENCY)

    async def one(blob: tuple[bytes, str]) -> Result | Exception:
        async with sem:
            try:
                return await vision.extract_json_from_image(blob[0], blob[1], "shelf")
            except ProviderError as exc:
                return exc

    t0 = time.perf_counter()
    outcomes = await asyncio.gather(*(one(b) for b in blobs))
    wall_ms = int((time.perf_counter() - t0) * 1000)
    good = [r for r in outcomes if isinstance(r, Result)]
    errors = [str(r) for r in outcomes if not isinstance(r, Result)]
    if not good:
        raise HTTPException(502, f"Shelf audit failed: {'; '.join(errors)[:300]}")

    agg = aggregate_frames([r.data for r in good], catalog.load_index(db))
    audit = build_audit(db, agg)
    live = [r.source for r in good if r.source != "fixture"]
    source = live[0] if live else "fixture"
    audit.update(frames=len(blobs), frames_read=len(good), frame_errors=errors,
                 sources=sorted({r.source for r in good}))

    action = PendingAction(kind="shelf_audit", payload=audit, status="proposed", source=source,
                           latency_ms=wall_ms)
    db.add(action)
    db.commit()
    db.refresh(action)
    return {"action_id": action.id, "kind": "shelf_audit", "status": action.status, **audit,
            "source": source, "latency_ms": wall_ms, "demo_mode": source == "fixture"}


def _apply_audit(db: Session, product_id: int, target: float, ref: str, note: str) -> float:
    """Set book stock to `target` with an audit StockMove (kind='audit', ref, note). Returns the change.
    (Not stock_ops.set_stock: with autoflush off it annotates the wrong StockMove row.)"""
    diff = round(target - stock_ops.current_stock(db, product_id), 6)
    if diff > 0:
        stock_ops.add_stock(db, product_id, diff, kind="audit", ref=ref, note=note)
    elif diff < 0:
        stock_ops.deduct_fifo(db, product_id, -diff, kind="audit", ref=ref, allow_negative=True)
        db.flush()
        move = db.query(StockMove).filter(StockMove.product_id == product_id, StockMove.ref == ref).order_by(
            StockMove.id.desc()).first()
        if move is not None:
            move.note = note
    return diff


class AuditConfirm(BaseModel):
    counts: Dict[int, float] = Field(default_factory=dict, description="product_id -> corrected counted qty")
    only: Optional[List[int]] = Field(None, description="adjust only these product ids (default: all with variance)")


def _audit_action(db: Session, action_id: int) -> PendingAction:
    action = db.get(PendingAction, action_id)
    if action is None or action.kind != "shelf_audit":
        raise HTTPException(404, f"No shelf audit proposal {action_id}")
    return action


@router.post("/shelf-audit/{action_id}/confirm")
def confirm_shelf_audit(action_id: int, body: Optional[AuditConfirm] = Body(None),
                        db: Session = Depends(get_db)):
    """Set book stock to the counted quantities (StockMove kind='audit') for products with a variance."""
    action = _audit_action(db, action_id)
    if action.status != "proposed":
        raise HTTPException(409, f"Audit already {action.status}")
    body = body or AuditConfirm()
    payload = action.payload or {}
    adjustments = []
    for row in payload.get("rows", []):
        pid = row["product_id"]
        if body.only is not None and pid not in body.only:
            continue
        target = float(body.counts.get(pid, row["counted"]))
        if target < 0:
            raise HTTPException(422, f"Count for product {pid} cannot be negative")
        old = stock_ops.current_stock(db, pid)
        change = _apply_audit(db, pid, target, f"audit:{action.id}", f"shelf audit #{action.id}")
        if abs(change) < 1e-9:
            continue
        adjustments.append({"product_id": pid, "name": row["name"], "old_stock": old, "new_stock": target,
                            "change": round(change, 3), "value": round(change * row["cost_price"], 2)})
    result = {"adjustments": adjustments,
              "total_adjustment_value": round(sum(a["value"] for a in adjustments), 2),
              "message_hi": f"{len(adjustments)} item ka stock sahi kar diya."}
    action.status, action.result, action.resolved_at = "confirmed", result, now_local()
    db.commit()
    events.publish("store", "stock_updated", {
        "reason": "shelf_audit", "audit_id": action.id,
        "products": [{"product_id": a["product_id"], "name": a["name"], "added": a["change"],
                      "new_stock": a["new_stock"]} for a in adjustments]})
    return {"action_id": action.id, "status": "confirmed", **result}


@router.post("/shelf-audit/{action_id}/cancel")
def cancel_shelf_audit(action_id: int, db: Session = Depends(get_db)):
    action = _audit_action(db, action_id)
    if action.status == "confirmed":
        raise HTTPException(409, "Audit already confirmed")
    action.status, action.resolved_at = "cancelled", now_local()
    db.commit()
    return {"action_id": action.id, "status": "cancelled"}
