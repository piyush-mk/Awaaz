"""Counter flow (Agent A): utterance -> cart -> checkout -> payment -> receipts. No API keys, no network."""
import pytest
from fastapi.testclient import TestClient

import main
import seed as seed_module
from database import SessionLocal
from models import Customer, Invoice, KhataEntry, MissedSale, Message, PendingAction, Payment
from services import events, llm, stock_ops
from services.types import ChatOut, Result, ToolCall

PHRASE = "do maggi ek surf excel chaar colgate"


@pytest.fixture(scope="module")
def client():
    seed_module.seed(reset=True, verbose=False)
    with TestClient(main.app) as c:
        yield c
    seed_module.seed(reset=True, verbose=False)


def say(client, text, session, **kw):
    data = {"text": text, "session_id": session, **{k: str(v) for k, v in kw.items()}}
    r = client.post("/api/agent/utterance", data=data)
    assert r.status_code == 200, r.text
    return r.json()


def store_events(after=0, type_=None):
    return [e for e in events.bus.replay("store", after) if type_ is None or e["type"] == type_]


def last_event_id():
    ev = events.bus.replay("store", 0)
    return ev[-1]["id"] if ev else 0


def stock(product_id):
    db = SessionLocal()
    try:
        return stock_ops.current_stock(db, product_id)
    finally:
        db.close()


def test_envelope_and_three_lines(client):
    mark = last_event_id()
    r = say(client, PHRASE, "s-basic")
    assert set(r) >= {"transcript", "cart", "actions", "spoken_text", "audio_url", "source",
                      "latency_ms", "demo_mode"}
    assert r["transcript"] == PHRASE and r["demo_mode"] is True
    lines = r["cart"]["lines"]
    assert [(ln["name"], ln["qty"]) for ln in lines] == [("Maggi", 2), ("Surf Excel", 1), ("Colgate", 4)]
    assert r["cart"]["total"] == 249.0
    assert "249" in r["spoken_text"]
    ev = store_events(mark, "cart_updated")
    assert ev and ev[0]["data"]["session_id"] == "s-basic"
    assert ev[0]["data"]["cart"]["total"] == 249.0
    # GET agrees
    assert client.get("/api/cart/s-basic").json()["total"] == 249.0


def test_amount_based_cheeni_weigh_instruction(client):
    r = say(client, "bees rupaye ki cheeni", "s-cheeni")
    line = r["cart"]["lines"][0]
    assert line["name"] == "Cheeni" and line["qty"] == 0.45
    assert line["weigh_instruction"] == "450 gram tolo"
    assert line["amount_rupees"] == 20.0 and line["line_total"] == 20.0
    assert "450 gram tolo" in r["spoken_text"]
    assert r["cart"]["total"] == 20.0
    co = client.post("/api/cart/s-cheeni/checkout", json={"rail": "simulated"}).json()
    assert co["total"] == 20.0
    inv = client.get(f"/api/invoices/{co['invoice_id']}").json()
    assert inv["total"] == 20.0 and inv["items"][0]["total"] == 20.0


