"""Distributor purchase bills: scan -> proposal -> confirm (F6).

`build_proposal` turns the vision JSON into a proposal dict (stored as
PendingAction(kind='purchase_bill').payload). `commit` writes PurchaseBill, PurchaseItem,
StockBatch (via stock_ops.add_stock), Product.cost_price and brand-new Products.
"""
from __future__ import annotations

import calendar
import re
from copy import deepcopy
from datetime import date, datetime
from typing import Any, Optional

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from models import PendingAction, Product, PurchaseBill, PurchaseItem, Supplier
from services import catalog, pricing, stock_ops
from services.clock import now_local, today_local
from services.price_guard import (check_expiry, check_margin, check_price, check_scheme, flag, inr,
                                  rupees)

SUPPLIER_MATCH_SCORE = 85
LOW_MATCH_SCORE = 90

SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}


class PurchaseError(Exception):
    """Business-rule failure; the router maps `status` to the HTTP status."""

    def __init__(self, message: str, status: int = 400, code: str = "purchase_error"):
        super().__init__(message)
        self.status = status
        self.code = code


# --- parsing helpers ---


def parse_date(value: Any) -> Optional[date]:
    """'2026-10-29', '29/10/2026', '29-10-26', '10/27' (MM/YY -> month end), date -> date."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})[/-](\d{2}|\d{4})", s)  # MM/YY or MM/YYYY: valid to month end
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        year += 2000 if year < 100 else 0
        if 1 <= month <= 12:
            return date(year, month, calendar.monthrange(year, month)[1])
    return None


def _iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# --- lookups ---


def match_supplier(db: Session, name: Optional[str]) -> Optional[Supplier]:
    """Existing supplier whose name matches the bill's printed name (fuzzy, word-order free)."""
    spoken = catalog.normalize(name or "")
    if not spoken:
        return None
    best, best_score = None, 0.0
    for s in db.query(Supplier).all():
        score = fuzz.token_set_ratio(spoken, catalog.normalize(s.name))
        if score > best_score:
            best, best_score = s, score
    return best if best_score >= SUPPLIER_MATCH_SCORE else None


def previous_rate(db: Session, product: Optional[Product], supplier_id: Optional[int]
                  ) -> tuple[Optional[float], str]:
    """Last confirmed cost of the product: same supplier first, then any supplier,
    then the catalog cost price. Returns (rate, source)."""
    if product is None:
        return None, "none"
    base = (db.query(PurchaseItem).join(PurchaseBill, PurchaseBill.id == PurchaseItem.bill_id)
            .filter(PurchaseBill.status == "confirmed", PurchaseItem.product_id == product.id,
                    PurchaseItem.rate > 0))
    order = (PurchaseBill.created_at.desc(), PurchaseItem.id.desc())
    if supplier_id:
        row = base.filter(PurchaseBill.supplier_id == supplier_id).order_by(*order).first()
        if row:
            return float(row.rate), "last_bill"
    row = base.order_by(*order).first()
    if row:
        return float(row.rate), "last_bill_other_supplier"
    if product.cost_price:
        return float(product.cost_price), "catalog_cost"
    return None, "none"


def find_duplicate(db: Session, supplier_id: Optional[int], bill_no: Optional[str]
                   ) -> Optional[PurchaseBill]:
    """A confirmed bill with the same supplier and bill number."""
    if not supplier_id or not (bill_no or "").strip():
        return None
    return (db.query(PurchaseBill)
            .filter(PurchaseBill.supplier_id == supplier_id, PurchaseBill.bill_no == bill_no.strip(),
                    PurchaseBill.status == "confirmed")
            .order_by(PurchaseBill.id.desc()).first())


# --- per-line analysis ---


def _label(line: dict) -> str:
    return line.get("product_name") or line.get("name_raw") or "Item"


