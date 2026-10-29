"""Parchi (handwritten shopping list) -> counter cart lines (F12).

Each vision row {name, qty, unit} is turned into a phrase ("500 g dal") and parsed by the
same quantity engine the counter uses, so units, loose goods and pricing behave exactly like
voice billing. Rows that match nothing come back in `unmatched`.
"""
from __future__ import annotations

from typing import Any, Optional

from schemas import CartLine
from services import quantity
from services.catalog import CatalogIndex

_UNIT_ALIASES = {"gm": "g", "gms": "g", "gram": "g", "grams": "g", "kilo": "kg", "kgs": "kg",
                 "ltr": "litre", "lt": "litre", "liter": "litre", "l": "litre", "pkt": "packet",
                 "pc": "packet", "pcs": "packet"}


def _qty_text(qty: float) -> str:
    return f"{qty:g}"


def parse_rows(rows: list[dict[str, Any]], index: CatalogIndex) -> tuple[list[CartLine], list[dict]]:
    """Vision rows -> (cart lines, unmatched rows). Duplicate products are merged."""
    lines: list[CartLine] = []
    unmatched: list[dict] = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        qty = float(row.get("qty") or 1) or 1.0
        unit = str(row.get("unit") or "").strip().lower()
        unit = _UNIT_ALIASES.get(unit, unit)
        raw = " ".join(x for x in (_qty_text(qty), unit, name) if x)
        parsed = _parse_one(raw, name, qty, unit, index)
        if parsed:
            for ln in parsed:
                ln.raw = raw
                ln.flags = [*ln.flags, "from_parchi"]
            lines.extend(parsed)
        else:
            unmatched.append({"name": name, "qty": qty, "unit": unit, "raw": raw})
    return _merge(lines), unmatched


def _parse_one(raw: str, name: str, qty: float, unit: str, index: CatalogIndex) -> list[CartLine]:
    out = quantity.parse_order_full(raw, index=index)
    if out.lines:
        return out.lines
    if not name:
        return []
    product, score = index.find_in_phrase(name)  # longer descriptions, e.g. "Surf Excel Easy Wash"
    if product is None:
        return []
    kind, factor = quantity.UNITS.get(unit, ("count", 1.0)) if unit else ("bare", 1.0)
    q = quantity.Qty(value=qty * factor if kind in ("weight", "volume") else qty, kind=kind,
                     unit=unit or None, raw=raw)
    return [quantity.build_line(product, q, raw, score)]


def _merge(lines: list[CartLine]) -> list[CartLine]:
    merged: dict[tuple, CartLine] = {}
    out: list[CartLine] = []
    for ln in lines:
        key = (ln.product_id, ln.unit)
        prev: Optional[CartLine] = merged.get(key) if ln.product_id is not None else None
        if prev is not None and ln.amount_rupees is None and prev.amount_rupees is None:
            prev.qty = round(prev.qty + ln.qty, 3)
            prev.line_total = round(prev.qty * prev.unit_price, 2)
            if prev.sell_mode == "loose":
                prev.weigh_instruction = quantity.weigh_instruction(prev.qty, prev.base_unit)
            continue
        if ln.product_id is not None:
            merged[key] = ln
        out.append(ln)
    return out
