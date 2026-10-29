"""Stock arithmetic over `StockBatch` (current stock) and `StockMove` (ledger).

Stock of a product is the sum of its batch quantities. Sales deduct FIFO by
expiry (first-expiring-first-out), then by receipt time. Every change also
writes a StockMove so the legacy transaction feed and velocity maths work.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Product, StockBatch, StockMove
from services.clock import now_local


class InsufficientStock(Exception):
    def __init__(self, product: Product, available: float, requested: float):
        super().__init__(f"{product.name}: {available:g} available, {requested:g} requested")
        self.product = product
        self.available = available
        self.requested = requested


def current_stock(db: Session, product_id: int) -> float:
    total = db.query(func.coalesce(func.sum(StockBatch.qty), 0.0)).filter(
        StockBatch.product_id == product_id).scalar()
    return round(float(total or 0.0), 3)


def stock_map(db: Session) -> dict[int, float]:
    """{product_id: stock} for every product with at least one batch."""
    rows = db.query(StockBatch.product_id, func.coalesce(func.sum(StockBatch.qty), 0.0)).group_by(
        StockBatch.product_id).all()
    return {int(pid): round(float(q), 3) for pid, q in rows}


def add_stock(db: Session, product_id: int, qty: float, *, batch_no: Optional[str] = None,
              expiry: Optional[date] = None, cost_price: Optional[float] = None,
              supplier_id: Optional[int] = None, kind: str = "restock", ref: Optional[str] = None,
              note: Optional[str] = None, at: Optional[datetime] = None) -> StockBatch:
    """Receive stock as a new batch and log the move."""
    at = at or now_local()
    batch = StockBatch(product_id=product_id, qty=qty, batch_no=batch_no, expiry=expiry,
                       cost_price=cost_price, supplier_id=supplier_id, received_at=at)
    db.add(batch)
    db.add(StockMove(product_id=product_id, qty_change=qty, kind=kind, ref=ref, note=note, at=at))
    return batch


def deduct_fifo(db: Session, product_id: int, qty: float, *, ref: Optional[str] = None,
                kind: str = "sale", amount: float = 0.0, allow_negative: bool = False,
                at: Optional[datetime] = None) -> list[tuple[int, float]]:
    """Take `qty` from batches, earliest expiry first. Returns [(batch_id, qty_taken)].
    Raises InsufficientStock unless allow_negative (then the newest batch goes negative)."""
    at = at or now_local()
    product = db.get(Product, product_id)
    batches = (
        db.query(StockBatch).filter(StockBatch.product_id == product_id, StockBatch.qty > 0)
        .order_by(StockBatch.expiry.is_(None), StockBatch.expiry, StockBatch.received_at, StockBatch.id)
        .all()
    )
    available = sum(b.qty for b in batches)
    if available + 1e-9 < qty and not allow_negative:
        raise InsufficientStock(product, available, qty)
    remaining = qty
    taken: list[tuple[int, float]] = []
    for b in batches:
        if remaining <= 1e-9:
            break
        use = min(b.qty, remaining)
        b.qty = round(b.qty - use, 6)
        remaining -= use
        taken.append((int(b.id), use))
    if remaining > 1e-9:  # oversell: record on the newest batch (or a fresh one)
        last = batches[-1] if batches else StockBatch(product_id=product_id, qty=0.0, received_at=at)
        if not batches:
            db.add(last)
            db.flush()
        last.qty = round(last.qty - remaining, 6)
        taken.append((int(last.id), remaining))
    db.add(StockMove(product_id=product_id, qty_change=-qty, kind=kind, ref=ref, amount=amount, at=at))
    return taken


def set_stock(db: Session, product_id: int, target: float, *, kind: str = "adjust",
              note: Optional[str] = None) -> float:
    """Force stock to `target`; returns the change applied."""
    diff = round(target - current_stock(db, product_id), 6)
    if diff > 0:
        add_stock(db, product_id, diff, kind=kind, note=note)
    elif diff < 0:
        deduct_fifo(db, product_id, -diff, kind=kind, allow_negative=True)
        db.flush()  # autoflush is off: make the new StockMove visible to the query below
        db.query(StockMove).filter(StockMove.product_id == product_id).order_by(
            StockMove.id.desc()).first().note = note
    return diff


def sold_qty(db: Session, product_id: int, days: int = 14, today: Optional[date] = None) -> float:
    """Units sold in the `days` calendar days before `today` (excludes today)."""
    today = today or now_local().date()
    start = datetime(today.year, today.month, today.day) - timedelta(days=days)
    end = datetime(today.year, today.month, today.day)
    total = db.query(func.coalesce(func.sum(-StockMove.qty_change), 0.0)).filter(
        StockMove.product_id == product_id, StockMove.kind == "sale",
        StockMove.at >= start, StockMove.at < end).scalar()
    return float(total or 0.0)


def velocity(db: Session, product_id: int, days: int = 14, today: Optional[date] = None) -> float:
    """Average units sold per day over the last `days` days."""
    return sold_qty(db, product_id, days, today) / float(days)


def days_of_cover(db: Session, product_id: int, days: int = 14, today: Optional[date] = None
                  ) -> Optional[float]:
    """Stock / 14-day velocity; None when nothing sold recently."""
    v = velocity(db, product_id, days, today)
    if v <= 0:
        return None
    return round(max(current_stock(db, product_id), 0.0) / v, 1)


def stock_status(quantity: float, threshold: float) -> str:
    """'low' <= threshold < 'medium' <= 2 x threshold < 'high' (legacy semantics)."""
    if quantity <= threshold:
        return "low"
    if quantity <= threshold * 2:
        return "medium"
    return "high"