def analyze_line(line: dict, today: date) -> dict:
    """(Re)compute the derived fields and flags of a line from its editable inputs
    (qty, rate, mrp, expiry, scheme_text, free_qty_received, previous_rate, product link)."""
    qty, rate = _f(line.get("qty")), _f(line.get("rate"))
    mrp = line.get("mrp")
    mrp = None if mrp in (None, "") else _f(mrp)
    flags: list[dict] = []
    name = _label(line)

    if line.get("is_new_candidate"):
        flags.append(flag("new_product", "info", f"{name}: catalog mein nahi hai, naya item"))
    elif line.get("match_score", 100) < LOW_MATCH_SCORE:
        flags.append(flag("low_match_confidence", "info", f"{name}: product match pakka nahi, check karein"))
    if qty <= 0:
        flags.append(flag("qty_missing", "warn", f"{name}: quantity padhi nahi gayi"))
    if rate <= 0:
        flags.append(flag("rate_missing", "warn", f"{name}: rate padha nahi gaya"))

    price = check_price(rate, line.get("previous_rate"), name=name)
    flags += price["flags"]
    margin = check_margin(rate, mrp, name=name)
    flags += margin["flags"]
    scheme = check_scheme(qty, _f(line.get("free_qty_received")), line.get("scheme_text"),
                          name=name, rate=rate)
    flags += scheme["flags"]
    exp = parse_date(line.get("expiry"))
    expiry = check_expiry(exp, today, name=name)
    flags += expiry["flags"]

    flags.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 3))
    line.update({
        "qty": qty, "rate": rate, "mrp": mrp, "expiry": _iso(exp),
        "free_qty_received": _f(line.get("free_qty_received")),
        "free_qty_expected": scheme["free_expected"], "scheme": scheme["scheme"],
        "rate_delta": price["delta"], "rate_delta_pct": price["delta_pct"],
        "margin_pct": margin["margin_pct"], "days_to_expiry": expiry["days_to_expiry"],
        "line_total": round(qty * rate, 2), "flags": flags,
    })
    return line


def new_product_candidate(raw: dict) -> dict:
    """Suggested catalog entry for a bill line that matched nothing."""
    rate, mrp = _f(raw.get("rate")), raw.get("mrp")
    mrp = _f(mrp) if mrp not in (None, "") else round(rate * 1.15, 2)
    return {"name": str(raw.get("name") or "").strip(), "unit": raw.get("unit") or "packet",
            "mrp": mrp, "cost_price": rate, "gst_rate": pricing.GST_RATES_BY_CATEGORY["packaged_food"],
            "category": "general"}


def _base_line(index: int, raw: dict, product: Optional[Product], score: float,
               prev: Optional[float], prev_source: str) -> dict:
    line = {
        "index": index, "name_raw": raw.get("name") or "", "product_id": product.id if product else None,
        "product_name": product.name if product else None, "match_score": round(float(score), 1),
        "is_new_candidate": product is None, "qty": raw.get("qty"), "unit": raw.get("unit") or "",
        "rate": raw.get("rate"), "mrp": raw.get("mrp"), "batch": raw.get("batch") or "",
        "expiry": raw.get("expiry"), "scheme_text": raw.get("scheme_text") or "",
        "free_qty_received": raw.get("free_qty") or 0, "previous_rate": prev,
        "previous_rate_source": prev_source,
    }
    if product is None:
        line["new_product"] = new_product_candidate(raw)
    return line


# --- proposal ---


def _short(line: dict) -> str:
    return _label(line)


