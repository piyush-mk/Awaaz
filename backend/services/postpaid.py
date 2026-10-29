"""Paytm Postpaid at the counter: a clearly SIMULATED flow (no real Paytm integration exists).

offer   -> PendingAction(kind="postpaid_offer", payload={... simulated: true})
approve -> Payment(mode="postpaid", status="success", rail="simulated") so the shop is paid now,
           a WhatsApp to the customer, `postpaid_approved` on the `store` channel.
No KhataEntry is written: the customer never owes the shop, the (simulated) lender carries the risk.
Every dict returned and every message sent carries `simulated: true` / the word "simulated".
"""
from __future__ import annotations

import secrets
from typing import Any, Optional

from sqlalchemy.orm import Session

from config import settings
from models import Customer, Invoice, PendingAction, Payment
from services import events
from services import whatsapp as wa
from services.clock import now_local
from services.khata import fmt_inr

KIND = "postpaid_offer"
SIMULATED_TAG = "(simulated demo)"


def credit_line(customer: Customer) -> float:
    """Simulated Postpaid limit: starts at Rs 10,000, minus Rs 2,000 for every late khata payment."""
    return float(max(2000, 10000 - 2000 * int(customer.late_payments or 0)))


def offer_link(offer_id: int) -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/khata/postpaid/{offer_id}/page"


def _view(action: PendingAction, customer: Optional[Customer] = None) -> dict[str, Any]:
    p = action.payload or {}
    out = {
        "simulated": True,
        "offer_id": action.id,
        "status": {"proposed": "offered", "confirmed": "approved", "cancelled": "cancelled"}.get(
            action.status, action.status),
        "customer_id": p.get("customer_id"),
        "customer": p.get("customer"),
        "amount": p.get("amount"),
        "eligible": p.get("eligible"),
        "limit": p.get("limit"),
        "invoice_id": p.get("invoice_id"),
        "message_hi": p.get("message_hi"),
        "link": p.get("link"),
        "payment_id": (action.result or {}).get("payment_id"),
    }
    return out


def view(action: PendingAction) -> dict[str, Any]:
    return _view(action)


def get_offer(db: Session, offer_id: int) -> Optional[PendingAction]:
    action = db.get(PendingAction, offer_id)
    return action if action is not None and action.kind == KIND else None


def create_offer(db: Session, customer: Customer, amount: float, invoice_id: Optional[int] = None,
                 send: bool = False) -> dict[str, Any]:
    """Create the offer. `send=True` also WhatsApps the customer the (simulated) approval link."""
    amount = round(abs(float(amount)), 2)
    limit = credit_line(customer)
    eligible = 0 < amount <= limit
    action = PendingAction(kind=KIND, status="proposed", source="rules", payload={}, session_id=None)
    db.add(action)
    db.flush()
    link = offer_link(action.id)
    if eligible:
        msg = (f"{customer.name}, Paytm Postpaid se ₹{fmt_inr(amount)} abhi chuka sakte hain, "
               f"baad mein aasaan kisht mein wapas karein. Aapki Postpaid limit ₹{fmt_inr(limit)} hai. "
               f"Approve karein {SIMULATED_TAG}.")
    else:
        msg = (f"{customer.name} ki Postpaid limit ₹{fmt_inr(limit)} hai, ₹{fmt_inr(amount)} ke liye "
               f"kaafi nahi {SIMULATED_TAG}.")
    action.payload = {
        "simulated": True, "customer_id": customer.id, "customer": customer.name, "amount": amount,
        "limit": limit, "eligible": eligible, "invoice_id": invoice_id, "message_hi": msg, "link": link,
    }
    out = _view(action, customer)
    out["whatsapp"] = None
    if send and eligible:
        wa_msg = wa.notify(db, customer.phone,
                           f"{msg}\n{link}\nSimulated: yeh sirf demo hai, asli paise nahi kate.",
                           customer_id=customer.id)
        out["whatsapp"] = {"message_id": wa_msg.id, "status": wa_msg.status, "simulated": True}
    events.publish("store", "postpaid_offered", {
        "simulated": True, "offer_id": action.id, "customer_id": customer.id, "customer": customer.name,
        "amount": amount, "eligible": eligible, "limit": limit, "invoice_id": invoice_id})
    return out


class OfferError(Exception):
    def __init__(self, detail: str, status: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def approve(db: Session, action: PendingAction) -> dict[str, Any]:
    """Simulate the customer approving Postpaid; the shop is paid now. Idempotent."""
    if action.status == "confirmed":
        return {**_view(action), "already_approved": True}
    if action.status == "cancelled":
        raise OfferError("offer was cancelled")
    p = action.payload or {}
    if not p.get("eligible"):
        raise OfferError("customer is not eligible for this amount (simulated limit)")
    customer = db.get(Customer, p["customer_id"])
    amount = float(p["amount"])
    invoice_id = p.get("invoice_id")
    if invoice_id and db.get(Invoice, invoice_id) is None:
        invoice_id = None
    payment = Payment(
        invoice_id=invoice_id, customer_id=customer.id if customer else None, mode="postpaid",
        amount=amount, status="success", rail="simulated",
        order_id=f"PP-{action.id}-{secrets.token_hex(3).upper()}", paid_at=now_local())
    db.add(payment)
    action.status = "confirmed"
    action.resolved_at = now_local()
    action.result = {"simulated": True, "payment_id": None, "order_id": payment.order_id}
    db.flush()
    action.result = {"simulated": True, "payment_id": payment.id, "order_id": payment.order_id}
    name = customer.name if customer else "Customer"
    wa_msg = wa.notify(
        db, customer.phone if customer else None,
        f"Paytm Postpaid se ₹{fmt_inr(amount)} ka bhugtaan ho gaya. Dhanyavaad {name}! "
        f"Simulated: yeh sirf demo hai, asli paise nahi kate.",
        customer_id=customer.id if customer else None)
    events.publish("store", "postpaid_approved", {
        "simulated": True, "offer_id": action.id, "customer_id": p["customer_id"], "customer": p["customer"],
        "amount": amount, "invoice_id": invoice_id, "payment_id": payment.id, "order_id": payment.order_id,
        "message": f"{p['customer']} ne Postpaid se ₹{fmt_inr(amount)} diye. Paise abhi mil gaye {SIMULATED_TAG}."})
    out = _view(action)
    out["payment"] = {"id": payment.id, "mode": "postpaid", "status": "success", "amount": amount,
                      "order_id": payment.order_id, "rail": "simulated"}
    out["whatsapp"] = {"message_id": wa_msg.id, "status": wa_msg.status, "simulated": True}
    out["shop_paid_now"] = True
    return out
