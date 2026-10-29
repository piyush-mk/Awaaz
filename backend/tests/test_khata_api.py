"""Khata ledger, limits, WhatsApp confirmation, reminders, passbook, Postpaid (simulated), notebook import.
No provider keys, no network."""
import dataclasses

import pytest
from fastapi.testclient import TestClient

import main
import seed as seed_module
from models import KhataEntry, Message, Payment, PendingAction
from services import events
from services import khata as kh
from services import postpaid as postpaid_service
from services import whatsapp as wa

VERMA = 2  # seed: balance 850, 3 late payments, limit 1000, phone 919810000002


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c
    seed_module.seed(reset=True, verbose=False)


@pytest.fixture(autouse=True)
def no_real_delivery(monkeypatch):
    monkeypatch.setattr(wa, "_schedule", lambda _mid: None)


def _events(channel, type_):
    return [e for e in events.bus.replay(channel, 0) if e["type"] == type_]


# --- pure helpers -------------------------------------------------------------


def test_fmt_and_confirm_message():
    assert kh.fmt_inr(1350) == "1,350" and kh.fmt_inr(150000) == "1,50,000" and kh.fmt_inr(99.5) == "99.50"
    cust = type("C", (), {"language": "hi-IN", "name": "Verma ji"})()
    assert kh.confirm_message(cust, 500, 1350) == (
        "₹500 aapke khate mein jude. Kul baaki ₹1,350. Galat ho toh reply karein.")
    assert kh.confirm_message(cust, -300, 1050) == "₹300 mile, baaki ₹1,050. Dhanyavaad."
    assert "saaf" in kh.confirm_message(cust, -300, 0)
    en = type("C", (), {"language": "en-IN", "name": "X"})()
    assert "Reply if this is wrong" in kh.confirm_message(en, 500, 1350)


def test_suggested_limit_ladder():
    def c(late, limit=1000.0):
        return type("C", (), {"late_payments": late, "credit_limit": limit, "name": "Verma ji"})()

    assert kh.suggested_limit(c(0)) == 1000
    assert kh.suggested_limit(c(1)) == 800
    assert kh.suggested_limit(c(2)) == 600
    assert kh.suggested_limit(c(3)) == 500 and kh.suggested_limit(c(7, 5000)) == 500
    assert kh.limit_reason(c(3)) == "Verma ji ne pichhli 3 baar der se chukaya. Limit ₹500 tak rakhein?"
    assert kh.limit_reason(c(0)) == ""


# --- customers ----------------------------------------------------------------


def test_customers_list_and_detail(client):
    rows = client.get("/api/khata/customers").json()
    assert all(r["name"] != "Walk-in Customer" for r in rows)
    verma = next(r for r in rows if r["id"] == VERMA)
    assert verma["balance"] == 850 and verma["late_payments"] == 3
    assert verma["suggested_limit"] == 500 and verma["risk"] == "high" and verma["over_limit"] is True
    assert "pichhli 3 baar" in verma["limit_reason"]
    assert verma["last_payment_at"] and verma["last_payment_amount"] > 0
    assert rows == sorted(rows, key=lambda r: -r["balance"])
    detail = client.get(f"/api/khata/customers/{VERMA}").json()
    assert detail["entries"][0]["running_balance"] == detail["balance"]
    assert client.get("/api/khata/customers/999").status_code == 404


# --- entries ------------------------------------------------------------------


def test_udhaar_flow_warning_and_whatsapp(client):
    r = client.post("/api/khata/entries", json={"customer_id": VERMA, "kind": "credit", "amount": 500})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["balance_before"] == 850 and body["balance_after"] == 1350
    text = body["whatsapp"]["text"]
    assert "1,350" in text and "Galat ho toh reply karein" in text
    assert body["whatsapp"]["to"] == "919810000002"
    w = body["warning"]
    assert w["over_limit"] and w["limit"] == 500 and "3 baar der se chukaya" in w["message_hi"]
    assert body["suggested_limit"] == 500 and body["entry"]["wa_status"] == "sent"
    assert body["entry"]["confirmed_by_customer"] is False
    msg = [e for e in events.bus.replay("wa", 0) if e["type"] == "wa_message"][-1]["data"]
    assert msg["body"] == text and msg["customer_id"] == VERMA
    upd = _events("store", "khata_updated")[-1]["data"]
    assert upd["customer_id"] == VERMA and upd["balance"] == 1350 and upd["warning"]["over_limit"]


