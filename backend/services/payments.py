"""Payment rails, cart checkout and payment completion.

RAILS. A Payment row carries `rail`, the way its QR/collect request was created:
    upi_intent   a standard UPI deep link/QR for the exact amount (default, works with any UPI app)
    simulated    same QR string, confirmed by the app button / Soundbox key / simulate endpoint
    paytm_dqr    Paytm Dynamic QR (NOT implemented)

>>> ADAPTER POINT (Paytm Dynamic QR) <<<  To enable the real rail, implement the two functions
`create_qr` and `fetch_status` below for rail == "paytm_dqr" (Paytm "Create QR code" API with MID +
merchant key, checksum via `paytmchecksum`, then the transaction-status API or the payment
callback posted to /webhooks/payments) and return "paytm_dqr" from `active_rail()` when PAYTM_MID
is configured. Nothing else in the counter flow needs to change: checkout stores `rail`, the
Soundbox renders `qr_payload`, and settlement always goes through `settle()`.

CHECKOUT. `checkout_cart` turns a Cart into a pending Invoice plus Payment rows (UPI / cash /
khata) and either waits for the UPI payment or, for cash/khata-only bills, completes at once.
COMPLETION. `settle` marks a payment successful (idempotent), then `finalize_invoice` marks the
invoice paid, deducts stock FIFO, detects low stock, publishes `payment_received` and queues the
WhatsApp text receipt and voice receipt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from config import settings
from models import Cart as CartRow, Customer, Invoice, Payment, Product
from schemas import CartLine
from services import events, invoicing, khata, receipts, stock_ops, tts_cache
from services.clock import now_local

log = logging.getLogger("awaaz.payments")

RAIL_UPI_INTENT = "upi_intent"
RAIL_PAYTM_DQR = "paytm_dqr"
RAIL_SIMULATED = "simulated"
RAIL_MANUAL = "manual"  # cash and khata parts: nothing to collect online
IMPLEMENTED_RAILS = (RAIL_UPI_INTENT, RAIL_SIMULATED)


# ---------------------------------------------------------------------------
# rails (adapter point)
# ---------------------------------------------------------------------------


def active_rail() -> str:
    """Rail used for new UPI payments. ADAPTER POINT: return RAIL_PAYTM_DQR when a Paytm MID is set."""
    return RAIL_UPI_INTENT


def upi_intent_string(amount: float, order_id: str, note: Optional[str] = None,
                      vpa: Optional[str] = None, name: Optional[str] = None) -> str:
    """upi://pay?pa=<vpa>&pn=<name>&am=<amount>&cu=INR&tr=<order_id>&tn=<note>"""
    vpa = vpa or settings.merchant_upi_vpa
    name = name or settings.merchant_name
    note = note or f"Bill {order_id}"
    return (f"upi://pay?pa={quote(vpa, safe='@')}&pn={quote(name)}&am={amount:.2f}&cu=INR"
            f"&tr={quote(order_id)}&tn={quote(note)}")


@dataclass
class QrInfo:
    rail: str
    order_id: str
    amount: float
    upi_string: str  # the deep link (same as qr_payload for the UPI rails)
    qr_payload: str  # exactly what the QR encodes
    expires_in_s: Optional[int] = None
    meta: dict[str, Any] = field(default_factory=dict)


def create_qr(order_id: str, amount: float, note: Optional[str] = None,
              rail: Optional[str] = None) -> QrInfo:
    """Create the collect request for a UPI payment on the given rail."""
    rail = rail or active_rail()
    if rail in (RAIL_UPI_INTENT, RAIL_SIMULATED):
        s = upi_intent_string(amount, order_id, note)
        return QrInfo(rail, order_id, amount, s, s)
    if rail == RAIL_PAYTM_DQR:
        # ADAPTER POINT: call Paytm Dynamic QR create API and return its qrData in qr_payload.
        raise NotImplementedError("Paytm Dynamic QR rail is not implemented")
    raise ValueError(f"unknown payment rail: {rail}")


