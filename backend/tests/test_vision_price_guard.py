"""price_guard: scheme parser, price, margin and expiry checks (pure functions)."""
from datetime import date

import pytest

from services import price_guard as pg


@pytest.mark.parametrize("text,buy,free", [
    ("Buy 10 Get 1 Free", 10, 1), ("buy 10 get 1", 10, 1), ("BUY 12 GET 2 FREE", 12, 2),
    ("10+1", 10, 1), ("10 + 1 free", 10, 1), ("10 pe 1 free", 10, 1)])
def test_scheme_parses(text, buy, free):
    s = pg.parse_scheme(text)
    assert (s.buy, s.free) == (buy, free)


@pytest.mark.parametrize("text", ["", None, "no scheme", "No Scheme", "NA", "-", "5% off", "5% + 2%"])
def test_no_scheme(text):
    assert pg.parse_scheme(text) is None


def test_expected_free_is_floor_of_qty_over_buy():
    s = pg.parse_scheme("Buy 10 Get 1")
    assert [s.expected_free(q) for q in (0, 9, 10, 19, 20, 25)] == [0, 0, 1, 1, 2, 2]


def test_scheme_missed_flag():
    r = pg.check_scheme(10, 0, "Buy 10 Get 1 Free", name="Surf", rate=45)
    assert r["free_expected"] == 1
    f = r["flags"][0]
    assert f["code"] == "scheme_missed" and "expected 1 got 0" in f["message"]
    assert f["missing"] == 1 and f["value"] == 45


def test_scheme_satisfied_or_absent_has_no_flag():
    assert pg.check_scheme(10, 1, "Buy 10 Get 1 Free")["flags"] == []
    assert pg.check_scheme(9, 0, "Buy 10 Get 1 Free")["flags"] == []
    assert pg.check_scheme(10, 0, "no scheme")["flags"] == []
    assert pg.check_scheme(10, 0, "")["flags"] == []


def test_unparsed_scheme_is_info_only():
    f = pg.check_scheme(10, 0, "special festival offer")["flags"]
    assert [x["code"] for x in f] == ["scheme_unparsed"] and f[0]["severity"] == "info"


def test_price_increase_over_two_percent():
    r = pg.check_price(45, 42, name="Surf")
    assert r["delta"] == 3 and r["flags"][0]["code"] == "price_increase"
    assert "Rs3 costlier" in r["flags"][0]["message"]


def test_price_within_tolerance_and_drop():
    assert pg.check_price(11.2, 11.0)["flags"] == []          # +1.8%
    assert pg.check_price(11.0, 11.0)["flags"] == []
    assert pg.check_price(40, 42)["flags"][0]["code"] == "price_drop"
    assert pg.check_price(40, None)["flags"] == []


def test_margin_check():
    assert pg.margin_pct(45, 45) == 0
    assert pg.check_margin(45, 45, name="Surf")["flags"][0]["code"] == "low_margin"
    assert pg.check_margin(9.6, 10)["flags"][0]["code"] == "low_margin"        # 4%
    assert pg.check_margin(11, 12)["flags"] == []                             # 8.3%
    assert pg.check_margin(50, 45)["flags"][0]["code"] == "rate_above_mrp"
    assert pg.check_margin(11, None)["flags"] == []


def test_expiry_check():
    today = date(2026, 10, 29)
    assert pg.check_expiry(date(2026, 12, 13), today)["flags"][0]["code"] == "expiry_soon"   # 45 days
    assert pg.check_expiry(date(2027, 3, 1), today)["flags"] == []
    assert pg.check_expiry(date(2026, 10, 1), today)["flags"][0]["code"] == "expired"
    assert pg.check_expiry(None, today)["flags"] == []


def test_inr_formatting():
    assert pg.inr(6850) == "₹6,850" and pg.inr(150) == "₹150" and pg.inr(123456) == "₹1,23,456"
