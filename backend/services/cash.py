"""Galla (cash drawer) arithmetic."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Payment, StoreProfile
from services.clock import day_bounds, today_local


def cash_received(db: Session, day: Optional[date] = None) -> float:
    """Cash payments (net of refunds) taken on a local day."""
    start, end = day_bounds(day or today_local())
    base = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
        Payment.mode == "cash", Payment.created_at >= start, Payment.created_at < end)
    got = base.filter(Payment.status == "success").scalar() or 0.0
    refunded = base.filter(Payment.status == "refunded").scalar() or 0.0
    return round(float(got) - float(refunded), 2)


def expected_cash(db: Session, day: Optional[date] = None) -> float:
    """Opening float + cash payments - cash refunds for the day."""
    store = db.query(StoreProfile).first()
    opening = float(store.opening_float or 0.0) if store else 0.0
    return round(opening + cash_received(db, day), 2)
