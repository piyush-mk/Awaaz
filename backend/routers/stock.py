"""Stock views (Phase 1, Agent D). Mounted at /api/stock.

GET  /api/stock                rich list: qty, cover, status, batches, next expiry, cost, margin
GET  /api/stock/cover          days of cover per product (lowest first)
GET  /api/stock/expiry         batches expiring within N days + suggested action and claim
GET  /api/stock/missed         missed-sale leaderboard (what customers asked for, shop lacked)
POST /api/stock/missed         record a missed sale
GET  /api/stock/product/{id}   one product in detail (batches, sales series, purchases, moves)
POST /api/stock/prices         set today's price for fresh/loose goods ("ande saat rupaye")
"""
from collections import defaultdict
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import MissedSale, Product, PurchaseBill, PurchaseItem, StockBatch, StockMove, Supplier
from services import catalog, festivals, insights, stock_ops
from services.clock import day_bounds, now_local, today_local

router = APIRouter()


def _batch_view(b: StockBatch, today) -> dict:
    return {"batch_id": b.id, "batch_no": b.batch_no, "qty": round(float(b.qty), 3),
            "expiry": b.expiry.isoformat() if b.expiry else None,
            "days_to_expiry": (b.expiry - today).days if b.expiry else None,
            "cost_price": b.cost_price,
            "received_at": b.received_at.isoformat() if b.received_at else None}


def _expiry_status(days: Optional[int]) -> Optional[str]:
    if days is None:
        return None
    if days < 0:
        return "expired"
    return "soon" if days <= insights.EXPIRY_DAYS else "ok"


