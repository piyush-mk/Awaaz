"""Reorder drafts: per-supplier purchase orders from days of cover x festival demand.

    need = velocity x lead_days x festival_multiplier + safety - stock

`lead_days` is the supplier's lead time (at least 1 day); `safety` is the larger of the
product's alert threshold and one day of (festival) demand. The result is rounded UP to
the buying step (carton size when a carton product exists, 5 kg/l for loose goods, else
whole units). The supplier is the one on the product's last confirmed PurchaseItem, then
`Product.supplier_id`. Each supplier gets one `PendingAction(kind='purchase_order')`;
sending it writes a WhatsApp message to the supplier through `services.whatsapp.notify`.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from models import PendingAction, Product, StoreProfile, Supplier
from services import events, festivals, insights, stock_ops, whatsapp
from services.clock import now_local, today_local

KIND = "purchase_order"
FESTIVAL_HORIZON_DAYS = 14


class ReorderError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _festival_demand(tags: list[str], today: date) -> tuple[float, Optional[dict]]:
    """(largest multiplier, the festival that causes it) among festivals in the next 14 days."""
    best, best_f = 1.0, None
    for f in festivals.upcoming(today, FESTIVAL_HORIZON_DAYS):
        m = festivals.multiplier(tags or [], f)
        if m > best:
            best, best_f = m, f
    return best, best_f


def _round_up(need: float, product: Product, carton: Optional[Product]) -> tuple[float, str]:
    """(qty rounded up to the buying step, step description)."""
    if carton is not None and carton.pack_size:
        step = float(carton.pack_size)
        return math.ceil(need / step) * step, f"{carton.name} ({step:g} ka pack)"
    if product.sell_mode == "loose":
        step = 5.0 if need >= 5 else 1.0
        return math.ceil(need / step) * step, f"{step:g} {product.unit} ke step mein"
    return float(math.ceil(need)), "poori ginti"


def _reason(p: Product, cover: Optional[float], stock: float, mult: float, fest: Optional[dict]) -> str:
    name = insights.short_name(p).lower()
    if cover is None:
        base = f"{name}: kam stock ({stock:g} {p.unit} bacha)"
    elif cover < 0.75:
        base = f"{name}: sirf aaj bhar ka stock"
    else:
        base = f"{name}: {round(cover):g} din ka stock"
    if mult > 1.0 and fest:
        base += f", {fest['name']} se pehle {insights.fmt_mult(mult)}x demand"
    return base


def draft_orders(db: Session, today: Optional[date] = None, supplier_id: Optional[int] = None
                 ) -> dict[str, Any]:
    """Build (but do not store) the suggested purchase orders.
    Returns {"orders": [payload,...], "unassigned": [...]}."""
    today = today or today_local()
    stock = stock_ops.stock_map(db)
    vel = insights.velocity_map(db, today)
    last_buy = insights.last_purchase_map(db)
    suppliers = {s.id: s for s in db.query(Supplier).all()}
    products = db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all()
    cartons = {p.parent_id: p for p in products if p.parent_id and p.pack_size}

    by_supplier: dict[int, list[dict]] = {}
    unassigned: list[dict] = []
    festival_seen: dict[int, dict] = {}
    for p in products:
        if p.parent_id:  # carton products are bought via their parent's step, not on their own
            continue
        qty_now = stock.get(p.id, 0.0)
        v = vel.get(p.id, 0.0)
        cover = insights.cover_of(qty_now, v)
        mult, fest = _festival_demand(p.festival_tags or [], today)
        sup_id = (last_buy.get(p.id) or {}).get("supplier_id") or p.supplier_id
        sup = suppliers.get(sup_id) if sup_id else None
        lead = max(float(sup.lead_days or 0) if sup else 1.0, 1.0)
        safety = max(float(p.threshold or 0.0), v * mult)
        need = v * lead * mult + safety - qty_now
        if need <= 1e-9:
            continue
        qty, step = _round_up(need, p, cartons.get(p.id))
        rate = (last_buy.get(p.id) or {}).get("rate") or float(p.cost_price or p.mrp or 0.0)
        line = {
            "product_id": p.id, "name": p.name, "name_hi": p.name_hi, "unit": p.unit, "qty": qty,
            "step": step, "current_stock": qty_now, "cover_days": cover, "velocity_per_day": round(v, 2),
            "multiplier": mult, "festival": fest["name"] if fest else None,
            "est_rate": round(float(rate), 2), "est_amount": round(qty * float(rate), 2),
            "reason": _reason(p, cover, qty_now, mult, fest),
        }
        if sup is None:
            unassigned.append(line)
            continue
        if supplier_id is not None and sup.id != supplier_id:
            continue
        by_supplier.setdefault(sup.id, []).append(line)
        if fest:
            festival_seen[sup.id] = fest

    orders = []
    for sid, lines in by_supplier.items():
        sup = suppliers[sid]
        lines.sort(key=lambda r: (r["cover_days"] is None, r["cover_days"] or 0.0, r["product_id"]))
        fest = festival_seen.get(sid)
        orders.append({
            "supplier_id": sid, "supplier_name": sup.name, "contact_name": sup.contact_name,
            "phone": sup.phone, "lead_days": int(sup.lead_days or 0), "visit_day": sup.visit_day,
            "lines": lines, "total_est": round(sum(r["est_amount"] for r in lines), 2),
            "festival": ({"name": fest["name"], "date": fest["date"].isoformat(),
                          "days_away": (fest["date"] - today).days} if fest else None),
            "created_for": today.isoformat(),
        })
    orders.sort(key=lambda o: (-sum(1 for r in o["lines"] if r["multiplier"] > 1), -o["total_est"]))
    return {"orders": orders, "unassigned": unassigned}


def _view(action: PendingAction) -> dict[str, Any]:
    p = dict(action.payload or {})
    return {"action_id": action.id, "po_number": po_number(action.id), "status": action.status,
            "sent": action.status == "confirmed", "source": action.source, "result": action.result,
            "created_at": action.created_at.isoformat() if action.created_at else None, **p}


def po_number(action_id: int) -> str:
    return f"PO-{action_id:04d}"


def save_drafts(db: Session, drafts: dict[str, Any], latency_ms: int = 0) -> list[dict[str, Any]]:
    """Store each order as a proposed PendingAction; older proposed POs for the same supplier
    are cancelled so repeated drafting never piles up duplicates."""
    out = []
    for order in drafts["orders"]:
        for old in db.query(PendingAction).filter(PendingAction.kind == KIND,
                                                  PendingAction.status == "proposed").all():
            if (old.payload or {}).get("supplier_id") == order["supplier_id"]:
                old.status = "cancelled"
                old.resolved_at = now_local()
        action = PendingAction(kind=KIND, payload=order, status="proposed", source="rules",
                               latency_ms=latency_ms)
        db.add(action)
        db.flush()
        out.append(_view(action))
    return out


def list_orders(db: Session, status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    q = db.query(PendingAction).filter(PendingAction.kind == KIND)
    if status:
        q = q.filter(PendingAction.status == status)
    return [_view(a) for a in q.order_by(PendingAction.id.desc()).limit(limit).all()]


def get_order(db: Session, action_id: int) -> PendingAction:
    action = db.get(PendingAction, action_id)
    if action is None or action.kind != KIND:
        raise ReorderError(404, "purchase order not found")
    return action


def po_text(db: Session, action: PendingAction, note: Optional[str] = None) -> str:
    """The WhatsApp message sent to the supplier."""
    p = action.payload or {}
    store = db.query(StoreProfile).first()
    store_name = store.name if store else "Ramesh General Store"
    place = f", {store.address.split(',')[0]}" if store and store.address else ""
    contact = (p.get("contact_name") or "").split(" ")[0]
    lines = [f"*{po_number(action.id)}* | {store_name}{place}", "",
             f"Namaste {contact + ' ji' if contact else 'ji'}, kripya ye maal bhejein:"]
    for i, ln in enumerate(p.get("lines", []), 1):
        lines.append(f"{i}. {ln['name']}: {ln['qty']:g} {ln['unit']}")
    total = sum(float(ln.get("est_amount") or 0.0) for ln in p.get("lines", []))
    if total:
        lines.append(f"\nAnumaanit: {insights.inr(total)}")
    fest = p.get("festival")
    due = today_local() + timedelta(days=int(p.get("lead_days") or 1))
    if fest:
        lines.append(f"{fest['name']} ({insights.fmt_date_short(date.fromisoformat(fest['date']))}) "
                     f"se pehle chahiye, kripya {insights.fmt_date_short(due)} tak bhej dein.")
    else:
        lines.append(f"Kripya {insights.fmt_date_short(due)} tak bhej dein.")
    if note:
        lines.append(note.strip())
    lines.append("Dhanyavaad.")
    return "\n".join(lines)


def apply_edits(db: Session, action: PendingAction, edits: list[dict[str, Any]]) -> None:
    """Edit quantities: {product_id, qty}; qty 0 removes the line; unknown products are added."""
    payload = dict(action.payload or {})
    lines = [dict(ln) for ln in payload.get("lines", [])]
    for e in edits:
        pid, qty = e.get("product_id"), float(e.get("qty", 0) or 0)
        if qty < 0:
            raise ReorderError(422, "qty cannot be negative")
        hit = next((ln for ln in lines if ln["product_id"] == pid), None)
        if hit is not None:
            if qty == 0:
                lines.remove(hit)
            else:
                hit["qty"] = qty
                hit["est_amount"] = round(qty * float(hit.get("est_rate") or 0.0), 2)
        elif qty > 0:
            prod = db.get(Product, pid)
            if prod is None:
                raise ReorderError(404, f"product {pid} not found")
            rate = float(prod.cost_price or prod.mrp or 0.0)
            lines.append({"product_id": prod.id, "name": prod.name, "name_hi": prod.name_hi, "unit": prod.unit,
                          "qty": qty, "step": "", "current_stock": stock_ops.current_stock(db, prod.id),
                          "cover_days": None, "velocity_per_day": 0.0, "multiplier": 1.0, "festival": None,
                          "est_rate": rate, "est_amount": round(qty * rate, 2), "reason": "haath se joda gaya"})
    if not lines:
        raise ReorderError(422, "purchase order has no lines left")
    payload["lines"] = lines
    payload["total_est"] = round(sum(ln["est_amount"] for ln in lines), 2)
    action.payload = payload


def send_order(db: Session, action_id: int, edits: Optional[list[dict[str, Any]]] = None,
               note: Optional[str] = None) -> dict[str, Any]:
    """Send the PO to the supplier on WhatsApp (outbox + SSE) and mark it confirmed."""
    action = get_order(db, action_id)
    if action.status == "confirmed":
        raise ReorderError(409, "purchase order already sent")
    if action.status == "cancelled":
        raise ReorderError(409, "purchase order was cancelled (a newer draft replaced it)")
    if edits:
        apply_edits(db, action, edits)
    payload = action.payload or {}
    body = po_text(db, action, note)
    msg = whatsapp.notify(db, payload.get("phone"), body, "text", supplier_id=payload.get("supplier_id"))
    action.status = "confirmed"
    action.resolved_at = now_local()
    action.result = {"message_id": msg.id, "sent_at": now_local().isoformat(timespec="seconds"),
                     "to": payload.get("phone")}
    db.commit()
    events.publish("store", "reorder_sent", {
        "action_id": action.id, "po_number": po_number(action.id), "supplier_id": payload.get("supplier_id"),
        "supplier_name": payload.get("supplier_name"), "lines": len(payload.get("lines", [])),
        "total_est": payload.get("total_est")})
    return {"action_id": action.id, "po_number": po_number(action.id), "status": "sent",
            "message": {"id": msg.id, "to": msg.to, "type": msg.type, "body": msg.body,
                        "status": msg.status, "supplier_id": msg.supplier_id, "channel": msg.channel},
            "order": _view(action)}
