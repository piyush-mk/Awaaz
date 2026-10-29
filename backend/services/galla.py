"""Galla (cash drawer) closing helpers (F7): expected-cash breakdown, denomination table,
low-confidence flags and the spoken Hinglish difference message."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Payment, StoreProfile
from services import cash
from services.clock import day_bounds, today_local
from services.price_guard import inr
from services.vision import NOTE_DENOMS, cash_total

LOW_CONFIDENCE = 0.8
DENOM_KEYS = [str(d) for d in NOTE_DENOMS] + ["coins"]


def breakdown(db: Session, day: Optional[date] = None) -> dict:
    """Expected cash = opening float + cash payments - cash refunds (the total comes from
    services.cash.expected_cash so there is a single source of truth)."""
    day = day or today_local()
    start, end = day_bounds(day)
    store = db.query(StoreProfile).first()
    base = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
        Payment.mode == "cash", Payment.created_at >= start, Payment.created_at < end)
    taken = round(float(base.filter(Payment.status == "success").scalar() or 0.0), 2)
    refunds = round(float(base.filter(Payment.status == "refunded").scalar() or 0.0), 2)
    return {"day": day.isoformat(), "opening_float": round(float(store.opening_float or 0.0), 2) if store else 0.0,
            "cash_payments": taken, "refunds": refunds, "expected": cash.expected_cash(db, day)}


def clean_denominations(raw: dict[str, Any]) -> dict[str, float]:
    """Validate a denominations table: known keys only, counts >= 0. Returns a full table."""
    out: dict[str, float] = {k: 0 for k in DENOM_KEYS}
    for k, v in (raw or {}).items():
        key = str(k).strip()
        if key not in out:
            raise ValueError(f"Unknown denomination '{k}' (use {', '.join(DENOM_KEYS)})")
        try:
            num = float(v or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Denomination '{k}': '{v}' is not a number") from exc
        if num < 0:
            raise ValueError(f"Denomination '{k}' cannot be negative")
        if key != "coins":
            if abs(num - round(num)) > 1e-9:
                raise ValueError(f"Denomination '{k}': note counts must be whole numbers")
            num = int(round(num))
        out[key] = num
    return out


def table(denoms: dict[str, float], per_conf: dict[str, float], overall: float) -> list[dict]:
    """Row per denomination: {denomination, count, value, confidence}. `coins` row's value is
    the rupee value of loose coins (count is not meaningful)."""
    rows = []
    for key in DENOM_KEYS:
        n = denoms.get(key, 0) or 0
        rows.append({"denomination": key, "count": n if key != "coins" else None,
                     "value": float(n) if key == "coins" else int(key) * n,
                     "confidence": round(float(per_conf.get(key, overall)), 2)})
    return rows


def low_confidence_flags(denoms: dict[str, float], per_conf: dict[str, float], overall: float,
                         threshold: float = LOW_CONFIDENCE) -> list[dict]:
    flags = []
    for key in DENOM_KEYS:
        n = denoms.get(key, 0) or 0
        conf = float(per_conf.get(key, overall))
        if n and conf < threshold:
            what = "coins" if key == "coins" else f"₹{key} ke note"
            flags.append({"denomination": key, "count": n if key != "coins" else None, "confidence": round(conf, 2),
                          "message": f"{what} dobara gin lein (pakka nahi: {int(conf * 100)}%)"})
    if overall < threshold and not flags:
        flags.append({"denomination": "all", "count": None, "confidence": round(overall, 2),
                      "message": "Photo saaf nahi hai, sab note dobara gin lein"})
    return flags


def difference_message(expected: float, counted: float) -> str:
    diff = round(counted - expected, 2)
    if abs(diff) < 0.005:
        return f"{inr(expected)} hona chahiye tha, aur {inr(counted)} hi hai. Hisaab bilkul sahi."
    tail = f"{inr(-diff)} kam." if diff < 0 else f"{inr(diff)} zyada."
    return f"{inr(expected)} hona chahiye tha, {inr(counted)} hai. {tail}"


def evaluate(db: Session, denoms: dict[str, float], per_conf: Optional[dict] = None,
             overall: float = 1.0, day: Optional[date] = None) -> dict:
    """Counted vs expected for a denominations table."""
    counted = round(cash_total(denoms), 2)
    bd = breakdown(db, day)
    diff = round(counted - bd["expected"], 2)
    per_conf = per_conf or {}
    return {"day": bd["day"], "counted": counted, "expected": bd["expected"], "difference": diff,
            "message_hi": difference_message(bd["expected"], counted), "denominations": denoms,
            "table": table(denoms, per_conf, overall), "confidence": round(overall, 2),
            "denomination_confidence": {k: round(float(per_conf.get(k, overall)), 2) for k in DENOM_KEYS},
            "low_confidence_flags": low_confidence_flags(denoms, per_conf, overall),
            "expected_breakdown": bd}
