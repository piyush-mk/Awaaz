"""Read-only business insights computed with SQL over invoices, stock and the khata.

Used by the morning brief (`services/brief.py`), reorder drafts (`services/reorder.py`),
Ask-your-munim (`services/munim.py`), the stock views and dashboard v2. Nothing here
writes to the database. "Today" always means the store-local (IST) date, and every
function takes an optional `today` so tests and the demo can pin the date.

Conventions:
  * sales = Invoice.total of non-cancelled invoices, bucketed by Invoice.created_at;
  * velocity = units sold per day over the 14 days BEFORE today (same window as
    `stock_ops.days_of_cover`, so numbers agree everywhere);
  * margin = invoice-item total minus product cost_price x qty (both GST-inclusive).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    CashClosing, Customer, Invoice, InvoiceItem, KhataEntry, MissedSale, Payment, Product,
    PurchaseBill, PurchaseItem, StockBatch, StockMove, Supplier,
)
from services import catalog, festivals, stock_ops
from services.clock import day_bounds, now_local, today_local

CREDIT_DAYS = 7  # udhaar older than this many days counts as overdue
COVER_ALERT_DAYS = 3.0  # "items under 3 days of cover"
VELOCITY_DAYS = 14
EXPIRY_DAYS = 7

WEEKDAYS_HI = ["Somvaar", "Mangalvaar", "Budhvaar", "Guruvaar", "Shukravaar", "Shanivaar", "Ravivaar"]
_HI_NUM = {1: "ek", 2: "do", 3: "teen", 4: "chaar", 5: "paanch", 6: "chhe", 7: "saat", 8: "aath",
           9: "nau", 10: "das"}
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------


def inr(amount: float) -> str:
    """Rupee display with Indian digit grouping: 8420 -> '₹8,420', 1234567 -> '₹12,34,567'."""
    n = int(round(abs(amount)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if amount < 0 and n else "") + "₹" + s


def hindi_count(n: float) -> str:
    """2 -> 'do', 7 -> 'saat', 12 -> '12' (spoken-friendly small counts)."""
    k = int(round(n))
    return _HI_NUM.get(k, str(k))


def days_phrase(cover: float) -> str:
    """Days of cover as a spoken phrase: 2.0 -> 'sirf do din', 0.4 -> 'sirf aaj bhar'."""
    if cover < 0.75:
        return "sirf aaj bhar"
    return f"sirf {hindi_count(cover)} din"


def short_name(p: Product) -> str:
    """Spoken short name: festival tag for festival goods ('ghee'), else the name without sizes."""
    for tag in p.festival_tags or []:
        if tag.replace("_", " ") in (p.name or "").lower():
            return tag.replace("_", " ")
    words = [w for w in (p.name or "").split() if not catalog._SIZE_TOKEN.match(w.lower())
             and not (w.startswith("(") and w.endswith(")"))]
    return " ".join(words) or (p.name or "")


def fmt_mult(m: float) -> str:
    return str(int(m)) if float(m).is_integer() else f"{m:g}"


def fmt_date_short(d: date) -> str:
    return f"{d.day} {_MONTHS[d.month - 1]}"


def pct_change(new: float, old: float) -> Optional[float]:
    if not old:
        return None
    return round((new - old) / old * 100.0, 1)


# ---------------------------------------------------------------------------
# periods and sales
# ---------------------------------------------------------------------------

_PERIOD_ALIASES = {
    "today": "today", "aaj": "today", "yesterday": "yesterday", "kal": "yesterday",
    "week": "week", "hafta": "week", "hafte": "week", "this_week": "week", "7d": "week",
    "month": "month", "mahina": "month", "mahine": "month", "this_month": "month", "30d": "month",
}


def normalize_period(period: Optional[str]) -> str:
    return _PERIOD_ALIASES.get((period or "today").strip().lower(), "today")


def period_range(period: str, today: Optional[date] = None) -> tuple[date, date]:
    """Inclusive (first_day, last_day). week = last 7 days incl. today; month = 1st..today."""
    today = today or today_local()
    p = normalize_period(period)
    if p == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if p == "week":
        return today - timedelta(days=6), today
    if p == "month":
        return today.replace(day=1), today
    return today, today


def _bounds(first: date, last: date) -> tuple[datetime, datetime]:
    return day_bounds(first)[0], day_bounds(last)[1]


def sales_between(db: Session, first: date, last: date) -> tuple[float, int]:
    """(total rupees, invoice count) for non-cancelled invoices on [first, last]."""
    start, end = _bounds(first, last)
    total, count = db.query(func.coalesce(func.sum(Invoice.total), 0.0), func.count(Invoice.id)).filter(
        Invoice.status != "cancelled", Invoice.created_at >= start, Invoice.created_at < end).one()
    return round(float(total or 0.0), 2), int(count or 0)


def sales_on(db: Session, day: date) -> float:
    return sales_between(db, day, day)[0]


def daily_sales_series(db: Session, days: int = 14, today: Optional[date] = None) -> list[dict]:
    """[{date, weekday, total, invoices, partial}] oldest first, ending today (partial)."""
    today = today or today_local()
    first = today - timedelta(days=days - 1)
    start, end = _bounds(first, today)
    rows = db.query(Invoice.created_at, Invoice.total).filter(
        Invoice.status != "cancelled", Invoice.created_at >= start, Invoice.created_at < end).all()
    totals: dict[date, float] = defaultdict(float)
    counts: dict[date, int] = defaultdict(int)
    for at, total in rows:
        totals[at.date()] += float(total or 0.0)
        counts[at.date()] += 1
    out = []
    for i in range(days):
        d = first + timedelta(days=i)
        out.append({"date": d.isoformat(), "weekday": d.strftime("%a"), "total": round(totals[d], 2),
                    "invoices": counts[d], "partial": d == today})
    return out


def hourly_sales(db: Session, day: date) -> list[dict]:
    """Sales buckets by hour for one day: [{hour, total, invoices}], covering at least 6..22."""
    start, end = day_bounds(day)
    rows = db.query(Invoice.created_at, Invoice.total).filter(
        Invoice.status != "cancelled", Invoice.created_at >= start, Invoice.created_at < end).all()
    totals: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)
    for at, total in rows:
        totals[at.hour] += float(total or 0.0)
        counts[at.hour] += 1
    lo = min([6] + list(totals))
    hi = max([22] + list(totals))
    return [{"hour": h, "label": f"{h:02d}:00", "total": round(totals[h], 2), "invoices": counts[h]}
            for h in range(lo, hi + 1)]


def payment_split(db: Session, day: date) -> dict[str, float]:
    """Successful payments of a day by mode (cash/upi/khata/postpaid/card), zero-filled."""
    start, end = day_bounds(day)
    rows = db.query(Payment.mode, func.coalesce(func.sum(Payment.amount), 0.0)).filter(
        Payment.status == "success", Payment.created_at >= start, Payment.created_at < end
    ).group_by(Payment.mode).all()
    out = {m: 0.0 for m in ("cash", "upi", "khata", "postpaid", "card")}
    for mode, amt in rows:
        out[mode] = round(float(amt or 0.0), 2)
    return out


def margin_between(db: Session, first: date, last: date) -> dict[str, float]:
    """Revenue, cost and gross margin of items sold on [first, last]."""
    start, end = _bounds(first, last)
    revenue, cost = db.query(
        func.coalesce(func.sum(InvoiceItem.total), 0.0),
        func.coalesce(func.sum(InvoiceItem.qty * func.coalesce(Product.cost_price, 0.0)), 0.0),
    ).select_from(InvoiceItem).join(Invoice, Invoice.id == InvoiceItem.invoice_id).outerjoin(
        Product, Product.id == InvoiceItem.product_id).filter(
        Invoice.status != "cancelled", Invoice.created_at >= start, Invoice.created_at < end).one()
    revenue, cost = float(revenue or 0.0), float(cost or 0.0)
    margin = revenue - cost
    return {"revenue": round(revenue, 2), "cost": round(cost, 2), "margin": round(margin, 2),
            "margin_pct": round(margin / revenue * 100.0, 1) if revenue else 0.0}


def sales_summary(db: Session, period: str = "today", today: Optional[date] = None) -> dict[str, Any]:
    """Total, bill count, average bill and a comparison with the equivalent earlier period."""
    today = today or today_local()
    p = normalize_period(period)
    first, last = period_range(p, today)
    total, count = sales_between(db, first, last)
    compare = None
    if p == "yesterday":
        base_first = base_last = first - timedelta(days=7)
        label = "pichle hafte ka usi din"
    elif p in ("week", "month"):
        span = (last - first).days + 1
        base_last = first - timedelta(days=1)
        base_first = base_last - timedelta(days=span - 1)
        label = "pichle hafte" if p == "week" else "pichle mahine ke barabar din"
    else:
        base_first = base_last = None
        label = ""
    if base_first is not None:
        base_total, _ = sales_between(db, base_first, base_last)
        compare = {"label": label, "from": base_first.isoformat(), "to": base_last.isoformat(),
                   "total": base_total, "delta_pct": pct_change(total, base_total)}
    return {"period": p, "from": first.isoformat(), "to": last.isoformat(), "total": total,
            "invoices": count, "avg_bill": round(total / count, 2) if count else 0.0,
            "compare": compare}


def top_items(db: Session, period: str = "week", n: int = 5, by: str = "amount",
              today: Optional[date] = None) -> dict[str, Any]:
    """Best sellers over a period, ranked by revenue (`by='amount'`) or units (`by='qty'`)."""
    today = today or today_local()
    p = normalize_period(period)
    first, last = period_range(p, today)
    start, end = _bounds(first, last)
    order = func.sum(InvoiceItem.qty) if by == "qty" else func.sum(InvoiceItem.total)
    rows = db.query(
        InvoiceItem.product_id, InvoiceItem.name, func.max(InvoiceItem.unit),
        func.sum(InvoiceItem.qty), func.sum(InvoiceItem.total),
    ).join(Invoice, Invoice.id == InvoiceItem.invoice_id).filter(
        Invoice.status != "cancelled", Invoice.created_at >= start, Invoice.created_at < end,
    ).group_by(InvoiceItem.product_id, InvoiceItem.name).order_by(order.desc()).limit(max(1, min(n, 20))).all()
    items = [{"product_id": pid, "name": name, "unit": unit or "", "qty": round(float(q), 2),
              "amount": round(float(a), 2)} for pid, name, unit, q, a in rows]
    return {"period": p, "from": first.isoformat(), "to": last.isoformat(), "by": by, "items": items}


# ---------------------------------------------------------------------------
# stock: velocity, cover, expiry
# ---------------------------------------------------------------------------


def velocity_map(db: Session, today: Optional[date] = None, days: int = VELOCITY_DAYS) -> dict[int, float]:
    """{product_id: units sold per day} over the `days` days before today."""
    today = today or today_local()
    end = datetime(today.year, today.month, today.day)
    start = end - timedelta(days=days)
    rows = db.query(StockMove.product_id, func.coalesce(func.sum(-StockMove.qty_change), 0.0)).filter(
        StockMove.kind == "sale", StockMove.at >= start, StockMove.at < end).group_by(
        StockMove.product_id).all()
    return {int(pid): float(q) / days for pid, q in rows}


def cover_of(stock: float, velocity: float) -> Optional[float]:
    if velocity <= 0:
        return None
    return round(max(stock, 0.0) / velocity, 1)


def low_cover(db: Session, today: Optional[date] = None, max_days: float = COVER_ALERT_DAYS,
              ) -> list[dict[str, Any]]:
    """Active products that will run out within `max_days` at the 14-day velocity."""
    today = today or today_local()
    stock = stock_ops.stock_map(db)
    vel = velocity_map(db, today)
    out = []
    for p in db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all():
        v = vel.get(p.id, 0.0)
        cover = cover_of(stock.get(p.id, 0.0), v)
        if cover is not None and cover < max_days:
            out.append({"product_id": p.id, "name": p.name, "name_hi": p.name_hi, "short_name": short_name(p),
                        "stock": stock.get(p.id, 0.0), "unit": p.unit, "cover_days": cover,
                        "velocity_per_day": round(v, 2)})
    out.sort(key=lambda r: (r["cover_days"], r["product_id"]))
    return out


def _supplier_names(db: Session) -> dict[int, Supplier]:
    return {s.id: s for s in db.query(Supplier).all()}


def expiring_batches(db: Session, days: int = EXPIRY_DAYS, today: Optional[date] = None
                     ) -> list[dict[str, Any]]:
    """Batches with stock that expire within `days` (or already expired), soonest first.
    `claim_amount` = cost price x qty, the value to claim back from the distributor."""
    today = today or today_local()
    horizon = today + timedelta(days=days)
    suppliers = _supplier_names(db)
    rows = (db.query(StockBatch, Product).join(Product, Product.id == StockBatch.product_id)
            .filter(StockBatch.qty > 0, StockBatch.expiry.isnot(None), StockBatch.expiry <= horizon)
            .order_by(StockBatch.expiry, StockBatch.id).all())
    out = []
    for b, p in rows:
        cost = float(b.cost_price if b.cost_price is not None else (p.cost_price or 0.0))
        sup = suppliers.get(b.supplier_id or p.supplier_id)
        days_left = (b.expiry - today).days
        claim = round(cost * float(b.qty), 2)
        out.append({
            "product_id": p.id, "name": p.name, "name_hi": p.name_hi, "short_name": short_name(p),
            "category": p.category, "batch_id": b.id, "batch_no": b.batch_no, "qty": round(float(b.qty), 3),
            "unit": p.unit, "expiry": b.expiry.isoformat(), "days_left": days_left,
            "expired": days_left < 0, "cost_price": cost, "claim_amount": claim,
            "supplier_id": sup.id if sup else None, "supplier_name": sup.name if sup else None,
            "supplier_phone": sup.phone if sup else None,
        })
    return out


def expiry_action(row: dict[str, Any]) -> str:
    """One-line Hinglish suggestion for an expiring batch."""
    claim = inr(row["claim_amount"])
    who = row.get("supplier_name") or "distributor"
    if row["days_left"] < 0:
        return f"Expire ho chuka: shelf se hatayein, {who} ko wapas karein: {claim} ka claim"
    if row["category"] == "fresh" and row["days_left"] <= 2:
        return f"Aaj hi discount par bechein; bacha toh {who} ko wapas karein: {claim} ka claim"
    return f"{who} ko wapas karein: {claim} ka claim"


# ---------------------------------------------------------------------------
# udhaar
# ---------------------------------------------------------------------------


def _oldest_unpaid(entries: list[KhataEntry]) -> Optional[datetime]:
    """FIFO: payments clear the oldest credits first; returns the date of the oldest credit
    that is still (partly) unpaid, or None when nothing is owed."""
    credits: list[list] = []
    for e in sorted(entries, key=lambda x: (x.at or datetime.min, x.id or 0)):
        if e.amount > 0:
            credits.append([e.at, float(e.amount)])
        else:
            pay = -float(e.amount)
            for c in credits:
                if pay <= 1e-9:
                    break
                use = min(c[1], pay)
                c[1] -= use
                pay -= use
    for at, left in credits:
        if left > 1e-9:
            return at
    return None


def udhaar_summary(db: Session, today: Optional[date] = None, top: int = 5) -> dict[str, Any]:
    """Outstanding credit: total, per-customer balances, who is due today / overdue."""
    today = today or today_local()
    owing = (db.query(Customer.id, Customer.name, Customer.name_hi, Customer.late_payments,
                      Customer.credit_limit, func.sum(KhataEntry.amount).label("bal"))
             .join(KhataEntry, KhataEntry.customer_id == Customer.id)
             .group_by(Customer.id).having(func.sum(KhataEntry.amount) > 0.5)
             .order_by(func.sum(KhataEntry.amount).desc()).all())
    entries_by_cust: dict[int, list[KhataEntry]] = defaultdict(list)
    if owing:
        for e in db.query(KhataEntry).filter(KhataEntry.customer_id.in_([r.id for r in owing])).all():
            entries_by_cust[e.customer_id].append(e)
    rows = []
    for r in owing:
        oldest = _oldest_unpaid(entries_by_cust[r.id])
        age = (today - oldest.date()).days if oldest else 0
        rows.append({"customer_id": r.id, "name": r.name, "name_hi": r.name_hi,
                     "balance": round(float(r.bal), 2), "late_payments": int(r.late_payments or 0),
                     "credit_limit": float(r.credit_limit or 0.0), "days_outstanding": age,
                     "oldest_credit": oldest.date().isoformat() if oldest else None})
    overdue = sorted([r for r in rows if r["days_outstanding"] > CREDIT_DAYS],
                     key=lambda r: -r["balance"])
    due_today = [r for r in rows if r["days_outstanding"] == CREDIT_DAYS]
    return {"total_outstanding": round(sum(r["balance"] for r in rows), 2),
            "customers_with_balance": len(rows), "credit_days": CREDIT_DAYS,
            "due_today": due_today, "overdue": overdue, "top": rows[:top], "all": rows}


def who_owes(db: Session, n: int = 5, customer: Optional[str] = None, today: Optional[date] = None
             ) -> dict[str, Any]:
    """Top debtors, or one customer's balance when `customer` (spoken name) is given."""
    summary = udhaar_summary(db, today)
    if customer:
        match, _score = catalog.match_customer(db, customer, threshold=80)
        if match is None:
            return {"customer_query": customer, "found": False, "customers": [],
                    "total_outstanding": summary["total_outstanding"]}
        row = next((r for r in summary["all"] if r["customer_id"] == match.id), None)
        if row is None:
            row = {"customer_id": match.id, "name": match.name, "name_hi": match.name_hi,
                   "balance": 0.0, "late_payments": int(match.late_payments or 0),
                   "credit_limit": float(match.credit_limit or 0.0), "days_outstanding": 0,
                   "oldest_credit": None}
        return {"customer_query": customer, "found": True, "customers": [row],
                "total_outstanding": summary["total_outstanding"]}
    return {"customer_query": None, "found": True, "customers": summary["all"][:max(1, min(n, 50))],
            "total_outstanding": summary["total_outstanding"],
            "customers_with_balance": summary["customers_with_balance"]}


