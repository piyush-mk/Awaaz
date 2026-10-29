"""Legacy dashboard API (shapes unchanged). Numbers now come from the seeded history:
there is no fake offset; today's sales are the sum of today's invoices."""
from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Invoice, InvoiceItem, Product, StockMove
from schemas import DashboardStats, TransactionOut
from services import insights, stock_ops
from services.clock import day_bounds, now_local, today_local

router = APIRouter()


def _low_stock(db: Session) -> list[dict]:
    stock = stock_ops.stock_map(db)
    out = []
    for p in db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all():
        qty = stock.get(p.id, 0.0)
        if qty <= (p.threshold or 0.0):
            out.append({"product_id": p.id, "name": p.name, "name_hi": p.name_hi, "quantity": qty,
                        "threshold": p.threshold, "unit": p.unit})
    return out


def _transactions(db: Session, limit: int) -> list[TransactionOut]:
    rows = (db.query(StockMove, Product).join(Product, Product.id == StockMove.product_id)
            .filter(StockMove.at <= now_local()).order_by(StockMove.at.desc(), StockMove.id.desc())
            .limit(limit).all())
    return [TransactionOut(id=m.id, product_id=m.product_id, product_name=p.name,
                           product_name_hi=p.name_hi or "", quantity_change=m.qty_change, type=m.kind,
                           amount=m.amount or 0.0, timestamp=m.at) for m, p in rows]


@router.get("/dashboard", response_model=DashboardStats)
def get_dashboard(db: Session = Depends(get_db)):
    stock = stock_ops.stock_map(db)
    products = db.query(Product).filter(Product.active.is_(True)).all()
    total_stock_value = sum(max(stock.get(p.id, 0.0), 0.0) * float(p.cost_price or p.price)
                            for p in products)

    start, end = day_bounds(today_local())
    today_sales = db.query(func.coalesce(func.sum(Invoice.total), 0.0)).filter(
        Invoice.status != "cancelled", Invoice.created_at >= start, Invoice.created_at < end).scalar()

    week_ago = now_local() - timedelta(days=7)
    top_raw = (
        db.query(InvoiceItem.product_id, func.sum(InvoiceItem.qty).label("qty"),
                 func.sum(InvoiceItem.total).label("amount"))
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .filter(Invoice.status != "cancelled", Invoice.created_at >= week_ago,
                InvoiceItem.product_id.isnot(None))
        .group_by(InvoiceItem.product_id).order_by(func.sum(InvoiceItem.total).desc()).limit(5).all()
    )
    top_selling = []
    for row in top_raw:
        product = db.get(Product, row.product_id)
        if product:
            top_selling.append({"product_id": row.product_id, "name": product.name,
                                "name_hi": product.name_hi, "total_qty": round(float(row.qty), 2),
                                "total_amount": round(float(row.amount), 2)})

    return DashboardStats(
        total_stock_value=round(total_stock_value, 2), today_sales=round(float(today_sales), 2),
        low_stock_count=len(_low_stock(db)), top_selling=top_selling,
        recent_transactions=_transactions(db, 20))


@router.get("/alerts")
def get_alerts(db: Session = Depends(get_db)):
    alerts = [{**a, "severity": "critical" if a["quantity"] <= 0 else "low"} for a in _low_stock(db)]
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/transactions", response_model=List[TransactionOut])
def get_transactions(limit: int = 20, db: Session = Depends(get_db)):
    return _transactions(db, limit)


@router.get("/dashboard/v2")
def get_dashboard_v2(db: Session = Depends(get_db)):
    """Richer dashboard: today vs yesterday, hourly buckets, payment-mode split, margin, top items,
    udhaar, low stock and a 14-day sales series (oldest first, ending today)."""
    today = today_local()
    yesterday = today - timedelta(days=1)
    t_total, t_count = insights.sales_between(db, today, today)
    y_total, y_count = insights.sales_between(db, yesterday, yesterday)
    w_total = insights.sales_on(db, yesterday - timedelta(days=7))
    split = insights.payment_split(db, today)
    split_sum = sum(split.values())
    stock = stock_ops.stock_map(db)
    products = db.query(Product).filter(Product.active.is_(True)).all()
    stock_value = sum(max(stock.get(p.id, 0.0), 0.0) * float(p.cost_price or p.price) for p in products)
    udhaar = insights.udhaar_summary(db, today)
    return {
        "date": today.isoformat(), "generated_at": now_local().isoformat(timespec="seconds"),
        "today": {"sales": t_total, "invoices": t_count,
                  "avg_bill": round(t_total / t_count, 2) if t_count else 0.0,
                  **{k: v for k, v in insights.margin_between(db, today, today).items()
                     if k in ("margin", "margin_pct")}},
        "yesterday": {"sales": y_total, "invoices": y_count,
                      "vs_last_week_pct": insights.pct_change(y_total, w_total),
                      **{k: v for k, v in insights.margin_between(db, yesterday, yesterday).items()
                         if k in ("margin", "margin_pct")}},
        "hourly": insights.hourly_sales(db, today),
        "payment_split": split,
        "payment_split_pct": {m: (round(a / split_sum * 100.0, 1) if split_sum else 0.0)
                              for m, a in split.items()},
        "margin": insights.margin_between(db, today, today),
        "top_items": insights.top_items(db, "today", 5, "amount", today)["items"],
        "top_items_week": insights.top_items(db, "week", 5, "amount", today)["items"],
        "udhaar": {"total_outstanding": udhaar["total_outstanding"],
                   "customers_with_balance": udhaar["customers_with_balance"],
                   "overdue_count": len(udhaar["overdue"]), "top": udhaar["top"]},
        "low_stock_count": len(_low_stock(db)),
        "total_stock_value": round(stock_value, 2),
        "series": insights.daily_sales_series(db, 14, today),
    }
