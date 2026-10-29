"""Payments (Agent A). Rails and settlement logic live in services/payments.py.

GET  /api/payments/{order_id}            status of a payment + its invoice
POST /api/payments/{order_id}/simulate   "payment aa gaya": app button / Soundbox key. Idempotent.
POST /api/payments/webhook               generic provider callback (same as /webhooks/payments)
POST /webhooks/payments                  mounted from `webhook_router` (needs a main.py include)
"""
import os
from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Payment
from services import payments as svc

router = APIRouter()
webhook_router = APIRouter()


@router.get("/{order_id}")
def get_payment(order_id: str, db: Session = Depends(get_db)):
    """{order_id, status: pending|success|failed, mode, amount, rail, paid_at, invoice{...},
    payments[], invoice_paid}"""
    payment = db.query(Payment).filter(Payment.order_id == order_id).first()
    if payment is None:
        raise HTTPException(404, f"Order {order_id} nahi mila")
    return svc.payment_view(payment)


@router.post("/{order_id}/simulate")
async def simulate_payment(order_id: str, db: Session = Depends(get_db)):
    """Mark the payment successful: invoice paid, stock deducted FIFO, `payment_received` published
    on the store channel, WhatsApp text + voice receipt queued. A second call is a no-op
    (`already_paid: true`)."""
    return await svc.settle(db, order_id, via="simulate")


async def _callback(payload: dict, secret: Optional[str], db: Session) -> dict:
    expected = os.environ.get("AWAAZ_WEBHOOK_SECRET", "")
    if expected and secret != expected:
        raise HTTPException(401, "bad webhook secret")
    info = svc.parse_callback(payload)
    if not info["order_id"]:
        raise HTTPException(422, "order_id missing")
    if info["state"] == "success":
        return await svc.settle(db, str(info["order_id"]), via="webhook", amount=info["amount"])
    if info["state"] == "failed":
        return await svc.fail(db, str(info["order_id"]), "webhook")
    return {"ok": True, "ignored": "status not final", "order_id": info["order_id"]}


@router.post("/webhook")
async def webhook(payload: dict = Body(...), x_webhook_secret: Optional[str] = Header(None),
                  db: Session = Depends(get_db)):
    """Generic callback: {order_id, status: SUCCESS|TXN_SUCCESS|PAID|..., amount?, txn_id?}. Paytm-style
    keys (ORDERID, STATUS, TXNAMOUNT, optionally nested under 'body') are understood. If the
    AWAAZ_WEBHOOK_SECRET env var is set, header X-Webhook-Secret must match."""
    return await _callback(payload, x_webhook_secret, db)


@webhook_router.post("")
async def webhook_root(payload: dict = Body(...), x_webhook_secret: Optional[str] = Header(None),
                       db: Session = Depends(get_db)):
    return await _callback(payload, x_webhook_secret, db)
