"""Khata (udhaar) ledger helpers shared by billing and the khata router.

Sign convention (see models.KhataEntry): amount > 0 is credit given, amount < 0 is a payment received.
Contract (stable; Agent B owns the internals and may extend, never change signatures). None of these
commit; the caller owns the transaction.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import KhataEntry


def balance(db: Session, customer_id: int) -> float:
    """What the customer owes right now (positive means they owe the shop)."""
    total = db.query(func.coalesce(func.sum(KhataEntry.amount), 0.0)).filter(
        KhataEntry.customer_id == customer_id
    ).scalar()
    return round(float(total or 0.0), 2)


def add_credit(
    db: Session,
    customer_id: int,
    amount: float,
    invoice_id: Optional[int] = None,
    note: Optional[str] = None,
) -> KhataEntry:
    """Record udhaar given to a customer."""
    entry = KhataEntry(customer_id=customer_id, amount=abs(float(amount)), invoice_id=invoice_id, note=note)
    db.add(entry)
    db.flush()
    return entry


def record_payment(
    db: Session,
    customer_id: int,
    amount: float,
    invoice_id: Optional[int] = None,
    note: Optional[str] = None,
) -> KhataEntry:
    """Record money received against a customer's khata."""
    entry = KhataEntry(customer_id=customer_id, amount=-abs(float(amount)), invoice_id=invoice_id, note=note)
    db.add(entry)
    db.flush()
    return entry