def fetch_status(payment: Payment) -> str:
    """Current status of a payment on its rail. Local rails: whatever we recorded.
    ADAPTER POINT: for paytm_dqr call the Paytm transaction-status API here."""
    return payment.status


# ---------------------------------------------------------------------------
# provider callbacks
# ---------------------------------------------------------------------------

SUCCESS_STATES = {"SUCCESS", "TXN_SUCCESS", "PAID", "COMPLETED", "CAPTURED", "SUCCEEDED", "OK"}
FAILED_STATES = {"FAILED", "FAILURE", "TXN_FAILURE", "CANCELLED", "CANCELED", "EXPIRED", "DECLINED"}


def _pick(d: dict, *names: str) -> Any:
    lower = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in lower and lower[n.lower()] not in (None, ""):
            return lower[n.lower()]
    return None


def parse_callback(payload: dict) -> dict:
    """Normalise a generic/Paytm-style callback into {order_id, state, amount, txn_id}.
    state is 'success' | 'failed' | 'pending'."""
    if not isinstance(payload, dict):
        return {"order_id": None, "state": "pending", "amount": None, "txn_id": None}
    for key in ("body", "data", "payload"):
        if isinstance(payload.get(key), dict):
            payload = {**payload, **payload[key]}
    status = str(_pick(payload, "status", "txn_status", "txnstatus", "resultstatus", "state") or "")
    state = "success" if status.upper() in SUCCESS_STATES else \
        "failed" if status.upper() in FAILED_STATES else "pending"
    amount = _pick(payload, "amount", "txnamount", "txn_amount", "am")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
    return {"order_id": _pick(payload, "order_id", "orderid", "tr", "merchant_order_id"),
            "state": state, "amount": amount,
            "txn_id": _pick(payload, "txn_id", "txnid", "bank_txn_id", "utr")}


# ---------------------------------------------------------------------------
# split allocation
# ---------------------------------------------------------------------------

MODES = ("upi", "cash", "khata")


def _p(x: float) -> int:
    return int(round(float(x) * 100 + 1e-9))


def allocate(total: float, splits: Optional[dict]) -> dict[str, float]:
    """Split `total` over upi/cash/khata. `splits` values: a number, or None meaning 'the rest'.
    No splits -> all UPI. A missing key counts as 0 unless nothing marks a remainder, in which
    case any shortfall goes to khata > upi > cash (the first of these set to None, else UPI)."""
    if not splits or not any(k in splits for k in MODES):
        return {"upi": round(total, 2), "cash": 0.0, "khata": 0.0}
    total_p = _p(total)
    known = {m: _p(splits[m]) for m in MODES if splits.get(m) is not None}
    unknown = [m for m in ("khata", "upi", "cash") if m in splits and splits[m] is None]
    rest = total_p - sum(known.values())
    if any(v < 0 for v in known.values()):
        raise HTTPException(400, "Amounts negative nahi ho sakte")
    if rest < 0:
        raise HTTPException(400, f"Parts ka jod ₹{sum(known.values()) / 100:g} bill se zyada hai "
                                 f"(₹{total_p / 100:g})")
    out = {m: known.get(m, 0) for m in MODES}
    if rest:
        out[unknown[0] if unknown else "upi"] += rest
    return {m: round(v / 100, 2) for m, v in out.items()}


# ---------------------------------------------------------------------------
# views
# ---------------------------------------------------------------------------


def _payment_dict(p: Payment) -> dict:
    return {"id": p.id, "order_id": p.order_id, "mode": p.mode, "amount": p.amount, "status": p.status,
            "rail": p.rail, "paid_at": p.paid_at.isoformat() if p.paid_at else None}