def test_checkout_simulate_receipts_and_idempotence(client):
    say(client, PHRASE, "s-pay", customer_id=3)  # Sharma ji, has a phone
    assert stock(5) == 12
    mark = last_event_id()
    co = client.post("/api/cart/s-pay/checkout").json()
    assert co["total"] == 249.0 and co["complete"] is False and co["amount_due"] == 249.0
    assert co["upi_string"].startswith("upi://pay?pa=") and "am=249.00" in co["upi_string"]
    assert f"tr={co['order_id']}" in co["upi_string"] and "cu=INR" in co["upi_string"]
    assert round(co["taxable_total"] + co["cgst_total"] + co["sgst_total"], 2) == 249.0
    ck = store_events(mark, "checkout")
    assert ck and ck[0]["data"]["upi_string"] == co["upi_string"] and ck[0]["data"]["total"] == 249.0
    assert ck[0]["data"]["spoken_text"] and ck[0]["data"]["items"]

    order = co["order_id"]
    assert client.get(f"/api/payments/{order}").json()["status"] == "pending"
    assert client.get(f"/api/invoices/{co['invoice_id']}").json()["status"] == "pending"

    db = SessionLocal()
    msgs_before = db.query(Message).count()
    db.close()
    mark = last_event_id()
    sim = client.post(f"/api/payments/{order}/simulate").json()
    assert sim["ok"] and sim["already_paid"] is False
    assert sim["invoice_paid"] is True
    assert "₹249" in sim["spoken_text"] and "prapt hue" in sim["spoken_text"]
    assert any(item["name"] == "Colgate" and item["quantity"] == 8 for item in sim["low_stock"])
    assert stock(5) == 8
    inv = client.get(f"/api/invoices/{co['invoice_id']}").json()
    assert inv["status"] == "paid" and inv["payments"][0]["status"] == "success"

    pr = store_events(mark, "payment_received")
    assert len(pr) == 1 and pr[0]["data"]["amount"] == 249.0
    assert pr[0]["data"]["spoken_text"].startswith("₹249 prapt hue")

    db = SessionLocal()
    new = db.query(Message).order_by(Message.id.desc()).limit(db.query(Message).count() - msgs_before).all()
    db.close()
    types = sorted(m.type for m in new)
    assert types == ["audio", "text"] and all(m.customer_id == 3 for m in new)
    text = next(m for m in new if m.type == "text")
    assert inv["number"] in text.body and f"/r/{inv['public_token']}" in text.body
    audio = next(m for m in new if m.type == "audio")
    assert audio.body.startswith("Aapne 2 Maggi, 1 Surf Excel, 4 Colgate liya, kul ₹249")

    # second simulate is a no-op
    mark = last_event_id()
    again = client.post(f"/api/payments/{order}/simulate").json()
    assert again["already_paid"] is True
    assert stock(5) == 8
    assert not store_events(mark, "payment_received")
    db = SessionLocal()
    assert db.query(Message).count() == msgs_before + 2
    db.close()
    # checkout again on the same finished cart returns the same bill
    co2 = client.post("/api/cart/s-pay/checkout").json()
    assert co2["order_id"] == order and co2["idempotent"] is True


def test_public_receipt_page(client):
    inv = client.get("/api/invoices?limit=1").json()[0]
    r = client.get(f"/r/{inv['public_token']}")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    for needle in (inv["number"], "Tax Invoice", "CGST", "SGST", "Ramesh General Store",
                   "GST is worked out of the MRP", "Maggi"):
        assert needle in r.text
    assert client.get("/r/not-a-token").status_code == 404


def test_bill_of_supply_for_composition_store(client):
    from models import StoreProfile
    db = SessionLocal()
    db.query(StoreProfile).first().composition_scheme = True
    db.commit()
    db.close()
    try:
        say(client, "do maggi", "s-comp")
        co = client.post("/api/cart/s-comp/checkout").json()
        assert co["doc_type"] == "bill_of_supply" and co["total"] == 24.0
        inv = client.get(f"/api/invoices/{co['invoice_id']}").json()
        page = client.get(f"/r/{inv['public_token']}").text
        assert "Bill of Supply" in page and "CGST" not in page
    finally:
        db = SessionLocal()
        db.query(StoreProfile).first().composition_scheme = False
        db.commit()
        db.close()


def test_split_payment_cash_upi_khata(client):
    client.post("/api/cart/s-split/lines", json={"items": [{"product_id": 2, "qty": 2}]})  # 2 x Rice 5kg = 700
    assert client.get("/api/cart/s-split").json()["total"] == 700.0
    r = say(client, "300 cash 200 Paytm baaki khate mein", "s-split", customer_id=2)
    (action,) = r["actions"]
    assert action["kind"] == "split_payment" and action["status"] == "proposed"
    assert action["payload"]["parts"] == {"upi": 200.0, "cash": 300.0, "khata": 200.0}
    c = client.post(f"/api/actions/{action['id']}/confirm").json()
    res = c["result"]
    modes = sorted((p["mode"], p["amount"], p["status"]) for p in res["payments"])
    assert modes == [("cash", 300.0, "success"), ("khata", 200.0, "success"), ("upi", 200.0, "pending")]
    assert res["amount_due"] == 200.0 and res["complete"] is False
    db = SessionLocal()
    entries = db.query(KhataEntry).filter(KhataEntry.invoice_id == res["invoice_id"]).all()
    db.close()
    assert [(e.customer_id, e.amount) for e in entries] == [(2, 200.0)]
    # confirming again does not create a second bill
    again = client.post(f"/api/actions/{action['id']}/confirm").json()
    assert again["already_resolved"] is True
    # UPI part arrives -> invoice paid
    assert client.post(f"/api/payments/{res['order_id']}/simulate").json()["invoice_paid"] is True
    inv = client.get(f"/api/invoices/{res['invoice_id']}").json()
    assert inv["status"] == "paid" and len(inv["payments"]) == 3
    assert round(sum(p["amount"] for p in inv["payments"]), 2) == inv["total"] == 700.0


