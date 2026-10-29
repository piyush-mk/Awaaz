"""MRP-inclusive GST arithmetic, invoice numbers and the GST 2.0 rate table.

Kirana prices are MRP *including* GST, so tax is backed out of the price:
    taxable = total / (1 + rate);  gst = total - taxable;  cgst = sgst = gst / 2
All arithmetic runs in integer paise. Rounding remainders are pushed into the
parts (taxable absorbs rounding, sgst absorbs the odd paisa) so the parts always
add up to the total exactly.

Composition-scheme dealers cannot collect GST: they issue a "bill of supply"
with no tax split (taxable = total).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

# GST 2.0 (effective 22 Sep 2025) rates by category, in percent. This is SEED DATA:
# verify every rate against the CBIC notification before relying on it for filing.
#   * Packaged food (noodles, biscuits, namkeen, ghee, butter, honey, dry fruits, sweets):
#     5% (was 12%/18%).
#   * Toothpaste, toilet soap: 5% (was 12%/18%).
#   * Detergent / washing powder / dishwash bar: 18% (unchanged).
#   * Staples (salt, unbranded atta/rice/dal/sugar loose, milk, eggs, paneer, bread): 0%.
#   * Branded pre-packed atta/rice: 5% (levied since Jul 2022, still 5%).
GST_RATES_BY_CATEGORY: dict[str, float] = {
    "packaged_food": 5.0,
    "oral_care": 5.0,
    "soap": 5.0,
    "detergent": 18.0,
    "staples": 0.0,
    "fresh": 0.0,
    "branded_staples": 5.0,
    "edible_oil": 5.0,
    "festival": 5.0,
    "confectionery": 18.0,
    "beverage_mix": 18.0,
    "aerated_drink": 40.0,  # 28% slab replaced by 40% for aerated/sugary drinks
    "water": 18.0,
}


def to_paise(rupees: float) -> int:
    """Rupees to integer paise (half-up on the float's decimal representation)."""
    return int(round(float(rupees) * 100 + 1e-9))


def to_rupees(paise: int) -> float:
    return round(paise / 100.0, 2)


@dataclass(frozen=True)
class TaxSplit:
    """GST split of one amount, all in paise; taxable + cgst + sgst == total."""

    total: int
    taxable: int
    cgst: int
    sgst: int

    @property
    def gst(self) -> int:
        return self.cgst + self.sgst


def split_inclusive(total_paise: int, rate_pct: float) -> TaxSplit:
    """Back GST out of a GST-inclusive amount (paise in, paise out)."""
    if rate_pct <= 0 or total_paise == 0:
        return TaxSplit(total_paise, total_paise, 0, 0)
    taxable = int(round(total_paise / (1.0 + rate_pct / 100.0)))
    gst = total_paise - taxable
    cgst = gst // 2
    sgst = gst - cgst
    return TaxSplit(total_paise, taxable, cgst, sgst)


@dataclass
class LineTotals:
    """Priced invoice line (rupees, 2 dp). `taxable + cgst + sgst == total`."""

    qty: float
    unit_price: float
    gst_rate: float
    taxable: float
    cgst: float
    sgst: float
    total: float


def price_line(qty: float, unit_price: float, gst_rate: float, composition: bool = False,
               total_override: Optional[float] = None) -> LineTotals:
    """Price one line. `total_override` pins the line total (amount-based sales:
    "Rs 20 ki cheeni" is billed Rs 20 whatever the rounded weight is)."""
    total_p = to_paise(total_override) if total_override is not None else to_paise(qty * unit_price)
    if composition:
        split = TaxSplit(total_p, total_p, 0, 0)
        rate = 0.0
    else:
        split = split_inclusive(total_p, gst_rate)
        rate = gst_rate
    return LineTotals(qty=qty, unit_price=unit_price, gst_rate=rate,
                      taxable=to_rupees(split.taxable), cgst=to_rupees(split.cgst),
                      sgst=to_rupees(split.sgst), total=to_rupees(split.total))


@dataclass
class InvoiceTotals:
    doc_type: str
    lines: list[LineTotals]
    taxable: float
    cgst: float
    sgst: float
    total: float
    by_rate: dict[float, dict[str, float]]  # rate -> {taxable, cgst, sgst, total}


def doc_type_for(composition: bool) -> str:
    return "bill_of_supply" if composition else "tax_invoice"


def totals_for_lines(lines: Iterable[LineTotals], composition: bool = False) -> InvoiceTotals:
    """Sum priced lines (in paise to avoid float drift) with a per-rate GST summary."""
    lines = list(lines)
    t = c = s = tot = 0
    by_rate: dict[float, list[int]] = {}
    for ln in lines:
        lt, lc, ls, ltot = (to_paise(ln.taxable), to_paise(ln.cgst), to_paise(ln.sgst),
                            to_paise(ln.total))
        t += lt
        c += lc
        s += ls
        tot += ltot
        agg = by_rate.setdefault(ln.gst_rate, [0, 0, 0, 0])
        agg[0] += lt
        agg[1] += lc
        agg[2] += ls
        agg[3] += ltot
    return InvoiceTotals(
        doc_type=doc_type_for(composition), lines=lines,
        taxable=to_rupees(t), cgst=to_rupees(c), sgst=to_rupees(s), total=to_rupees(tot),
        by_rate={r: {"taxable": to_rupees(v[0]), "cgst": to_rupees(v[1]),
                     "sgst": to_rupees(v[2]), "total": to_rupees(v[3])} for r, v in by_rate.items()},
    )


# --- invoice numbers ---


def financial_year(day: date) -> str:
    """Indian FY label: 2026-10-29 -> '2026-27'; 2026-02-01 -> '2025-26'."""
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def invoice_number(prefix: str, day: date, seq: int) -> str:
    """e.g. RGS/2026-27/000123"""
    return f"{prefix}/{financial_year(day)}/{seq:06d}"


def parse_sequence(number: str) -> int:
    """Trailing sequence of an invoice number ('RGS/2026-27/000123' -> 123); 0 if malformed."""
    try:
        return int(number.rsplit("/", 1)[-1])
    except (ValueError, IndexError):
        return 0