def udhaar_total(db: Session, today: Optional[date] = None) -> dict[str, Any]:
    s = udhaar_summary(db, today)
    return {"total_outstanding": s["total_outstanding"], "customers_with_balance": s["customers_with_balance"],
            "overdue_count": len(s["overdue"]), "overdue_amount": round(sum(r["balance"] for r in s["overdue"]), 2),
            "credit_days": s["credit_days"]}


# ---------------------------------------------------------------------------
# missed sales, cash gap, festival
# ---------------------------------------------------------------------------


def missed_sales(db: Session, days: int = 7, now: Optional[datetime] = None, limit: int = 20
                 ) -> list[dict[str, Any]]:
    """Missed-sale leaderboard: what customers asked for and the shop did not have."""
    now = now or now_local()
    since = now - timedelta(days=days)
    rows = (db.query(func.lower(func.trim(MissedSale.product_name)), func.max(MissedSale.product_name),
                     func.count(MissedSale.id), func.max(MissedSale.at), func.max(MissedSale.product_id))
            .filter(MissedSale.at >= since).group_by(func.lower(func.trim(MissedSale.product_name)))
            .order_by(func.count(MissedSale.id).desc(), func.max(MissedSale.at).desc()).limit(limit).all())
    index = catalog.load_index(db)
    out = []
    for _key, name, count, last, pid in rows:
        product, _ = index.match(name)
        out.append({"product_name": name, "count": int(count), "last_asked": last.isoformat() if last else None,
                    "product_id": pid or (product.id if product else None),
                    "in_catalog": bool(pid or product)})
    return out


