"""Distributor-bill guards: price increase, trade scheme, margin and expiry checks.

Pure functions (no database, no network) so they are trivially testable.

  * price check   rate vs the last confirmed rate; an increase above 2% is flagged.
  * scheme check  "Buy 10 Get 1 Free" / "10+1": expected free = floor(qty / buy) * free;
                  fewer free units on the bill than expected means the distributor
                  did not give the scheme.
  * margin check  (MRP - rate) / MRP below 5% is thin (MRP includes GST, so the real
                  margin is even lower).
  * expiry check  expired, or expiring within 60 days.

Flags are dicts: {"code", "severity" ("info" | "warn" | "error"), "message"}.
`message` is short Hinglish-friendly text the UI can show as is.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

PRICE_INCREASE_PCT = 2.0
MIN_MARGIN_PCT = 5.0
EXPIRY_WARN_DAYS = 60

_BUY_GET = re.compile(
    r"(?:buy|kharid\w*|लें|खरीदें)?\s*(\d+)\s*(?:get|pe|par|per|पर|पे)\s*(\d+)\b", re.IGNORECASE)
_PLUS = re.compile(r"(?<![\d%.])(\d+)\s*\+\s*(\d+)(?!\s*%)")
_NO_SCHEME = {"", "-", "--", "na", "n/a", "nil", "none", "no", "no scheme", "null"}


@dataclass(frozen=True)
class Scheme:
    buy: int
    free: int

    def expected_free(self, qty: float) -> int:
        """Free units owed for `qty` bought units: floor(qty / buy) * free."""
        if self.buy <= 0 or qty <= 0:
            return 0
        return int(math.floor(qty / self.buy + 1e-9)) * self.free


def parse_scheme(text: Optional[str]) -> Optional[Scheme]:
    """'Buy 10 Get 1 Free' / 'buy 10 get 1' / '10+1' / '10 pe 1 free' -> Scheme(10, 1).
    Returns None for empty / 'no scheme' text and for discounts that are not unit schemes."""
    t = (text or "").strip()
    if t.lower() in _NO_SCHEME:
        return None
    m = _PLUS.search(t) or _BUY_GET.search(t)
    if not m:
        return None
    buy, free = int(m.group(1)), int(m.group(2))
    if buy <= 0 or free <= 0:
        return None
    return Scheme(buy, free)


def flag(code: str, severity: str, message: str, **extra) -> dict:
    return {"code": code, "severity": severity, "message": message, **extra}


def rupees(x: float) -> str:
    """'3', '2.5', '8.6' (no trailing zeros) for use inside messages."""
    x = round(float(x), 2)
    return f"{int(x)}" if x == int(x) else f"{x:g}"


# --- individual checks ---


def check_price(rate: float, prev_rate: Optional[float], *, name: str = "",
                threshold_pct: float = PRICE_INCREASE_PCT) -> dict:
    """Compare against the previous rate. Returns
    {"previous_rate", "delta", "delta_pct", "flags"}; flags hold at most one entry."""
    out = {"previous_rate": prev_rate, "delta": None, "delta_pct": None, "flags": []}
    if prev_rate is None or prev_rate <= 0 or rate <= 0:
        return out
    delta = round(rate - prev_rate, 2)
    pct = round(delta / prev_rate * 100.0, 2)
    out["delta"], out["delta_pct"] = delta, pct
    label = name or "Rate"
    if pct > threshold_pct:
        out["flags"].append(flag(
            "price_increase", "warn",
            f"{label} rate Rs{rupees(rate)} vs Rs{rupees(prev_rate)} last time: Rs{rupees(delta)} costlier",
            amount=delta))
    elif pct < -threshold_pct:
        out["flags"].append(flag(
            "price_drop", "info",
            f"{label} rate Rs{rupees(rate)} vs Rs{rupees(prev_rate)} last time: Rs{rupees(-delta)} cheaper",
            amount=delta))
    return out


def margin_pct(rate: float, mrp: Optional[float]) -> Optional[float]:
    """(MRP - rate) / MRP in percent; None when MRP or rate is unknown."""
    if not mrp or mrp <= 0 or rate is None or rate <= 0:
        return None
    return round((mrp - rate) / mrp * 100.0, 2)


def check_margin(rate: float, mrp: Optional[float], *, name: str = "",
                 min_pct: float = MIN_MARGIN_PCT) -> dict:
    m = margin_pct(rate, mrp)
    out = {"margin_pct": m, "flags": []}
    label = name or "Item"
    if m is None:
        return out
    if m < 0:
        out["flags"].append(flag("rate_above_mrp", "error",
                                 f"{label}: rate Rs{rupees(rate)} is above MRP Rs{rupees(mrp)}"))
    elif m < min_pct:
        out["flags"].append(flag("low_margin", "warn",
                                 f"{label}: margin only {m:g}% (MRP Rs{rupees(mrp)}, rate Rs{rupees(rate)})",
                                 margin_pct=m))
    return out


def check_scheme(qty: float, free_received: float, scheme_text: Optional[str], *, name: str = "",
                 rate: float = 0.0) -> dict:
    """Scheme check. Returns {"scheme", "free_expected", "flags"}.
    Flags 'scheme_missed' when fewer free units arrived than the scheme promises."""
    scheme = parse_scheme(scheme_text)
    out = {"scheme": None, "free_expected": 0, "flags": []}
    label = name or "Item"
    if scheme is None:
        if (scheme_text or "").strip().lower() not in _NO_SCHEME:
            out["flags"].append(flag("scheme_unparsed", "info",
                                     f"{label}: scheme '{scheme_text}' not understood, check by hand"))
        return out
    expected = scheme.expected_free(qty)
    out["scheme"] = {"buy": scheme.buy, "free": scheme.free, "text": scheme_text}
    out["free_expected"] = expected
    got = float(free_received or 0)
    if got + 1e-9 < expected:
        missing = expected - got
        out["flags"].append(flag(
            "scheme_missed", "warn",
            f"{label}: free packet not counted ('{(scheme_text or '').strip()}'): expected "
            f"{rupees(expected)} got {rupees(got)}",
            expected=expected, received=got, missing=missing,
            value=round(missing * rate, 2) if rate else None))
    return out


def check_expiry(expiry: Optional[date], today: date, *, name: str = "",
                 warn_days: int = EXPIRY_WARN_DAYS) -> dict:
    out = {"days_to_expiry": None, "flags": []}
    if expiry is None:
        return out
    days = (expiry - today).days
    out["days_to_expiry"] = days
    label = name or "Item"
    if days < 0:
        out["flags"].append(flag("expired", "error", f"{label}: already expired {-days} din pehle",
                                 days=days))
    elif days <= warn_days:
        out["flags"].append(flag("expiry_soon", "warn", f"{label}: {days} din mein expire",
                                 days=days))
    return out


def inr(x: float) -> str:
    """Indian grouping with the rupee sign: 6850 -> '₹6,850', 123456 -> '₹1,23,456', 2.5 -> '₹2.5'."""
    x = round(float(x), 2)
    neg = x < 0
    x = abs(x)
    whole = int(x)
    frac = round(x - whole, 2)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    if frac:
        s += f"{frac:.2f}".rstrip("0")[1:]
    return ("-" if neg else "") + "₹" + s