def invoice_brief(invoice: Invoice) -> dict:
    return {"id": invoice.id, "number": invoice.number, "status": invoice.status,
            "doc_type": invoice.doc_type, "total": invoice.total,
            "customer_id": invoice.customer_id, "public_token": invoice.public_token,
            "receipt_url": receipts.receipt_url(invoice)}


def payment_view(payment: Payment) -> dict:
    """GET /api/payments/{order_id}."""
    inv = payment.invoice
    return {"order_id": payment.order_id, "status": fetch_status(payment), "mode": payment.mode,
            "amount": payment.amount, "rail": payment.rail,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
            "invoice": invoice_brief(inv) if inv else None,
            "payments": [_payment_dict(p) for p in inv.payments] if inv else [],
            "invoice_paid": bool(inv and inv.status == "paid")}


def _customer_brief(db: Session, customer_id: Optional[int]) -> Optional[dict]:
    c = db.get(Customer, customer_id) if customer_id else None
    return {"id": c.id, "name": c.name, "phone": c.phone, "balance": c.balance} if c else None


async def checkout_result(db: Session, invoice: Invoice, *, speak: bool = True,
                          idempotent: bool = False) -> dict:
    """The checkout response/event body for an invoice."""
    upi = next((p for p in invoice.payments if p.mode == "upi"), None)
    pending = [p for p in invoice.payments if p.status == "pending"]
    due = round(sum(p.amount for p in pending), 2)
    qr = None
    if upi is not None and upi.status == "pending":
        qr = create_qr(upi.order_id, upi.amount, f"{settings.merchant_name} bill {invoice.number}",
                       upi.rail if upi.rail in IMPLEMENTED_RAILS else None)
    if due > 0:
        spoken = f"Kul ₹{receipts.fmt_money(invoice.total)}. QR scan karke ₹{receipts.fmt_money(due)} bharein."
    else:
        spoken = f"Bill ban gaya, kul ₹{receipts.fmt_money(invoice.total)}."
    audio_url = None
    if speak:
        audio_url = (await tts_cache.get_speech(spoken)).url
    primary = invoice.payments[0].order_id if invoice.payments else None
    return {
        "order_id": upi.order_id if upi is not None else primary,
        "invoice_id": invoice.id, "invoice_number": invoice.number, "status": invoice.status,
        "doc_type": invoice.doc_type, "total": invoice.total, "amount_due": due,
        "complete": invoice.status == "paid",
        "upi_string": qr.upi_string if qr else None, "qr_payload": qr.qr_payload if qr else None,
        "rail": upi.rail if upi is not None else RAIL_MANUAL,
        "taxable_total": invoice.taxable_total, "cgst_total": invoice.cgst_total,
        "sgst_total": invoice.sgst_total,
        "items": [{"name": it.name, "name_hi": it.name_hi, "qty": it.qty, "unit": it.unit,
                   "rate": it.mrp, "total": it.total} for it in invoice.items],
        "payments": [_payment_dict(p) for p in invoice.payments],
        "customer": _customer_brief(db, invoice.customer_id),
        "receipt_url": receipts.receipt_url(invoice),
        "spoken_text": spoken, "audio_url": audio_url, "idempotent": idempotent,
    }


# ---------------------------------------------------------------------------
# checkout
# ---------------------------------------------------------------------------


