"""F7 galla closing (fixture mode, no keys)."""
import pytest
from fastapi.testclient import TestClient

import main
import seed as seed_module
from database import SessionLocal
from models import CashClosing
from services import cash, events, galla
from services.clock import today_local

IMG = {"image": ("cash.jpg", b"fake", "image/jpeg")}


@pytest.fixture(scope="module")
def client():
    seed_module.seed(reset=True, verbose=False)
    with TestClient(main.app) as c:
        yield c
    seed_module.seed(reset=True, verbose=False)


def test_expected_breakdown(client):
    r = client.get("/api/galla/expected").json()
    db = SessionLocal()
    try:
        assert r["expected"] == cash.expected_cash(db, today_local())
    finally:
        db.close()
    assert r["expected"] == pytest.approx(r["opening_float"] + r["cash_payments"] - r["refunds"])
    assert r["opening_float"] == 2000 and r["expected"] == 6850 and r["already_closed"] is None
    assert "source" in r and "latency_ms" in r


def test_scan_fixture_is_150_short(client):
    assert client.post("/api/galla/scan").status_code == 422
    r = client.post("/api/galla/scan", files=IMG)
    assert r.status_code == 200
    out = r.json()
    assert out["counted"] == 6700 and out["expected"] == 6850 and out["difference"] == -150
    assert out["message_hi"] == "₹6,850 hona chahiye tha, ₹6,700 hai. ₹150 kam."
    assert out["source"] == "fixture" and out["demo_mode"] is True and out["latency_ms"] == 0
    assert out["denominations"]["500"] == 8 and out["denominations"]["coins"] == 0
    assert 0 < out["confidence"] <= 1
    rows = {t["denomination"]: t for t in out["table"]}
    assert rows["500"]["value"] == 4000 and rows["20"]["confidence"] == 0.74
    assert {f["denomination"] for f in out["low_confidence_flags"]} == {"20", "10"}
    assert out["expected_breakdown"]["expected"] == 6850
    # scanning does not write anything
    assert client.get("/api/galla/history").json()["items"][0]["day"] != today_local().isoformat()


def test_close_with_correction_writes_cashclosing_and_event(client):
    last = (events.bus.replay("store") or [{"id": 0}])[-1]["id"]
    scan = client.post("/api/galla/scan", files=IMG).json()
    fixed = {**scan["denominations"], "10": 15}          # the merchant recounts: 15 ten-rupee notes
    r = client.post("/api/galla/close", json={"denominations": fixed})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["counted"] == 6750 and out["expected"] == 6850 and out["difference"] == -100
    assert out["message_hi"] == "₹6,850 hona chahiye tha, ₹6,750 hai. ₹100 kam."
    assert out["updated"] is False and out["speech"]["audio_base64"] == "" and out["speech"]["url"] is None
    db = SessionLocal()
    try:
        row = db.query(CashClosing).filter(CashClosing.day == today_local()).one()
        assert (row.expected, row.counted, row.diff) == (6850, 6750, -100)
        assert row.denominations["10"] == 15
    finally:
        db.close()
    ev = [e for e in events.bus.replay("store", last) if e["type"] == "galla_closed"]
    assert ev and ev[-1]["data"]["diff"] == -100 and ev[-1]["data"]["counted"] == 6750

    # closing again the same day replaces the count
    again = client.post("/api/galla/close", json={"denominations": scan["denominations"], "speak": False}).json()
    assert again["updated"] is True and again["difference"] == -150 and again["speech"] is None
    hist = client.get("/api/galla/history").json()
    assert hist["items"][0]["day"] == today_local().isoformat() and hist["items"][0]["diff"] == -150
    assert hist["summary"]["count"] == len(hist["items"]) and hist["summary"]["short_days"] >= 1
    assert client.get("/api/galla/expected").json()["already_closed"]["counted"] == 6700


@pytest.mark.parametrize("bad", [{"777": 1}, {"500": -1}, {"500": 1.5}, {"500": "x"}])
def test_close_validation(client, bad):
    assert client.post("/api/galla/close", json={"denominations": bad}).status_code in (422,)


def test_messages():
    assert galla.difference_message(6850, 6850).endswith("Hisaab bilkul sahi.")
    assert galla.difference_message(6850, 7000).endswith("₹150 zyada.")
    assert galla.difference_message(6850, 6700).endswith("₹150 kam.")
    flags = galla.low_confidence_flags({"500": 0}, {}, 0.5)
    assert flags[0]["denomination"] == "all"
    assert galla.low_confidence_flags({"500": 1}, {"500": 0.9}, 0.9) == []