def spoken_summary(proposal: dict) -> str:
    """Hinglish summary read aloud after a scan."""
    lines = [ln for ln in proposal["lines"] if not ln.get("skip")]
    parts = [f"{proposal['supplier']['name'] or 'Distributor'} ka bill: {len(lines)} item, "
             f"kul {inr(proposal['total'])}."]
    if proposal["duplicate"]["is_duplicate"]:
        parts.append(f"Dhyan dein, bill number {proposal['bill_no']} pehle hi enter ho chuka hai.")

    def by_code(code):
        return [ln for ln in lines for f in ln["flags"] if f["code"] == code]

    ups = sorted(by_code("price_increase"), key=lambda ln: -(ln["rate_delta"] or 0))
    missed = [ln for ln in by_code("scheme_missed")]
    sentence = []
    if ups:
        top = ups[:2]
        sentence.append(" aur ".join(f"{_short(ln)} {inr(ln['rate_delta'])} mehenga aaya hai" for ln in top))
        if len(ups) > 2:
            sentence.append(f"{len(ups) - 2} aur item mehenge hain")
    if missed:
        ln = missed[0]
        f = next(f for f in ln["flags"] if f["code"] == "scheme_missed")
        what = f"'{(ln['scheme_text'] or '').strip()}' ka free packet nahi gina" if f["missing"] == 1 else \
            f"'{(ln['scheme_text'] or '').strip()}' ke {rupees(f['missing'])} free packet nahi gine"
        extra = f" (aur {len(missed) - 1} item mein bhi)" if len(missed) > 1 else ""
        sentence.append(what + extra if ups else f"{_short(ln)} mein {what}{extra}")
    if sentence:
        parts.append(", aur ".join(sentence) + ".")
    exp = sorted(by_code("expiry_soon") + by_code("expired"), key=lambda ln: ln["days_to_expiry"])
    if exp:
        first = exp[0]
        msg = f"{_short(first)} {first['days_to_expiry']} din mein expire ho jayega"
        if first["days_to_expiry"] < 0:
            msg = f"{_short(first)} expire ho chuka hai"
        parts.append(msg + (f" (aur {len(exp) - 1} item)" if len(exp) > 1 else "") + ".")
    low = [ln for ln in by_code("low_margin") if ln not in ups]  # already covered by "mehenga"
    if low:
        parts.append(f"{_short(low[0])} par margin bahut kam hai.")
    new = [ln for ln in lines if ln["is_new_candidate"]]
    if new:
        names = ", ".join(ln["name_raw"] for ln in new[:2])
        parts.append(f"{names} naya item hai, catalog mein jodna hai?")
    if len(parts) == 1:
        parts.append("Sab theek lag raha hai.")
    return " ".join(parts)


def build_proposal(db: Session, data: dict, today: Optional[date] = None) -> dict:
    """Vision JSON -> proposal dict (JSON-serialisable)."""
    today = today or today_local()
    supplier = match_supplier(db, data.get("supplier"))
    supplier_id = supplier.id if supplier else None
    bill_no = (data.get("bill_no") or "").strip() or None
    index = catalog.load_index(db)

    lines: list[dict] = []
    for i, raw in enumerate(data.get("lines") or []):
        product, score = index.find_in_phrase(raw.get("name") or "")
        prev, source = previous_rate(db, product, supplier_id)
        lines.append(analyze_line(_base_line(i, raw, product, score, prev, source), today))

    dup = find_duplicate(db, supplier_id, bill_no)
    proposal = {
        "supplier": {"name": supplier.name if supplier else (data.get("supplier") or None),
                     "supplier_id": supplier_id, "is_new": supplier is None and bool(data.get("supplier")),
                     "printed_name": data.get("supplier")},
        "bill_no": bill_no,
        "bill_date": _iso(parse_date(data.get("date"))) or today.isoformat(),
        "duplicate": {"is_duplicate": dup is not None, "bill_id": dup.id if dup else None},
        "lines": lines,
        "total": round(sum(ln["line_total"] for ln in lines), 2),
    }
    proposal["flags"] = summary_flags(proposal)
    proposal["summary"] = summarize(proposal)
    proposal["message_hi"] = spoken_summary(proposal)
    return proposal


def summary_flags(proposal: dict) -> list[dict]:
    out: list[dict] = []
    if proposal["duplicate"]["is_duplicate"]:
        out.append(flag("duplicate_bill", "error",
                        f"Bill {proposal['bill_no']} pehle hi enter ho chuka hai",
                        bill_id=proposal["duplicate"]["bill_id"]))
    if proposal["supplier"]["is_new"]:
        out.append(flag("new_supplier", "info", f"Naya supplier: {proposal['supplier']['name']}"))
    if not proposal["bill_no"]:
        out.append(flag("bill_no_missing", "info", "Bill number padha nahi gaya"))
    for ln in proposal["lines"]:
        if ln.get("skip"):
            continue
        for f in ln["flags"]:
            if f["severity"] != "info" or f["code"] in ("new_product", "price_drop"):
                out.append({**f, "line_index": ln["index"], "product_id": ln["product_id"],
                            "name": _label(ln)})
    out.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 3))
    return out