def cash_gap(db: Session, day: Optional[date] = None) -> Optional[dict[str, Any]]:
    """Galla closing of `day`, or the most recent closing when day is None."""
    q = db.query(CashClosing)
    if day is not None:
        q = q.filter(CashClosing.day == day)
    c = q.order_by(CashClosing.day.desc(), CashClosing.id.desc()).first()
    if c is None:
        return None
    diff = round(float(c.diff or 0.0), 2)
    return {"day": c.day.isoformat(), "expected": round(float(c.expected or 0.0), 2),
            "counted": round(float(c.counted or 0.0), 2), "diff": diff,
            "status": "theek" if abs(diff) < 0.5 else ("kam" if diff < 0 else "zyada")}


def festival_block(db: Session, today: Optional[date] = None, stock: Optional[dict[int, float]] = None,
                   vel: Optional[dict[int, float]] = None) -> Optional[dict[str, Any]]:
    """Next festival with the demand multipliers and which tagged products will run out first.

    A product is `at_risk` when its cover divided by the festival multiplier is shorter
    than the days left, i.e. it sells out before the festival at festival-rate demand."""
    today = today or today_local()
    fest = festivals.next_festival(today)
    if fest is None:
        return None
    stock = stock if stock is not None else stock_ops.stock_map(db)
    vel = vel if vel is not None else velocity_map(db, today)
    days_away = int(fest["days_away"])
    products = []
    for p in db.query(Product).filter(Product.active.is_(True)).all():
        mult = festivals.multiplier(p.festival_tags or [], fest)
        if mult <= 1.0:
            continue
        cover = cover_of(stock.get(p.id, 0.0), vel.get(p.id, 0.0))
        adjusted = round(cover / mult, 1) if cover is not None else None
        products.append({"product_id": p.id, "name": p.name, "name_hi": p.name_hi, "short_name": short_name(p),
                         "stock": stock.get(p.id, 0.0), "unit": p.unit, "multiplier": mult,
                         "cover_days": cover, "festival_cover_days": adjusted,
                         "at_risk": adjusted is not None and adjusted < days_away})
    products.sort(key=lambda r: (r["cover_days"] is None, r["cover_days"] or 0.0, -r["multiplier"]))
    tag_mults: dict[str, float] = {}
    for p in db.query(Product).filter(Product.active.is_(True)).all():
        for t in p.festival_tags or []:
            if t in fest.get("multipliers", {}):
                tag_mults[t] = float(fest["multipliers"][t])
    return {
        "name": fest["name"], "date": fest["date"].isoformat(), "date_short": fmt_date_short(fest["date"]),
        "days_away": days_away, "lead_days": int(fest.get("lead_days", 10)),
        "active": days_away <= int(fest.get("lead_days", 10)),
        "multipliers": [{"tag": t, "multiplier": m} for t, m in
                        sorted(tag_mults.items(), key=lambda kv: -kv[1])],
        "products": products, "at_risk": [r for r in products if r["at_risk"]],
        "last_year_note": (fest.get("last_year") or {}).get("note", ""),
    }


