import random
from datetime import date

import pytest

from services import pricing
from services.pricing import (financial_year, invoice_number, parse_sequence, price_line,
                              split_inclusive, to_paise, totals_for_lines)


def test_demo_cart_totals_exactly_249():
    """Maggi x2 (12) + Surf x1 (45) + Colgate x4 (45), GST 2.0 rates, MRP-inclusive."""
    lines = [price_line(2, 12, 5), price_line(1, 45, 18), price_line(4, 45, 5)]
    t = totals_for_lines(lines)
    assert t.total == 249.0
    assert t.doc_type == "tax_invoice"
    assert round(t.taxable + t.cgst + t.sgst, 2) == 249.0
    assert abs(t.cgst - t.sgst) <= 0.02
    for ln in lines:
        assert round(ln.taxable + ln.cgst + ln.sgst, 2) == ln.total


def test_gst_is_backed_out_of_mrp_not_added():
    ln = price_line(1, 118, 18)
    assert ln.total == 118.0 and ln.taxable == 100.0 and ln.cgst == 9.0 and ln.sgst == 9.0


@pytest.mark.parametrize("rate", [0, 5, 12, 18, 40])
def test_parts_always_sum_to_total(rate):
    rng = random.Random(rate)
    for _ in range(500):
        total_p = rng.randint(1, 500000)
        s = split_inclusive(total_p, rate)
        assert s.taxable + s.cgst + s.sgst == total_p
        assert abs(s.cgst - s.sgst) <= 1


def test_zero_rate_has_no_tax():
    ln = price_line(2, 28, 0)
    assert (ln.taxable, ln.cgst, ln.sgst, ln.total) == (56.0, 0.0, 0.0, 56.0)


def test_composition_scheme_issues_bill_of_supply_without_tax():
    lines = [price_line(2, 12, 5, composition=True), price_line(1, 45, 18, composition=True)]
    t = totals_for_lines(lines, composition=True)
    assert t.doc_type == "bill_of_supply"
    assert t.cgst == 0 and t.sgst == 0 and t.taxable == t.total == 69.0


def test_total_override_pins_amount_based_lines():
    ln = price_line(0.45, 44, 5, total_override=20)
    assert ln.total == 20.0
    assert round(ln.taxable + ln.cgst + ln.sgst, 2) == 20.0


def test_by_rate_summary_adds_up():
    t = totals_for_lines([price_line(2, 12, 5), price_line(1, 45, 18), price_line(1, 10, 5)])
    assert round(sum(v["total"] for v in t.by_rate.values()), 2) == t.total
    assert set(t.by_rate) == {5, 18}


def test_money_helpers():
    assert to_paise(249.0) == 24900 and to_paise(19.8) == 1980 and to_paise(0.29) == 29
    assert pricing.to_rupees(24900) == 249.0


def test_financial_year_and_invoice_number():
    assert financial_year(date(2026, 10, 29)) == "2026-27"
    assert financial_year(date(2027, 3, 31)) == "2026-27"
    assert financial_year(date(2026, 4, 1)) == "2026-27"
    assert financial_year(date(2026, 3, 31)) == "2025-26"
    assert invoice_number("RGS", date(2026, 10, 29), 123) == "RGS/2026-27/000123"
    assert parse_sequence("RGS/2026-27/000123") == 123 and parse_sequence("junk") == 0


def test_gst2_rate_table_values():
    r = pricing.GST_RATES_BY_CATEGORY
    assert r["packaged_food"] == 5 and r["oral_care"] == 5 and r["soap"] == 5
    assert r["detergent"] == 18 and r["staples"] == 0 and r["fresh"] == 0
    assert 12 not in r.values() and 28 not in r.values()