def summarize(proposal: dict) -> dict:
    lines = [ln for ln in proposal["lines"] if not ln.get("skip")]
    codes = lambda c: [ln for ln in lines if any(f["code"] == c for f in ln["flags"])]  # noqa: E731
    missed_value = 0.0
    for ln in lines:
        for f in ln["flags"]:
            if f["code"] == "scheme_missed":
                missed_value += f.get("value") or 0.0
    return {
        "lines": len(lines),
        "matched": sum(1 for ln in lines if not ln["is_new_candidate"]),
        "new_products": len(codes("new_product")),
        "price_increases": len(codes("price_increase")),
        "price_increase_cost": round(sum((ln["rate_delta"] or 0) * ln["qty"] for ln in codes("price_increase")), 2),
        "schemes_missed": len(codes("scheme_missed")),
        "scheme_missed_value": round(missed_value, 2),
        "expiring": len(codes("expiry_soon")) + len(codes("expired")),
        "low_margin": len(codes("low_margin")),
        "duplicate": proposal["duplicate"]["is_duplicate"],
    }


# --- confirm ---


def _apply_edits(lines: list[dict], edits: dict, db: Session, supplier_id: Optional[int],
                 today: date) -> list[dict]:
    """Apply per-line edits from the confirm body and re-run the analysis."""
    by_index = {ln["index"]: ln for ln in lines}
    for e in edits.get("lines") or []:
        ln = by_index.get(e.get("index"))
        if ln is None:
            raise PurchaseError(f"No line with index {e.get('index')}", 422, "bad_line_index")
        for key in ("qty", "rate", "mrp", "batch", "expiry", "scheme_text", "unit"):
            if key in e and e[key] is not None:
                ln[key] = e[key]
        if "free_qty" in e and e["free_qty"] is not None:
            ln["free_qty_received"] = e["free_qty"]
        if e.get("skip") is not None:
            ln["skip"] = bool(e["skip"])
        if e.get("create_product") is not None:
            ln["create_product"] = bool(e["create_product"])
        if e.get("new_product"):
            ln["new_product"] = {**(ln.get("new_product") or {}), **e["new_product"]}
        if e.get("product_id") is not None and e["product_id"] != ln.get("product_id"):
            product = db.get(Product, e["product_id"])
            if product is None:
                raise PurchaseError(f"Product {e['product_id']} not found", 404, "product_not_found")
            ln.update(product_id=product.id, product_name=product.name, is_new_candidate=False,
                      match_score=100.0)
            ln.pop("new_product", None)
            ln["previous_rate"], ln["previous_rate_source"] = previous_rate(db, product, supplier_id)
    for ln in lines:
        analyze_line(ln, today)
    return lines


def _create_product(db: Session, ln: dict, supplier_id: Optional[int]) -> Product:
    np = ln.get("new_product") or new_product_candidate({"name": ln["name_raw"], "rate": ln["rate"],
                                                           "mrp": ln["mrp"], "unit": ln["unit"]})
    name = np.get("name") or ln["name_raw"]
    norm = catalog.normalize(name)
    aliases = sorted({norm, catalog.normalize(re.sub(r"\b\d+(?:\.\d+)?\s*(?:g|gm|kg|ml|l)\b", "", name))} - {""})
    product = Product(
        name=name, name_hi=np.get("name_hi") or "", aliases=aliases,
        category=np.get("category") or "general", gst_rate=_f(np.get("gst_rate"), 5.0),
        mrp=_f(np.get("mrp")), cost_price=_f(ln["rate"]) or _f(np.get("cost_price")),
        unit=np.get("unit") or "packet", sell_mode="unit", base_unit="pc", threshold=5,
        supplier_id=supplier_id, active=True)
    db.add(product)
    db.flush()
    return product