# ---------------------------------------------------------------------------
# supplier / price lookups
# ---------------------------------------------------------------------------


def last_purchase_map(db: Session) -> dict[int, dict[str, Any]]:
    """{product_id: {supplier_id, rate, at}} from the most recent confirmed PurchaseItem."""
    rows = (db.query(PurchaseItem.product_id, PurchaseItem.rate, PurchaseBill.supplier_id,
                     PurchaseBill.created_at, PurchaseItem.id)
            .join(PurchaseBill, PurchaseBill.id == PurchaseItem.bill_id)
            .filter(PurchaseItem.product_id.isnot(None), PurchaseBill.status == "confirmed")
            .order_by(PurchaseBill.created_at, PurchaseItem.id).all())
    out: dict[int, dict[str, Any]] = {}
    for pid, rate, sid, at, _iid in rows:  # later rows overwrite earlier ones
        out[int(pid)] = {"supplier_id": sid, "rate": float(rate or 0.0), "at": at}
    return out


# ---------------------------------------------------------------------------
# the morning-brief fact sheet
# ---------------------------------------------------------------------------


def build_facts(db: Session, today: Optional[date] = None) -> dict[str, Any]:
    """Everything the morning brief may say, as plain JSON-able facts. The LLM is allowed
    to use ONLY numbers that appear in here."""
    today = today or today_local()
    yesterday = today - timedelta(days=1)
    week_ago = yesterday - timedelta(days=7)
    y_total, y_count = sales_between(db, yesterday, yesterday)
    w_total, _ = sales_between(db, week_ago, week_ago)
    delta = pct_change(y_total, w_total)

    stock = stock_ops.stock_map(db)
    vel = velocity_map(db, today)
    udhaar = udhaar_summary(db, today)
    top = top_items(db, "yesterday", 3, "amount", today)["items"]
    expiring = expiring_batches(db, EXPIRY_DAYS, today)
    missed = missed_sales(db, 7)
    gap = cash_gap(db, yesterday)
    fest = festival_block(db, today, stock, vel)
    if fest:
        fest = {**fest, "products": fest["products"][:6]}

    return {
        "date": today.isoformat(), "weekday": WEEKDAYS_HI[today.weekday()],
        "yesterday": {
            "date": yesterday.isoformat(), "weekday": WEEKDAYS_HI[yesterday.weekday()],
            "total": y_total, "invoices": y_count,
            "same_weekday_last_week": {"date": week_ago.isoformat(), "total": w_total},
            "delta_pct": delta, "delta_amount": round(y_total - w_total, 2),
        },
        "top_items": top,
        "low_cover": low_cover(db, today)[:6],
        "expiring": [{k: r[k] for k in ("product_id", "name", "short_name", "batch_no", "qty", "unit",
                                        "expiry", "days_left", "claim_amount")} for r in expiring[:5]],
        "udhaar": {
            "total_outstanding": udhaar["total_outstanding"],
            "customers_with_balance": udhaar["customers_with_balance"],
            "due_today": [{k: r[k] for k in ("name", "balance")} for r in udhaar["due_today"][:3]],
            "overdue": [{k: r[k] for k in ("customer_id", "name", "balance", "days_outstanding",
                                           "late_payments")} for r in udhaar["overdue"][:3]],
            "credit_days": udhaar["credit_days"],
        },
        "missed_sales": missed[:3],
        "festival": fest if fest and fest["active"] else None,
        "next_festival": ({"name": fest["name"], "date": fest["date"], "days_away": fest["days_away"]}
                          if fest else None),
        "cash_gap": gap if gap and abs(gap["diff"]) >= 0.5 else None,
    }
