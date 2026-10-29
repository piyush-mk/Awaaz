"""Invoices and the public receipt page (Phase 1, Agent A).

GET  /api/invoices, /api/invoices/{id}        schemas.InvoiceOut
POST /api/invoices/{id}/send                  WhatsApp text receipt + voice receipt
GET  /r/{token}                               public HTML receipt (mounted by `public_router`)
"""
from fastapi import APIRouter

from routers._stub import not_implemented

router = APIRouter()
public_router = APIRouter()


@router.get("")
def list_invoices():
    not_implemented("GET /api/invoices", "Agent A")


@router.get("/{invoice_id}")
def get_invoice(invoice_id: int):
    not_implemented("GET /api/invoices/{id}", "Agent A")


@router.post("/{invoice_id}/send")
def send_invoice(invoice_id: int):
    not_implemented("POST /api/invoices/{id}/send", "Agent A")


@public_router.get("/{token}")
def public_receipt(token: str):
    not_implemented("GET /r/{token}", "Agent A")