def test_payment_and_fuzzy_name_and_errors(client):
    r = client.post("/api/khata/entries", json={"customer_name": "verma", "kind": "payment", "amount": 300}).json()
    assert r["customer"]["id"] == VERMA
    assert r["balance_after"] == r["balance_before"] - 300
    assert r["whatsapp"]["text"].startswith("₹300 mile, baaki ₹")
    assert r["warning"] is None
    assert client.post("/api/khata/entries", json={"customer_name": "zzzz qqq", "amount": 5}).status_code == 404
    assert client.post("/api/khata/entries", json={"customer_id": VERMA, "amount": 0}).status_code == 422


def test_enforce_limit_blocks_and_writes_nothing(client, db):
    before = db.query(KhataEntry).filter_by(customer_id=VERMA).count()
    r = client.post("/api/khata/entries", json={"customer_id": VERMA, "amount": 5000, "enforce_limit": True})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "credit_limit_exceeded"
    db.expire_all()
    assert db.query(KhataEntry).filter_by(customer_id=VERMA).count() == before
    ok = client.post("/api/khata/entries", json={"customer_id": 3, "amount": 100, "enforce_limit": True})
    assert ok.status_code == 200 and ok.json()["warning"] is None  # Sharma ji: no late payments


def test_confirm_and_dispute_endpoints(client):
    entry = client.post("/api/khata/entries", json={"customer_id": 5, "amount": 40, "send_whatsapp": False}).json()
    eid = entry["entry"]["id"]
    assert entry["whatsapp"] is None
    assert client.post(f"/api/khata/entries/{eid}/confirm").json()["confirmed_by_customer"] is True
    d = client.post(f"/api/khata/entries/{eid}/dispute", json={"note": "nahi liya"}).json()
    assert d["disputed"] is True and d["confirmed_by_customer"] is False
    assert _events("store", "khata_disputed")[-1]["data"]["entry_id"] == eid
    assert client.post("/api/khata/entries/99999/confirm").status_code == 404


# --- reminders, passbook --------------------------------------------------------


def test_reminders_preview_and_send(client, db):
    prev = client.post("/api/khata/reminders/preview").json()
    assert prev["count"] == len(prev["reminders"]) > 3
    assert all(r["balance"] > 0 for r in prev["reminders"])
    assert "1st-7th" in prev["window_note"] and isinstance(prev["in_salary_window"], bool)
    verma = next(r for r in prev["reminders"] if r["customer_id"] == VERMA)
    assert "upi://pay" in verma["text"] and "baaki hain" in verma["text"] and verma["has_phone"]
    assert prev["reminders"][0]["balance"] >= prev["reminders"][-1]["balance"]
    only = client.post("/api/khata/reminders/preview", json={"customer_ids": [VERMA]}).json()
    assert only["count"] == 1
    sent = client.post("/api/khata/reminders/send", json={"customer_ids": [VERMA]}).json()
    assert len(sent["sent"]) == 1
    db.expire_all()
    assert "baaki hain" in db.get(Message, sent["sent"][0]["message_id"]).body


def test_passbook_pages(client):
    token = kh.passbook_token(VERMA)
    page = client.get(f"/api/khata/passbook/{token}")
    assert page.status_code == 200 and "Verma ji ka khata" in page.text and "upi://pay" in page.text
    assert client.get("/api/khata/passbook/2.deadbeefdeadbeef").status_code == 404
    assert client.get("/api/khata/passbook/garbage").status_code == 404
    assert client.get(f"/api/khata/customers/{VERMA}/passbook").status_code == 200
    assert kh.customer_id_from_token(token) == VERMA
    assert token in kh.passbook_url(VERMA)


# --- Postpaid (simulated) -------------------------------------------------------


