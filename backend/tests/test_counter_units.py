"""Pure helpers of the counter: split allocation, callback parsing, UPI string, control phrases."""
import pytest
from fastapi import HTTPException

from services import counter, payments


def test_allocate_defaults_and_remainders():
    assert payments.allocate(249, None) == {"upi": 249.0, "cash": 0.0, "khata": 0.0}
    assert payments.allocate(500, {"cash": 300, "upi": 200, "khata": None}) == \
        {"cash": 300.0, "upi": 200.0, "khata": 0.0}
    assert payments.allocate(700, {"cash": 300, "upi": 200, "khata": None}) == \
        {"cash": 300.0, "upi": 200.0, "khata": 200.0}
    assert payments.allocate(249, {"cash": 100}) == {"cash": 100.0, "upi": 149.0, "khata": 0.0}
    assert payments.allocate(249, {"customer_id": 3}) == {"upi": 249.0, "cash": 0.0, "khata": 0.0}
    parts = payments.allocate(100.1, {"cash": 33.37, "upi": None})
    assert round(sum(parts.values()), 2) == 100.1
    with pytest.raises(HTTPException):
        payments.allocate(100, {"cash": 80, "upi": 40})


def test_upi_string_and_callback():
    s = payments.upi_intent_string(249, "AWZ000001", "Bill RGS/1", vpa="shop@paytm", name="Ramesh General Store")
    assert s == ("upi://pay?pa=shop@paytm&pn=Ramesh%20General%20Store&am=249.00&cu=INR&tr=AWZ000001"
                 "&tn=Bill%20RGS/1")
    assert payments.create_qr("A1", 10).rail == "upi_intent"
    with pytest.raises(NotImplementedError):
        payments.create_qr("A1", 10, rail="paytm_dqr")
    cb = payments.parse_callback({"body": {"ORDERID": "A1", "STATUS": "TXN_SUCCESS", "TXNAMOUNT": "10.00"}})
    assert cb == {"order_id": "A1", "state": "success", "amount": 10.0, "txn_id": None}
    assert payments.parse_callback({"order_id": "A1", "status": "failed"})["state"] == "failed"
    assert payments.parse_callback({"order_id": "A1", "status": "pending"})["state"] == "pending"


@pytest.mark.parametrize("text,expected", [
    ("galat hai", "undo"), ("cancel", "undo"), ("haan", "confirm"), ("ji haan", "confirm"),
    ("theek hai", "confirm"), ("nahi", "no"), ("do maggi", None), ("maggi cancel kar do", None),
    ("do", None), ("bas kitna hua", None),
])
def test_classify_control(text, expected):
    assert counter.classify_control(text) == expected


def test_indian_grouping():
    assert counter._inr(1350) == "1,350" and counter._inr(500) == "500"
    assert counter._inr(123456) == "1,23,456"
