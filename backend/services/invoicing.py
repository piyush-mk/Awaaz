"""Create invoices from cart lines (GST-correct, numbered, with a public token).

Shared by the legacy /api/bill/confirm flow and the Phase 1 checkout flow.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from models import Invoice, InvoiceItem, Product, StoreProfile
from schemas import CartLine
from services import pricing
from services.clock import now_local
from services.stock_ops import deduct_fifo


def get_store(db: Session) -> StoreProfile:
    """The single StoreProfile row (created with defaults if the DB is empty)."""
    store = db.query(StoreProfile).first()
    if store is None:
        store = StoreProfile(name="Ramesh General Store", invoice_prefix="RGS")
        db.add(store)
        db.flush()
    return store


def next_invoice_number(db: Session, store: StoreProfile, at: Optional[datetime] = None) -> str:
    """Next number in the store's series for the financial year of `at`."""
    at = at or now_local()
    prefix = store.invoice_prefix or "INV"
    fy = pricing.financial_year(at.date())
    last = (
        db.query(Invoice.number).filter(Invoice.number.like(f"{prefix}/{fy}/%"))
        .order_by(Invoice.number.desc()).first()
    )
    seq = pricing.parse_sequence(last[0]) + 1 if last else 1
    return pricing.invoice_number(prefix, at.date(), seq)


def create_invoice(db: Session, lines: Iterable[CartLine], *, customer_id: Optional[int] = None,
                   status: str = "pending", cart_id: Optional[str] = None,
                   at: Optional[datetime] = None, number: Optional[str] = None,
                   note: Optional[str] = None) -> Invoice:
    """Build and add an Invoice with priced items (flushes, does not commit).
    Amount-based lines (`amount_rupees` set) are billed exactly that amount."""
    at = at or now_local()
    store = get_store(db)
    composition = bool(store.composition_scheme)
    priced = []
    items: list[InvoiceItem] = []
    for ln in lines:
        product = db.get(Product, ln.product_id) if ln.product_id else None
        override = ln.amount_rupees if ln.amount_rupees is not None else None
        lt = pricing.price_line(ln.qty, ln.unit_price, ln.gst_rate, composition, override)
        priced.append(lt)
        items.append(InvoiceItem(
            product_id=ln.product_id, name=ln.name, name_hi=ln.name_hi, qty=ln.qty, unit=ln.unit,
            mrp=ln.unit_price, gst_rate=lt.gst_rate, hsn=product.hsn if product else None,
            taxable=lt.taxable, cgst=lt.cgst, sgst=lt.sgst, total=lt.total,
        ))
    totals = pricing.totals_for_lines(priced, composition)
    inv = Invoice(
        number=number or next_invoice_number(db, store, at), doc_type=totals.doc_type,
        customer_id=customer_id, status=status, taxable_total=totals.taxable,
        cgst_total=totals.cgst, sgst_total=totals.sgst, total=totals.total,
        public_token=secrets.token_urlsafe(8), cart_id=cart_id, note=note, created_at=at,
        paid_at=at if status == "paid" else None, items=items,
    )
    db.add(inv)
    db.flush()
    return inv


def deduct_invoice_stock(db: Session, invoice: Invoice, allow_negative: bool = True,
                         at: Optional[datetime] = None) -> list[dict]:
    """FIFO-deduct every catalogued item of an invoice. Returns per-product stock info."""
    from services.stock_ops import current_stock

    out = []
    for it in invoice.items:
        if not it.product_id:
            continue
        before = current_stock(db, it.product_id)
        deduct_fifo(db, it.product_id, it.qty, ref=f"invoice:{invoice.id}", amount=it.total,
                    allow_negative=allow_negative, at=at)
        out.append({"product_id": it.product_id, "name": it.name, "name_hi": it.name_hi,
                    "old_quantity": before, "new_quantity": round(before - it.qty, 3),
                    "unit": it.unit})
    return out