def commit(db: Session, action: PendingAction, edits: Optional[dict] = None,
           today: Optional[date] = None) -> tuple[dict, list[tuple[str, dict]]]:
    """Commit a proposed purchase bill. Returns (result, events). The caller owns
    db.commit() and publishes the events on channel 'store' after it succeeds."""
    edits = edits or {}
    today = today or today_local()
    if action.kind != "purchase_bill":
        raise PurchaseError("Not a purchase bill proposal", 404, "wrong_kind")
    if action.status != "proposed":
        raise PurchaseError(f"Proposal already {action.status}", 409, "already_resolved")

    payload = deepcopy(action.payload or {})
    sup = payload.get("supplier") or {}
    supplier_id = edits.get("supplier_id") or sup.get("supplier_id")
    supplier_name = edits.get("supplier_name") or sup.get("name")
    bill_no = payload.get("bill_no")

    dup = find_duplicate(db, supplier_id, bill_no)
    if dup is not None and not edits.get("force"):
        raise PurchaseError(f"Bill {bill_no} is already recorded (purchase #{dup.id}). "
                            "Send force=true to record it again.", 409, "duplicate_bill")

    lines = _apply_edits(payload["lines"], edits, db, supplier_id, today)
    if supplier_id is None and supplier_name:
        supplier = Supplier(name=supplier_name)
        db.add(supplier)
        db.flush()
        supplier_id = supplier.id
    elif supplier_id is not None and db.get(Supplier, supplier_id) is None:
        raise PurchaseError(f"Supplier {supplier_id} not found", 404, "supplier_not_found")

    kept = [ln for ln in lines if not ln.get("skip")]
    if not kept:
        raise PurchaseError("Nothing to record: all lines skipped", 422, "empty_bill")
    create_all = bool(edits.get("create_new_products"))

    bill = PurchaseBill(
        supplier_id=supplier_id, bill_no=bill_no, bill_date=parse_date(payload.get("bill_date")) or today,
        total=round(sum(ln["line_total"] for ln in kept), 2), status="confirmed",
        photo_ref=payload.get("photo_ref"), flags=[], created_at=now_local())
    db.add(bill)
    db.flush()

    stock_updates: list[dict] = []
    created: list[dict] = []
    for ln in kept:
        product = db.get(Product, ln["product_id"]) if ln.get("product_id") else None
        if product is None and (ln.get("create_product") or create_all):
            product = _create_product(db, ln, supplier_id)
            ln.update(product_id=product.id, product_name=product.name, is_new_candidate=False)
            created.append({"product_id": product.id, "name": product.name})
        free_recv = _f(ln.get("free_qty_received"))
        db.add(PurchaseItem(
            bill_id=bill.id, product_id=product.id if product else None, name_raw=ln["name_raw"],
            qty=ln["qty"], unit=ln.get("unit") or None, rate=ln["rate"], prev_rate=ln.get("previous_rate"),
            mrp=ln.get("mrp"), batch_no=ln.get("batch") or None, expiry=parse_date(ln.get("expiry")),
            scheme_text=ln.get("scheme_text") or None, free_qty_expected=ln["free_qty_expected"],
            free_qty_received=free_recv, flags=ln["flags"]))
        received = ln["qty"] + free_recv
        if product is not None and received > 0:
            before = stock_ops.current_stock(db, product.id)
            stock_ops.add_stock(
                db, product.id, received, batch_no=ln.get("batch") or None, expiry=parse_date(ln.get("expiry")),
                cost_price=ln["rate"] or None, supplier_id=supplier_id, kind="restock",
                ref=f"purchase:{bill.id}", note=f"bill {bill_no}" if bill_no else "distributor bill",
                at=now_local())
            db.flush()  # sessions run with autoflush off; keep later current_stock() reads accurate
            if ln["rate"] > 0:
                product.cost_price = ln["rate"]
            if product.supplier_id is None and supplier_id:
                product.supplier_id = supplier_id
            stock_updates.append({"product_id": product.id, "name": product.name, "added": received,
                                  "free_qty": free_recv, "old_stock": before,
                                  "new_stock": round(before + received, 3),
                                  "cost_price": product.cost_price})
    payload["lines"] = lines
    bill.flags = summary_flags({**payload, "supplier": {**sup, "name": supplier_name}, "lines": lines,
                                "duplicate": payload.get("duplicate") or {"is_duplicate": False}})

    result = {
        "bill_id": bill.id, "supplier_id": supplier_id, "supplier": supplier_name, "bill_no": bill_no,
        "total": bill.total, "items_recorded": len(kept), "stock_updates": stock_updates,
        "new_products": created, "flags": bill.flags,
        "message_hi": f"{len(stock_updates)} item ka stock update ho gaya. Bill {inr(bill.total)}.",
    }
    action.status = "confirmed"
    action.result = result
    action.payload = payload
    action.resolved_at = now_local()
    events = [("stock_updated", {
        "reason": "purchase", "bill_id": bill.id, "supplier": supplier_name,
        "products": [{k: u[k] for k in ("product_id", "name", "added", "new_stock")} for u in stock_updates],
        "new_products": created})]
    return result, events