def test_cash_only_completes_immediately(client):
    say(client, "ek parle g", "s-cash")
    s = stock(9)
    co = client.post("/api/cart/s-cash/checkout", json={"splits": {"cash": 10}}).json()
    assert co["complete"] is True and co["upi_string"] is None
    assert client.get(f"/api/invoices/{co['invoice_id']}").json()["status"] == "paid"
    assert stock(9) == s - 1


def test_khata_part_needs_customer(client):
    say(client, "ek parle g", "s-nocust")
    r = client.post("/api/cart/s-nocust/checkout", json={"splits": {"khata": None}})
    assert r.status_code == 400
    assert client.get("/api/cart/s-nocust").json()["status"] == "open"


def bal(cid):
    db = SessionLocal()
    try:
        return db.query(Customer).get(cid).balance
    finally:
        db.close()


def test_udhaar_proposal_confirm_and_whatsapp(client):
    b0 = bal(2)
    r = say(client, "verma ji ke khate mein paanch sau", "s-udhaar")
    (action,) = r["actions"]
    assert action["kind"] == "add_udhaar" and action["status"] == "proposed"
    p = action["payload"]
    assert p["customer_id"] == 2 and p["amount"] == 500 and p["balance_before"] == b0
    assert p["balance_after"] == b0 + 500 and p["over_limit"] is True and p["late_payments"] == 3
    assert bal(2) == b0  # nothing committed yet
    done = client.post(f"/api/actions/{action['id']}/confirm").json()
    assert done["action"]["status"] == "confirmed" and done["result"]["balance"] == b0 + 500
    assert bal(2) == b0 + 500
    db = SessionLocal()
    msg = db.query(Message).filter(Message.customer_id == 2).order_by(Message.id.desc()).first()
    db.close()
    assert f"₹500 aapke khate mein jude. Kul baaki ₹{int(b0 + 500):,}." in msg.body


def test_khata_payment_by_voice(client):
    b0 = bal(2)
    r = say(client, "verma ji ne paanch sau diye", "s-khpay")
    (action,) = r["actions"]
    assert action["kind"] == "record_khata_payment" and action["payload"]["amount"] == 500
    client.post(f"/api/actions/{action['id']}/confirm")
    assert bal(2) == b0 - 500


def test_undo_pending_and_cart(client):
    say(client, "do maggi", "s-undo")
    r = say(client, "bas kitna hua", "s-undo")
    (action,) = r["actions"]
    assert action["kind"] == "checkout" and action["status"] == "proposed"
    # "galat hai" drops the pending checkout, the cart stays
    u = say(client, "galat hai", "s-undo")
    assert u["actions"][0]["id"] == action["id"] and u["actions"][0]["status"] == "cancelled"
    assert len(u["cart"]["lines"]) == 1
    # a second "galat hai" undoes the cart edit
    u2 = say(client, "galat hai", "s-undo")
    assert u2["cart"]["lines"] == []
    # nothing left to undo
    assert "kuch nahi" in say(client, "galat hai", "s-undo")["spoken_text"]


def test_voice_haan_confirms_checkout(client):
    say(client, "do maggi", "s-haan")
    say(client, "total kitna hua", "s-haan")
    r = say(client, "haan", "s-haan")
    assert r["actions"][0]["status"] == "confirmed"
    assert r["cart"]["status"] == "checked_out" and r["cart"]["invoice_id"]
    assert "24" in r["spoken_text"]


def test_missed_sale(client):
    r = say(client, "kurkure nahi hai", "s-miss")
    assert "Kurkure" in r["spoken_text"] and r["cart"]["lines"] == []
    db = SessionLocal()
    rows = db.query(MissedSale).filter(MissedSale.product_name == "Kurkure").count()
    db.close()
    assert rows >= 7  # six seeded + this one