def test_postpaid_offer_and_approve(client, db):
    offer = client.post("/api/khata/postpaid/offer",
                        json={"customer_id": VERMA, "amount": 500, "send_whatsapp": True}).json()
    assert offer["simulated"] is True and offer["eligible"] is True and offer["limit"] == 4000
    assert "simulated" in offer["message_hi"] and offer["link"].endswith(f"/postpaid/{offer['offer_id']}/page")
    assert offer["whatsapp"]["simulated"] is True and offer["status"] == "offered"
    row = db.get(PendingAction, offer["offer_id"])
    assert row.kind == "postpaid_offer" and row.status == "proposed"
    page = client.get(f"/api/khata/postpaid/{offer['offer_id']}/page")
    assert page.status_code == 200 and "SIMULATED" in page.text

    entries_before = db.query(KhataEntry).filter_by(customer_id=VERMA).count()
    done = client.post(f"/api/khata/postpaid/{offer['offer_id']}/approve").json()
    assert done["simulated"] is True and done["status"] == "approved" and done["shop_paid_now"] is True
    assert done["payment"]["mode"] == "postpaid" and done["whatsapp"]["simulated"] is True
    db.expire_all()
    pay = db.get(Payment, done["payment"]["id"])
    assert pay.mode == "postpaid" and pay.status == "success" and pay.amount == 500 and pay.rail == "simulated"
    assert db.query(KhataEntry).filter_by(customer_id=VERMA).count() == entries_before  # no udhaar created
    assert "simulated" in db.query(Message).order_by(Message.id.desc()).first().body.lower()
    ev = _events("store", "postpaid_approved")[-1]["data"]
    assert ev["simulated"] is True and ev["amount"] == 500 and ev["customer_id"] == VERMA
    again = client.post(f"/api/khata/postpaid/{offer['offer_id']}/approve").json()
    assert again["already_approved"] is True
    assert db.query(Payment).filter_by(mode="postpaid").count() == 1


def test_postpaid_ineligible_amount(client):
    offer = client.post("/api/khata/postpaid/offer", json={"customer_id": VERMA, "amount": 99999}).json()
    assert offer["eligible"] is False and offer["simulated"] is True
    assert client.post(f"/api/khata/postpaid/{offer['offer_id']}/approve").status_code == 409
    assert client.post("/api/khata/postpaid/99999/approve").status_code == 404
    assert postpaid_service.credit_line(type("C", (), {"late_payments": 0})()) == 10000


# --- notebook photo import ------------------------------------------------------


def _upload(client):
    return client.post("/api/khata/import-photo", files={"image": ("page.jpg", b"\xff\xd8fake", "image/jpeg")})


def test_import_photo_fixture_flow(client, db):
    r = _upload(client)
    assert r.status_code == 200, r.text
    prop = r.json()
    assert prop["source"] == "fixture" and prop["summary"]["rows"] == 5
    assert prop["summary"]["new_customers"] == 5 and prop["summary"]["included_amount"] == 2575
    assert {x["name"] for x in prop["rows"]} >= {"Tiwari ji", "Mishra ji"}
    edits = {"rows": [{"index": 4, "include": False}, {"index": 0, "amount": 400}]}
    done = client.post(f"/api/khata/import/{prop['action_id']}/confirm", json=edits).json()
    assert len(done["created_customers"]) == 4 and done["skipped"] == 1
    assert done["total_imported"] == 400 + 1150 + 275 + 640
    db.expire_all()
    tiwari = next(c for c in client.get("/api/khata/customers").json() if c["name"] == "Tiwari ji")
    assert tiwari["balance"] == 400
    assert db.get(PendingAction, prop["action_id"]).status == "confirmed"
    assert client.post(f"/api/khata/import/{prop['action_id']}/confirm").status_code == 409
    assert _events("store", "khata_imported")[-1]["data"]["entries"] == 4


def test_import_matches_existing_customers(client):
    prop = _upload(client).json()  # Tiwari/Mishra/Pandey/Rina now exist from the previous test
    matched = [r for r in prop["rows"] if r["match"]]
    assert {r["name"] for r in matched} >= {"Tiwari ji", "Mishra ji"}
    assert all(r["action"] == "add_to_existing" and r["include"] is False for r in matched)
    assert all(r["match"]["current_balance"] > 0 for r in matched)
    assert client.post("/api/khata/import-photo").status_code == 422
    assert client.get(f"/api/khata/import/{prop['action_id']}").json()["action_id"] == prop["action_id"]


def test_settings_replace_helper_still_frozen():
    # Guards the assumption used by the WhatsApp tests: settings are frozen, so tests replace module copies.
    with pytest.raises(dataclasses.FrozenInstanceError):
        wa.settings.wa_token = "x"