async def checkout_cart(db: Session, cart: CartRow, *, splits: Optional[dict] = None,
                        customer_id: Optional[int] = None, rail: Optional[str] = None,
                        note: Optional[str] = None, speak: bool = True) -> dict:
    """Cart -> pending Invoice + Payments. Publishes `checkout` on the store channel (or completes the
    sale immediately when nothing is left to collect online). Safe to call twice (idempotent)."""
    if cart.status == "checked_out" and cart.invoice_id:
        inv = db.get(Invoice, cart.invoice_id)
        if inv is not None:
            return await checkout_result(db, inv, speak=False, idempotent=True)
    lines = [CartLine(**d) for d in (cart.lines or [])]
    if not lines:
        raise HTTPException(400, "Cart khali hai")
    if rail and rail not in IMPLEMENTED_RAILS:
        raise HTTPException(400, f"rail '{rail}' available nahi hai (use {', '.join(IMPLEMENTED_RAILS)})")
    cust_id = customer_id or (splits or {}).get("customer_id") or cart.customer_id
    customer = db.get(Customer, cust_id) if cust_id else None
    if cust_id and customer is None:
        raise HTTPException(404, f"Customer {cust_id} nahi mila")

    invoice = invoicing.create_invoice(db, lines, customer_id=cust_id, status="pending",
                                       cart_id=cart.id, note=note)
    try:
        parts = allocate(invoice.total, splits)
        if parts["khata"] > 0 and customer is None:
            raise HTTPException(400, "Khate mein likhne ke liye customer chuniye (customer_id)")
        if sum(parts.values()) <= 0:
            raise HTTPException(400, "Bill ka total zero hai")
    except HTTPException:
        db.rollback()
        raise

    now = now_local()
    base = f"AWZ{invoice.id:06d}"
    made: list[Payment] = []

    def order_id() -> str:
        return base if not made else f"{base}-{len(made)}"

    if parts["upi"] > 0:
        made.append(Payment(invoice_id=invoice.id, customer_id=cust_id, mode="upi", amount=parts["upi"],
                            status="pending", order_id=order_id(), rail=rail or active_rail()))
    if parts["cash"] > 0:
        made.append(Payment(invoice_id=invoice.id, customer_id=cust_id, mode="cash", amount=parts["cash"],
                            status="success", order_id=order_id(), rail=RAIL_MANUAL, paid_at=now))
    warning = None
    if parts["khata"] > 0:
        made.append(Payment(invoice_id=invoice.id, customer_id=cust_id, mode="khata", amount=parts["khata"],
                            status="success", order_id=order_id(), rail=RAIL_MANUAL, paid_at=now))
        before = khata.balance(db, cust_id)
        khata.add_credit(db, cust_id, parts["khata"], invoice_id=invoice.id, note=f"Bill {invoice.number}")
        if before + parts["khata"] > (customer.credit_limit or 0):
            warning = (f"{customer.name} ka khata ₹{receipts.fmt_money(before + parts['khata'])} ho jayega, "
                       f"limit ₹{receipts.fmt_money(customer.credit_limit or 0)} hai")
    for p in made:
        db.add(p)
    cart.status = "checked_out"
    cart.invoice_id = invoice.id
    if cust_id and not cart.customer_id:
        cart.customer_id = cust_id
    db.flush()
    db.refresh(invoice)

    if any(p.status == "pending" for p in made):
        db.commit()
        result = await checkout_result(db, invoice, speak=speak)
        result["khata_warning"] = warning
        events.publish("store", "checkout", jsonable_encoder({**result, "session_id": cart.id}))
        return result

    done = await finalize_invoice(db, invoice, received=None, via="counter")
    result = await checkout_result(db, invoice, speak=False)
    result.update({"khata_warning": warning, "spoken_text": done["spoken_text"],
                   "audio_url": done["audio_url"], "low_stock": done["low_stock"]})
    return result


# ---------------------------------------------------------------------------
# completion
# ---------------------------------------------------------------------------


def _low_stock(db: Session, stock: list[dict]) -> list[dict]:
    out = []
    for info in stock:
        product = db.get(Product, info["product_id"])
        if product is None:
            continue
        qty = info["new_quantity"]
        level = stock_ops.stock_status(qty, product.threshold or 0.0)
        if level == "high":
            continue
        unit = info.get("unit") or ""
        shown = f"{qty:g} {unit}".strip() if unit in ("kg", "litre") else f"{qty:g}"
        text = (f"{product.name} khatam ho gaya" if qty <= 0
                else f"{product.name} ab sirf {shown} bacha hai")
        out.append({"product_id": product.id, "name": product.name, "quantity": qty, "unit": unit,
                    "threshold": product.threshold, "level": level, "text": text})
    return out