def test_stock_context_restock(client):
    before = stock(1)
    r = say(client, "das packet maggi", "s-stock", context="stock")
    assert r["cart"]["lines"] == []
    (action,) = r["actions"]
    assert action["kind"] == "restock" and action["payload"]["items"][0]["quantity"] == 10
    assert stock(1) == before
    c = client.post(f"/api/actions/{action['id']}/confirm").json()
    assert c["result"]["updated"][0]["new_quantity"] == before + 10 == stock(1)


def test_fix_and_remove_by_voice_and_manual_edits(client):
    say(client, "teen maggi do colgate", "s-fix")
    r = say(client, "maggi teen nahi do", "s-fix")
    assert {ln["name"]: ln["qty"] for ln in r["cart"]["lines"]} == {"Maggi": 2, "Colgate": 2}
    r = say(client, "colgate ko ek kar do", "s-fix")
    assert {ln["name"]: ln["qty"] for ln in r["cart"]["lines"]} == {"Maggi": 2, "Colgate": 1}
    r = say(client, "colgate hata do", "s-fix")
    assert [ln["name"] for ln in r["cart"]["lines"]] == ["Maggi"] and "hata diya" in r["spoken_text"]
    # undo brings the removed line back
    assert len(say(client, "galat hai", "s-fix")["cart"]["lines"]) == 2
    # manual API
    client.put("/api/cart/s-fix/lines/1", json={"qty": 5})
    assert {ln["name"]: ln["qty"] for ln in client.get("/api/cart/s-fix").json()["lines"]}["Maggi"] == 5
    client.delete("/api/cart/s-fix/lines/5")
    assert [ln["name"] for ln in client.get("/api/cart/s-fix").json()["lines"]] == ["Maggi"]
    set_ = client.post("/api/cart/s-fix/lines", json={"mode": "set", "items": [{"name": "maggi", "qty": 0}]})
    assert set_.json()["lines"] == []
    assert client.post("/api/cart/s-fix/lines", json={"items": [{"name": "zzzzqq", "qty": 1}]}).status_code == 404
    assert client.delete("/api/cart/s-fix").json()["lines"] == []


def test_exact_rules_are_not_overwritten_by_llm(client, monkeypatch):
    async def wrong(messages, db, tools=None, context="counter", timeout=4.0):
        raise AssertionError("the LLM must not be asked when the rules fully understood")

    import services.counter as counter_mod
    monkeypatch.setattr(counter_mod.llm, "complete_or_rules", wrong)
    r = say(client, PHRASE, "s-sure")
    assert r["source"] != "sarvam" and len(r["cart"]["lines"]) == 3


def test_llm_handles_what_the_rules_do_not_understand(client, monkeypatch):
    async def fake(messages, db, tools=None, context="counter", timeout=4.0):
        calls = [ToolCall("add_to_cart", {"items": [{"name": "Maggi", "qty": 3}]}),
                 ToolCall("add_udhaar", {"customer": "Sharma ji", "amount": 100})]
        return Result(ChatOut(tool_calls=calls), "sarvam", 800)

    import services.counter as counter_mod
    monkeypatch.setattr(counter_mod.llm, "complete_or_rules", fake)
    r = say(client, "woh bachon wala kuch de do", "s-llm")
    assert r["source"] == "sarvam"
    assert [(ln["name"], ln["qty"]) for ln in r["cart"]["lines"]] == [("Maggi", 3)]
    assert r["actions"][0]["kind"] == "add_udhaar" and r["actions"][0]["source"] == "sarvam"
    # undo restores the pre-utterance cart (empty)
    say(client, "galat hai", "s-llm")  # cancels the udhaar proposal
    assert say(client, "galat hai", "s-llm")["cart"]["lines"] == []