def _margin(price: float, cost: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    if cost is None or not price:
        return None, None
    m = round(price - cost, 2)
    return m, round(m / price * 100.0, 1)


def _rows(db: Session, today) -> list[dict]:
    stock = stock_ops.stock_map(db)
    vel = insights.velocity_map(db, today)
    last_buy = insights.last_purchase_map(db)
    suppliers = {s.id: s for s in db.query(Supplier).all()}
    batches: dict[int, list[StockBatch]] = defaultdict(list)
    for b in db.query(StockBatch).filter(StockBatch.qty > 0).order_by(
            StockBatch.expiry.is_(None), StockBatch.expiry, StockBatch.id).all():
        batches[b.product_id].append(b)
    out = []
    for p in db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all():
        qty = stock.get(p.id, 0.0)
        v = vel.get(p.id, 0.0)
        bl = [_batch_view(b, today) for b in batches.get(p.id, [])]
        days_list = [b["days_to_expiry"] for b in bl if b["days_to_expiry"] is not None]
        nxt = min(days_list) if days_list else None
        buy = last_buy.get(p.id)
        last_cost = buy["rate"] if buy else None
        cost = last_cost if last_cost is not None else p.cost_price
        margin, margin_pct = _margin(p.price, cost)
        sup = suppliers.get((buy or {}).get("supplier_id") or p.supplier_id)
        fm = festivals.product_multiplier(p.festival_tags or [], today)
        out.append({
            "product_id": p.id, "name": p.name, "name_hi": p.name_hi, "category": p.category, "unit": p.unit,
            "sell_mode": p.sell_mode, "base_unit": p.base_unit, "qty": qty, "threshold": p.threshold,
            "status": stock_ops.stock_status(qty, p.threshold or 0.0),
            "days_of_cover": insights.cover_of(qty, v), "velocity_per_day": round(v, 2),
            "price": p.price, "cost_price": p.cost_price, "last_cost_price": last_cost,
            "margin_per_unit": margin, "margin_pct": margin_pct,
            "stock_value": round(max(qty, 0.0) * float(cost or 0.0), 2),
            "batches": bl, "next_expiry": next((b["expiry"] for b in bl if b["expiry"]), None),
            "days_to_expiry": nxt, "expiry_status": _expiry_status(nxt),
            "supplier_id": sup.id if sup else None, "supplier_name": sup.name if sup else None,
            "festival_tags": p.festival_tags or [], "festival_multiplier": fm,
        })
    return out


@router.get("")
def stock_list(q: Optional[str] = None, status: Optional[str] = None, category: Optional[str] = None,
               sort: str = "id", db: Session = Depends(get_db)):
    """Rich stock list. Filters: q (name contains), status (low|medium|high), category.
    sort: id | name | cover | value | expiry | margin."""
    today = today_local()
    rows = _rows(db, today)
    if q:
        needle = q.strip().lower()
        rows = [r for r in rows if needle in r["name"].lower() or needle in (r["name_hi"] or "")]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if category:
        rows = [r for r in rows if r["category"] == category]
    keys = {
        "name": lambda r: r["name"].lower(),
        "cover": lambda r: (r["days_of_cover"] is None, r["days_of_cover"] or 0.0),
        "value": lambda r: -r["stock_value"],
        "expiry": lambda r: (r["days_to_expiry"] is None, r["days_to_expiry"] or 0),
        "margin": lambda r: -(r["margin_pct"] or -999.0),
    }
    if sort in keys:
        rows.sort(key=keys[sort])
    return {
        "items": rows, "count": len(rows),
        "summary": {"total_stock_value": round(sum(r["stock_value"] for r in rows), 2),
                    "low_count": sum(1 for r in rows if r["status"] == "low"),
                    "expiring_count": sum(1 for r in rows if r["expiry_status"] in ("soon", "expired"))},
    }


@router.get("/cover")
def cover(max_days: Optional[float] = None, db: Session = Depends(get_db)):
    """Days of cover (stock / 14-day velocity) per product, lowest first. Items nothing sold of are omitted."""
    rows = [{"product_id": r["product_id"], "name": r["name"], "name_hi": r["name_hi"], "stock": r["qty"],
             "unit": r["unit"], "days_of_cover": r["days_of_cover"], "velocity_per_day": r["velocity_per_day"],
             "status": r["status"]} for r in _rows(db, today_local()) if r["days_of_cover"] is not None]
    if max_days is not None:
        rows = [r for r in rows if r["days_of_cover"] <= max_days]
    rows.sort(key=lambda r: r["days_of_cover"])
    return {"items": rows, "count": len(rows)}


@router.get("/expiry")
def expiry(days: int = 7, db: Session = Depends(get_db)):
    """Batches expiring within `days` (and already expired), with the claim to raise."""
    items = insights.expiring_batches(db, max(0, min(days, 365)), today_local())
    for r in items:
        r["suggested_action"] = insights.expiry_action(r)
    return {"days": days, "items": items, "count": len(items),
            "total_claim": round(sum(r["claim_amount"] for r in items), 2)}


@router.get("/missed")
def missed_list(days: int = 7, limit: int = 20, db: Session = Depends(get_db)):
    """Missed-sale leaderboard for the last `days` days: count and last asked."""
    items = insights.missed_sales(db, days, limit=limit)
    for r in items:
        r["suggestion"] = (f"{r['product_name']} {r['count']} baar maanga gaya, stock mein add karein"
                           if not r["in_catalog"] else f"{r['product_name']} {r['count']} baar maanga gaya, "
                           "stock badhayein")
    return {"days": days, "items": items, "count": len(items), "total_asks": sum(r["count"] for r in items)}


class MissedIn(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=80)
    product_id: Optional[int] = None


@router.post("/missed")
def add_missed(body: MissedIn, db: Session = Depends(get_db)):
    """Record that a customer asked for something the shop did not have."""
    name = body.product_name.strip()
    pid = body.product_id
    if pid is None:
        product, _ = catalog.match_product(db, name)
        pid = product.id if product else None
    row = MissedSale(product_name=name, product_id=pid, at=now_local())
    db.add(row)
    db.commit()
    count = db.query(func.count(MissedSale.id)).filter(
        func.lower(func.trim(MissedSale.product_name)) == name.lower(),
        MissedSale.at >= now_local() - timedelta(days=7)).scalar()
    return {"id": row.id, "product_name": name, "product_id": pid, "asked_this_week": int(count)}


@router.get("/product/{product_id}")
def product_detail(product_id: int, db: Session = Depends(get_db)):
    today = today_local()
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    row = next(r for r in _rows(db, today) if r["product_id"] == product_id) if product.active else None
    if row is None:
        qty = stock_ops.current_stock(db, product_id)
        row = {"product_id": product.id, "name": product.name, "qty": qty}
    first = today - timedelta(days=29)
    moves = db.query(StockMove.at, StockMove.qty_change).filter(
        StockMove.product_id == product_id, StockMove.kind == "sale",
        StockMove.at >= day_bounds(first)[0]).all()
    per_day: dict = defaultdict(float)
    for at, q in moves:
        per_day[at.date()] += -float(q)
    series = [{"date": (first + timedelta(days=i)).isoformat(),
               "qty": round(per_day[first + timedelta(days=i)], 2)} for i in range(30)]
    recent = db.query(StockMove).filter(StockMove.product_id == product_id).order_by(
        StockMove.at.desc(), StockMove.id.desc()).limit(10).all()
    purchases = (db.query(PurchaseItem, PurchaseBill).join(PurchaseBill, PurchaseBill.id == PurchaseItem.bill_id)
                 .filter(PurchaseItem.product_id == product_id).order_by(PurchaseBill.created_at.desc()).limit(5).all())
    sup = db.get(Supplier, product.supplier_id) if product.supplier_id else None
    return {
        **row, "unit": product.unit, "mrp": product.mrp, "gst_rate": product.gst_rate,
        "sales_30d": series,
        "recent_moves": [{"at": m.at.isoformat(), "qty_change": m.qty_change, "kind": m.kind, "ref": m.ref,
                          "amount": m.amount} for m in recent],
        "purchases": [{"bill_no": b.bill_no, "date": b.bill_date.isoformat() if b.bill_date else None,
                       "qty": i.qty, "rate": i.rate, "prev_rate": i.prev_rate, "scheme": i.scheme_text,
                       "status": b.status} for i, b in purchases],
        "supplier": {"id": sup.id, "name": sup.name, "phone": sup.phone, "lead_days": sup.lead_days} if sup else None,
    }


class PriceIn(BaseModel):
    product_id: Optional[int] = None
    name: Optional[str] = None
    price: float = Field(..., gt=0)


class PricesIn(BaseModel):
    items: list[PriceIn] = Field(..., min_length=1)


@router.post("/prices")
def set_prices(body: PricesIn, db: Session = Depends(get_db)):
    """Set today's price (per sell unit; per kg/litre for loose goods)."""
    index = catalog.load_index(db)
    done, skipped = [], []
    for it in body.items:
        product = db.get(Product, it.product_id) if it.product_id else None
        if product is None and it.name:
            product, _ = index.match(it.name)
        if product is None:
            skipped.append({"name": it.name, "product_id": it.product_id, "reason": "product nahi mila"})
            continue
        old = product.price
        if product.is_loose:
            product.loose_price_per_base = it.price
        product.mrp = it.price
        done.append({"product_id": product.id, "name": product.name, "old_price": old, "new_price": it.price})
    db.commit()
    return {"updated": done, "skipped": skipped}