async def finalize_invoice(db: Session, invoice: Invoice, *, received: Optional[Payment],
                           via: str) -> dict:
    """Invoice fully paid: mark it, deduct stock FIFO, publish `payment_received`, send receipts."""
    now = now_local()
    invoice.status = "paid"
    invoice.paid_at = now
    stock = invoicing.deduct_invoice_stock(db, invoice, allow_negative=True, at=now)
    low = _low_stock(db, stock)
    db.commit()

    amount = received.amount if received is not None else invoice.total
    mode = received.mode if received is not None else (
        invoice.payments[0].mode if len(invoice.payments) == 1 else "mixed")
    spoken = f"₹{receipts.fmt_money(amount)} prapt hue."
    if low:
        spoken += " " + ". ".join(item["text"] for item in low[:3]) + "."
    audio_url = (await tts_cache.get_speech(spoken)).url
    data = {
        "order_id": received.order_id if received is not None else
        (invoice.payments[0].order_id if invoice.payments else None),
        "invoice_id": invoice.id, "number": invoice.number, "amount": amount, "total": invoice.total,
        "mode": mode, "via": via, "customer": _customer_brief(db, invoice.customer_id),
        "spoken_text": spoken, "audio_url": audio_url, "low_stock": low,
        "stock_after": [{"product_id": s["product_id"], "name": s["name"], "quantity": s["new_quantity"],
                         "unit": s["unit"]} for s in stock],
        "receipt_url": receipts.receipt_url(invoice), "paid_at": now.isoformat(),
        "session_id": invoice.cart_id,
    }
    events.publish("store", "payment_received", jsonable_encoder(data))
    sent = await receipts.send_receipts(db, invoice)
    db.commit()
    return {**data, "receipts": [{"id": m.id, "type": m.type, "to": m.to} for m in sent]}


async def settle(db: Session, order_id: str, *, via: str = "simulate",
                 amount: Optional[float] = None) -> dict:
    """Mark the payment with this order id successful. Idempotent: a second call changes nothing."""
    payment = db.query(Payment).filter(Payment.order_id == order_id).first()
    if payment is None:
        raise HTTPException(404, f"Order {order_id} nahi mila")
    if payment.status == "success":
        return {**payment_view(payment), "ok": True, "already_paid": True}
    if payment.status in ("failed", "refunded"):
        raise HTTPException(409, f"Payment {payment.status} hai")
    if amount is not None and abs(amount - payment.amount) > 0.01:
        raise HTTPException(422, f"Amount mismatch: expected {payment.amount}, got {amount}")
    payment.status = "success"
    payment.paid_at = now_local()
    invoice = payment.invoice
    if invoice is not None and invoice.status != "paid" and \
            not any(p.status == "pending" for p in invoice.payments if p.id != payment.id):
        done = await finalize_invoice(db, invoice, received=payment, via=via)
    else:
        db.commit()
        done = {"spoken_text": f"₹{receipts.fmt_money(payment.amount)} prapt hue.", "audio_url": None,
                "low_stock": [], "receipts": []}
    db.refresh(payment)
    return {**payment_view(payment), "ok": True, "already_paid": False,
            "spoken_text": done["spoken_text"], "audio_url": done["audio_url"],
            "low_stock": done["low_stock"], "receipts": done["receipts"]}


async def fail(db: Session, order_id: str, reason: str = "failed") -> dict:
    payment = db.query(Payment).filter(Payment.order_id == order_id).first()
    if payment is None:
        raise HTTPException(404, f"Order {order_id} nahi mila")
    if payment.status == "pending":
        payment.status = "failed"
        db.commit()
        events.publish("store", "payment_failed", {"order_id": order_id, "amount": payment.amount,
                                                   "reason": reason, "invoice_id": payment.invoice_id})
    return {**payment_view(payment), "ok": True}