def test_llm_failure_keeps_rules_result(client, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")

    import services.counter as counter_mod
    monkeypatch.setattr(counter_mod.llm, "complete_or_rules", boom)
    r = say(client, "ek patanjali shahad do colgate", "s-boom")
    assert [(ln["name"], ln["qty"]) for ln in r["cart"]["lines"]] == [("Patanjali Honey", 1), ("Colgate", 2)]


def test_audio_upload_with_demo_phrase(client):
    r = client.post("/api/agent/utterance", files={"audio": ("a.webm", b"xx", "audio/webm")},
                    data={"session_id": "s-audio"}, headers={"X-Demo-Phrase": "5"}).json()
    assert r["stt_source"] == "fixture" and r["demo_mode"] is True
    assert [ln["name"] for ln in r["cart"]["lines"]] == ["Patanjali Honey", "Colgate"]
    assert client.post("/api/agent/utterance", data={"session_id": "x"}).status_code == 422
    assert client.post("/api/agent/utterance", data={"text": "x", "context": "bad"}).status_code == 422


def test_usual_basket(client):
    u = client.get("/api/cart/usual/3").json()
    assert u["customer"]["name"] == "Sharma ji" and len(u["lines"]) == 3 and u["total"] > 0
    by_upi = client.get("/api/cart/usual", params={"upi_id": "sharma.ji@paytm"}).json()
    assert by_upi["customer"]["id"] == 3
    assert client.get("/api/cart/usual", params={"upi_id": "nobody@x"}).status_code == 404
    att = client.post("/api/cart/s-usual/customer", json={"upi_id": "kapoor.family@paytm"}).json()
    assert att["customer"]["name"] == "Mrs. Kapoor" and att["usual"]["lines"]
    cart = client.post("/api/cart/s-usual/usual").json()
    assert cart["customer_id"] == 4 and len(cart["lines"]) == 4
    # by voice
    r = say(client, "sharma ji ka usual", "s-usual2")
    assert len(r["cart"]["lines"]) == 3 and r["cart"]["customer_id"] == 3


def test_webhook_marks_paid(client):
    say(client, "ek parle g", "s-hook")
    co = client.post("/api/cart/s-hook/checkout").json()
    bad = client.post("/api/payments/webhook", json={"order_id": co["order_id"], "status": "SUCCESS",
                                                     "amount": 99})
    assert bad.status_code == 422
    ok = client.post("/api/payments/webhook", json={"ORDERID": co["order_id"], "STATUS": "TXN_SUCCESS",
                                                    "TXNAMOUNT": "10.00"}).json()
    assert ok["ok"] and ok["invoice_paid"] is True
    assert client.get(f"/api/payments/{co['order_id']}").json()["status"] == "success"
    assert client.post("/api/payments/webhook", json={"status": "SUCCESS"}).status_code == 422
    assert client.get("/api/payments/NOPE").status_code == 404


def test_invoice_send_and_list(client):
    rows = client.get("/api/invoices?limit=5").json()
    assert rows and {"number", "public_url", "items", "payments"} <= set(rows[0])
    inv = next(r for r in client.get("/api/invoices?limit=50&customer_id=3").json())
    sent = client.post(f"/api/invoices/{inv['id']}/send").json()
    assert [m["type"] for m in sent["messages"]] == ["text", "audio"]
    walkin = client.get("/api/invoices?limit=50").json()
    no_phone = next(i for i in walkin if i["customer_id"] in (None, 1))
    assert client.post(f"/api/invoices/{no_phone['id']}/send").status_code == 400
    assert client.post(f"/api/invoices/{no_phone['id']}/send", json={"to": "919999999999", "voice": False}
                       ).json()["messages"][0]["to"] == "919999999999"
    assert client.get("/api/invoices/99999999").status_code == 404


def test_actions_listing_and_cancel(client):
    r = say(client, "verma ji ke khate mein sau", "s-act")
    aid = r["actions"][0]["id"]
    listed = client.get("/api/actions", params={"session_id": "s-act", "status": "proposed"}).json()
    assert [a["id"] for a in listed] == [aid]
    assert client.get(f"/api/actions/{aid}").json()["kind"] == "add_udhaar"
    assert client.post(f"/api/actions/{aid}/cancel").json()["action"]["status"] == "cancelled"
    assert client.post(f"/api/actions/{aid}/confirm").status_code == 409
    assert client.post("/api/actions/99999/confirm").status_code == 404


def test_all_store_events_are_json_serialisable():
    import json
    evs = events.bus.replay("store", 0)
    assert {"cart_updated", "utterance"} <= {e["type"] for e in evs}
    for e in evs:
        json.dumps(e["data"])
        assert events.format_sse(e).startswith("id: ")
