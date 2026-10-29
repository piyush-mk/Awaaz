"""Invoices and the public receipt page (Agent A). HTML/text builders live in services/receipts.py.

GET  /api/invoices            list (?limit=&status=&customer_id=), newest first
GET  /api/invoices/{id}       one invoice with items and payments
POST /api/invoices/{id}/send  resend the WhatsApp text receipt + voice receipt {to?, voice?}
GET  /r/{token}               public mobile HTML receipt (mounted from `public_router`)
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Invoice
from schemas import InvoiceOut
from services import receipts

router = APIRouter()
public_router = APIRouter()


class InvoiceView(InvoiceOut):
    public_url: Optional[str] = None
    customer_name: Optional[str] = None
    payment_summary: str = ""


class SendBody(BaseModel):
    to: Optional[str] = None  # phone override; default is the invoice's customer
    voice: bool = True


def _view(inv: Invoice) -> InvoiceView:
    v = InvoiceView.model_validate(inv)
    v.public_url = receipts.receipt_url(inv)
    v.customer_name = inv.customer.name if inv.customer else None
    v.payment_summary = ", ".join(f"{receipts.MODE_LABELS.get(p.mode, p.mode)} ₹{receipts.fmt_money(p.amount)}"
                                  for p in inv.payments)
    return v


@router.get("", response_model=list[InvoiceView])
def list_invoices(limit: int = Query(20, ge=1, le=200), status: Optional[str] = None,
                  customer_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Invoice)
    if status:
        q = q.filter(Invoice.status == status)
    if customer_id:
        q = q.filter(Invoice.customer_id == customer_id)
    return [_view(i) for i in q.order_by(Invoice.id.desc()).limit(limit).all()]


@router.get("/{invoice_id}", response_model=InvoiceView)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(404, f"Invoice {invoice_id} nahi mila")
    return _view(inv)


@router.post("/{invoice_id}/send")
async def send_invoice(invoice_id: int, body: Optional[SendBody] = Body(None),
                       db: Session = Depends(get_db)):
    """Queue the receipt again. 400 if there is no phone to send to."""
    body = body or SendBody()
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(404, f"Invoice {invoice_id} nahi mila")
    msgs = await receipts.send_receipts(db, inv, to=body.to, voice=body.voice)
    if not msgs:
        raise HTTPException(400, "Customer ka phone number nahi hai; body mein 'to' dein")
    db.commit()
    return {"ok": True, "invoice_id": inv.id, "receipt_url": receipts.receipt_url(inv),
            "messages": [{"id": m.id, "type": m.type, "to": m.to, "status": m.status,
                          "media_ref": m.media_ref} for m in msgs]}


@public_router.get("/{token}", response_class=HTMLResponse)
def public_receipt(token: str, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.public_token == token).first()
    if inv is None:
        return HTMLResponse(receipts.not_found_html(), status_code=404)
    return HTMLResponse(receipts.receipt_html(db, inv),
                        headers={"Cache-Control": "private, max-age=60"})
