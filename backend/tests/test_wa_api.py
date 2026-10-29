"""WhatsApp: Meta delivery (mocked httpx), webhook signature + payloads, inbound routing, simulator.
No provider keys, no real network."""
import asyncio
import dataclasses
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import main
import seed as seed_module
from models import KhataEntry, Message, PendingAction
from routers import whatsapp as wa_router
from services import events, http
from services import khata as kh
from services import wa_orders
from services import whatsapp as wa

VERMA, VERMA_PHONE = 2, "919810000002"


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c
    seed_module.seed(reset=True, verbose=False)


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    """No threads, no leftover mock transport."""
    monkeypatch.setattr(wa, "_schedule", lambda _mid: None)
    monkeypatch.setattr(http, "TRANSPORT", None)
    wa.STATE.update(last_error=None, last_error_at=None)


def set_settings(monkeypatch, **kw):
    new = dataclasses.replace(wa.settings, **kw)
    for module in (wa, wa_router, wa_orders, kh):
        monkeypatch.setattr(module, "settings", new)
    return new


def mock_graph(monkeypatch, handler):
    monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(handler))


def _events(channel, type_):
    return [e for e in events.bus.replay(channel, 0) if e["type"] == type_]


def _sign(secret: str, raw: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def text_payload(text, sender=VERMA_PHONE, wamid="wamid.IN1"):
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": sender, "profile": {"name": "Verma"}}],
        "messages": [{"from": sender, "id": wamid, "type": "text", "text": {"body": text}}]}}]}]}


def give_udhaar(client, customer_id=VERMA, amount=100):
    return client.post("/api/khata/entries", json={"customer_id": customer_id, "amount": amount}).json()


# --- sim only ---------------------------------------------------------------------


def test_notify_is_sim_only_without_keys(client, db, monkeypatch):
    scheduled = []
    monkeypatch.setattr(wa, "_schedule", scheduled.append)
    msg = wa.notify(db, VERMA_PHONE, "hello", customer_id=VERMA)
    db.commit()
    assert msg.channel == "sim" and msg.status == "delivered" and scheduled == []
    assert asyncio.run(wa.deliver(msg.id)) is False  # keys absent: no-op, no network
    assert wa.normalize_phone("98100 00002") == VERMA_PHONE and wa.e164("09810000002") == "+919810000002"
    assert wa.normalize_phone("abc") is None and wa.same_phone("+91 98100-00002", VERMA_PHONE)


# --- Meta delivery (mocked) -------------------------------------------------------


def test_meta_text_send_payload(client, db, monkeypatch):
    set_settings(monkeypatch, wa_token="TOKEN123", wa_phone_number_id="555")
    scheduled = []
    monkeypatch.setattr(wa, "_schedule", scheduled.append)
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, json={"messages": [{"id": "wamid.OUT1"}]})

    mock_graph(monkeypatch, handler)
    body = give_udhaar(client)
    mid = body["whatsapp"]["message_id"]
    assert scheduled == [mid] and body["entry"]["wa_status"] == "queued"  # delivery follows the commit
    assert asyncio.run(wa.deliver(mid)) is True
    req = seen[0]
    assert str(req.url) == "https://graph.facebook.com/v21.0/555/messages"
    assert req.headers["authorization"] == "Bearer TOKEN123"
    sent = json.loads(req.content)
    assert sent["messaging_product"] == "whatsapp" and sent["to"] == VERMA_PHONE and sent["type"] == "text"
    assert "Galat ho toh reply karein" in sent["text"]["body"]
    db.expire_all()
    m = db.get(Message, mid)
    assert (m.channel, m.wa_id, m.status) == ("wa", "wamid.OUT1", "sent")
    entry = db.get(KhataEntry, body["entry"]["id"])
    assert entry.wa_status == "sent"
    assert _events("wa", "wa_status")[-1]["data"] == {"id": mid, "status": "sent", "channel": "wa",
                                                      "wa_id": "wamid.OUT1", "error": None}
    assert wa.status_summary(db)["configured"] is True
    assert asyncio.run(wa.deliver(mid)) is False  # already sent: not sent twice
    assert len(seen) == 1


def test_background_thread_delivery_after_commit(client, db, monkeypatch):
    """The real scheduler (no test override): the send happens on a thread after the request commits."""
    import time

    set_settings(monkeypatch, wa_token="T", wa_phone_number_id="555")
    monkeypatch.setattr(wa, "_schedule", wa._run_in_thread)
    mock_graph(monkeypatch, lambda req: httpx.Response(200, json={"messages": [{"id": "wamid.BG"}]}))
    mid = give_udhaar(client, amount=2)["whatsapp"]["message_id"]
    for _ in range(50):
        db.expire_all()
        if db.get(Message, mid).status == "sent":
            break
        time.sleep(0.1)
    assert db.get(Message, mid).wa_id == "wamid.BG"


def test_window_closed_marks_failed_and_keeps_sim_copy(client, db, monkeypatch):
    set_settings(monkeypatch, wa_token="T", wa_phone_number_id="555")
    mock_graph(monkeypatch, lambda req: httpx.Response(400, json={"error": {
        "code": 131047, "message": "Re-engagement message"}}))
    mid = give_udhaar(client)["whatsapp"]["message_id"]
    assert asyncio.run(wa.deliver(mid)) is False
    db.expire_all()
    m = db.get(Message, mid)
    assert m.status == "failed" and m.channel == "sim"
    assert "24-hour window" in wa.error_for(mid) and "24-hour window" in wa.STATE["last_error"]
    assert _events("wa", "wa_status")[-1]["data"]["error"].startswith("24-hour window")
    api = client.get("/api/wa/messages", params={"since_id": mid - 1}).json()
    assert api[0]["status"] == "failed" and "24-hour window" in api[0]["error"]
    assert "24-hour window" in client.get("/api/wa/status").json()["last_error"]


def test_network_error_never_raises(client, db, monkeypatch):
    set_settings(monkeypatch, wa_token="T", wa_phone_number_id="555")

    def boom(req):
        raise httpx.ConnectError("no route")

    mock_graph(monkeypatch, boom)
    mid = give_udhaar(client)["whatsapp"]["message_id"]
    assert asyncio.run(wa.deliver(mid)) is False
    db.expire_all()
    assert db.get(Message, mid).status == "failed" and "ConnectError" in wa.error_for(mid)
    assert asyncio.run(wa.deliver(999999)) is False  # unknown id: still no raise


def test_no_phone_means_sim_only(client, db, monkeypatch):
    set_settings(monkeypatch, wa_token="T", wa_phone_number_id="555")
    scheduled = []
    monkeypatch.setattr(wa, "_schedule", scheduled.append)
    r = client.post("/api/khata/entries", json={"customer_id": 5, "amount": 10}).json()  # Singh sahab: no phone
    assert scheduled == [] and r["entry"]["wa_status"] == "sent"


def test_audio_media_is_uploaded_then_sent_by_id(client, db, monkeypatch, tmp_path):
    set_settings(monkeypatch, wa_token="T", wa_phone_number_id="555")
    audio = tmp_path / "receipt.mp3"
    audio.write_bytes(b"ID3fake")
    calls = []

    def handler(req: httpx.Request):
        calls.append((req.url.path, req.content))
        if req.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "MEDIA77"})
        return httpx.Response(200, json={"messages": [{"id": "wamid.A"}]})

    mock_graph(monkeypatch, handler)
    msg = wa.notify(db, VERMA_PHONE, "voice receipt", type="audio", customer_id=VERMA, media_ref=str(audio))
    db.commit()
    assert asyncio.run(wa.deliver(msg.id)) is True
    assert calls[0][0].endswith("/555/media") and b"ID3fake" in calls[0][1] and b"audio/mpeg" in calls[0][1]
    assert json.loads(calls[1][1])["audio"] == {"id": "MEDIA77"}
    img = wa.notify(db, VERMA_PHONE, "dekho", type="image", customer_id=VERMA,
                    media_ref="https://example.com/a.jpg")
    db.commit()
    assert asyncio.run(wa.deliver(img.id)) is True
    assert json.loads(calls[2][1])["image"] == {"link": "https://example.com/a.jpg", "caption": "dekho"}


# --- webhook ------------------------------------------------------------------------


def test_webhook_verify(client):
    ok = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "awaaz-verify",
                                                  "hub.challenge": "1234"})
    assert ok.status_code == 200 and ok.text == "1234"
    assert client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "bad",
                                                    "hub.challenge": "1"}).status_code == 403


def test_signature_checked_when_secret_set(client, db, monkeypatch):
    set_settings(monkeypatch, wa_app_secret="s3cret")
    raw = json.dumps(text_payload("galat hai")).encode()
    assert client.post("/webhooks/whatsapp", content=raw).status_code == 403
    assert client.post("/webhooks/whatsapp", content=raw,
                       headers={"X-Hub-Signature-256": "sha256=" + "0" * 64}).status_code == 403
    before = db.query(Message).filter_by(direction="in").count()
    assert db.query(Message).filter_by(direction="in").count() == before
    good = client.post("/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": _sign("s3cret", raw),
                                                                   "Content-Type": "application/json"})
    assert good.status_code == 200 and good.json()["messages"] == 1
    db.expire_all()
    assert db.query(Message).filter_by(direction="in").count() == before + 1


def test_no_secret_allows_unsigned_and_bad_json(client):
    assert client.post("/webhooks/whatsapp", json={"entry": []}).status_code == 200
    assert client.post("/webhooks/whatsapp", content=b"{nope").status_code == 400


def test_inbound_galat_marks_latest_entry_disputed(client, db):
    entry_id = give_udhaar(client, amount=120)["entry"]["id"]
    n_before = len(_events("store", "khata_disputed"))
    r = client.post("/webhooks/whatsapp", json=text_payload("galat hai", wamid="wamid.G1"))
    assert r.status_code == 200
    db.expire_all()
    e = db.get(KhataEntry, entry_id)
    assert kh.is_disputed(e) and e.confirmed_by_customer is False and "galat hai" in e.note
    ev = _events("store", "khata_disputed")
    assert len(ev) == n_before + 1 and ev[-1]["data"]["entry_id"] == entry_id
    assert ev[-1]["data"]["customer"] == "Verma ji"
    inbound = [x for x in _events("wa", "wa_message") if x["data"].get("direction") == "in"][-1]["data"]
    assert inbound["body"] == "galat hai" and inbound["customer_id"] == VERMA
    reply = db.query(Message).filter_by(direction="out").order_by(Message.id.desc()).first()
    assert "note kar liya" in reply.body
    assert client.get("/api/khata/customers/2").json()["disputed_entries"] >= 1
    # a Meta retry of the same message id is ignored
    client.post("/webhooks/whatsapp", json=text_payload("galat hai", wamid="wamid.G1"))
    db.expire_all()
    assert db.query(Message).filter_by(wa_id="wamid.G1").count() == 1


def test_inbound_sahi_confirms(client, db):
    entry_id = give_udhaar(client, amount=60)["entry"]["id"]
    out = client.post("/api/wa/simulate-inbound", json={"from_phone": VERMA_PHONE, "type": "text",
                                                        "body": "Haan sahi hai"}).json()
    assert out["routed"] == "khata_confirm" and out["simulated"] is True
    db.expire_all()
    assert db.get(KhataEntry, entry_id).confirmed_by_customer is True
    assert _events("store", "khata_confirmed")[-1]["data"]["entry_id"] == entry_id


def test_status_receipts_update_messages(client, db, monkeypatch):
    mid = give_udhaar(client, amount=1)["whatsapp"]["message_id"]
    db.get(Message, mid).wa_id = "wamid.RCPT"
    db.commit()
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.RCPT", "status": "delivered"}]}}]}]}
    assert client.post("/webhooks/whatsapp", json=payload).json()["statuses"] == 1
    db.expire_all()
    assert db.get(Message, mid).status == "delivered"
    payload["entry"][0]["changes"][0]["value"]["statuses"][0] = {
        "id": "wamid.RCPT", "status": "failed", "errors": [{"code": 131047, "title": "Re-engagement"}]}
    client.post("/webhooks/whatsapp", json=payload)
    db.expire_all()
    assert db.get(Message, mid).status == "failed" and "24-hour" in wa.error_for(mid)


# --- F13: voice / photo / text orders -------------------------------------------------


def test_simulated_audio_order_creates_wa_order_and_packing_list(client, db):
    r = client.post("/api/wa/simulate-inbound",
                    files={"file": ("voice.ogg", b"OggSfake", "audio/ogg")},
                    data={"from_phone": "919810000004", "type": "audio"})  # Mrs. Kapoor
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["routed"] == "wa_order" and out["transcript"] == "do maggi ek surf excel chaar colgate"
    assert out["total"] == 249 and [l["qty"] for l in out["lines"]] == [2, 1, 4]
    db.expire_all()
    action = db.get(PendingAction, out["action_id"])
    assert action.kind == "wa_order" and action.status == "proposed" and action.source == "fixture"
    assert action.payload["customer"] == "Mrs. Kapoor" and action.payload["total"] == 249
    reply = db.get(Message, out["reply_message_id"])
    assert reply.direction == "out" and reply.to == "919810000004"
    assert "Maggi x 2 packet" in reply.body and "Kul: ₹249" in reply.body
    assert "upi://pay?pa=paytm.merchant%40paytm" in reply.body and "am=249.00" in reply.body
    ev = _events("store", "wa_order")[-1]["data"]
    assert ev["action_id"] == action.id and ev["total"] == 249 and ev["input_type"] == "audio"
    inbound = db.query(Message).filter_by(direction="in", type="audio").order_by(Message.id.desc()).first()
    assert inbound.body == out["transcript"] and inbound.media_ref.startswith("/api/wa/media/")
    assert client.get(inbound.media_ref).content == b"OggSfake"
    assert client.get("/api/wa/media/..%2Fx").status_code == 404
    assert [o["id"] for o in client.get("/api/wa/orders").json()][0] == action.id


def test_audio_transcript_passthrough_and_demo_phrase(client):
    a = client.post("/api/wa/simulate-inbound", json={"from_phone": VERMA_PHONE, "type": "audio",
                                                      "body": "paanch dettol sabun teen vim bar"}).json()
    assert a["routed"] == "wa_order" and a["total"] == 5 * 35 + 3 * 15
    b = client.post("/api/wa/simulate-inbound", json={"from_phone": VERMA_PHONE, "type": "audio",
                                                      "demo_phrase": "5"}).json()
    assert [l["name"] for l in b["lines"]] == ["Patanjali Honey", "Colgate"]


def test_image_parchi_order(client):
    out = client.post("/api/wa/simulate-inbound", files={"file": ("p.jpg", b"\xff\xd8x", "image/jpeg")},
                      data={"from_phone": VERMA_PHONE, "type": "image"}).json()
    assert out["routed"] == "wa_order"
    names = {l["name"] for l in out["lines"]}
    assert {"Cheeni", "Maggi", "Surf Excel"} <= names and out["total"] > 0


def test_text_order_and_greeting_and_unrecognized(client):
    t = client.post("/api/wa/simulate-inbound", json={"from_phone": "9876500000", "type": "text",
                                                      "body": "do maggi aur ek colgate bhej do"}).json()
    assert t["routed"] == "wa_order" and t["customer_id"] is None and t["total"] == 24 + 45
    assert client.post("/api/wa/simulate-inbound", json={"from_phone": VERMA_PHONE, "type": "text",
                                                         "body": "hi"}).json()["routed"] == "greeting"
    assert client.post("/api/wa/simulate-inbound", json={"from_phone": VERMA_PHONE, "type": "text",
                                                         "body": "kal milte hain"}).json()["routed"] == "stored"
    assert client.post("/api/wa/simulate-inbound", json={"from_phone": VERMA_PHONE, "type": "audio",
                                                         "body": "namaste ji"}).json()["routed"] == "unrecognized"


def test_webhook_audio_downloads_media_and_routes_like_simulator(client, db, monkeypatch):
    set_settings(monkeypatch, wa_token="T", wa_phone_number_id="555")
    seen = []

    def handler(req: httpx.Request):
        seen.append(str(req.url))
        assert req.headers["authorization"] == "Bearer T"
        if req.url.host == "graph.facebook.com":
            return httpx.Response(200, json={"url": "https://lookaside.fbsbx.com/m/1", "mime_type": "audio/ogg"})
        return httpx.Response(200, content=b"OGGDATA")

    mock_graph(monkeypatch, handler)
    payload = {"entry": [{"changes": [{"value": {"messages": [{
        "from": "919810000004", "id": "wamid.AUD1", "type": "audio",
        "audio": {"id": "MEDIA1", "mime_type": "audio/ogg; codecs=opus"}}]}}]}]}
    assert client.post("/webhooks/whatsapp", json=payload).status_code == 200
    assert seen == ["https://graph.facebook.com/v21.0/MEDIA1", "https://lookaside.fbsbx.com/m/1"]
    db.expire_all()
    inbound = db.query(Message).filter_by(wa_id="wamid.AUD1").one()
    assert inbound.channel == "wa" and inbound.type == "audio" and inbound.body.startswith("do maggi")
    action = db.query(PendingAction).filter_by(kind="wa_order").order_by(PendingAction.id.desc()).first()
    assert action.payload["total"] == 249 and action.payload["input_type"] == "audio"
    sim = client.post("/api/wa/simulate-inbound", data={"from_phone": "919810000004", "type": "audio"},
                      files={"file": ("v.ogg", b"OGGDATA", "audio/ogg")}).json()
    assert sim["routed"] == "wa_order" and sim["total"] == action.payload["total"]


def test_webhook_failed_media_download_is_survivable(client, db, monkeypatch):
    set_settings(monkeypatch, wa_token="T", wa_phone_number_id="555")
    mock_graph(monkeypatch, lambda req: httpx.Response(404, json={"error": {"message": "gone"}}))
    payload = {"entry": [{"changes": [{"value": {"messages": [{
        "from": VERMA_PHONE, "id": "wamid.BAD", "type": "image", "image": {"id": "M2", "caption": "list"}}]}}]}]}
    assert client.post("/webhooks/whatsapp", json=payload).status_code == 200
    db.expire_all()
    assert "could not be downloaded" in db.query(Message).filter_by(wa_id="wamid.BAD").one().body


def test_interactive_button_reply_routes_as_dispute(client, db):
    give_udhaar(client, amount=33)
    payload = {"entry": [{"changes": [{"value": {"messages": [{
        "from": VERMA_PHONE, "id": "wamid.BTN", "type": "interactive",
        "interactive": {"button_reply": {"id": "khata_wrong", "title": "Galat"}}}]}}]}]}
    n = len(_events("store", "khata_disputed"))
    client.post("/webhooks/whatsapp", json=payload)
    assert len(_events("store", "khata_disputed")) == n + 1


# --- order lifecycle and simulator endpoints ----------------------------------------------


def test_order_confirm_and_cancel(client, db):
    ids = [client.post("/api/wa/simulate-inbound", json={"from_phone": VERMA_PHONE, "type": "text",
                                                         "body": "teen maggi"}).json()["action_id"] for _ in range(2)]
    ok = client.post(f"/api/wa/orders/{ids[0]}/confirm").json()
    assert ok["status"] == "confirmed"
    assert client.post(f"/api/wa/orders/{ids[0]}/cancel").status_code == 409
    assert client.post(f"/api/wa/orders/{ids[1]}/cancel").json()["status"] == "cancelled"
    assert _events("store", "wa_order_updated")[-1]["data"]["status"] == "cancelled"
    assert client.post("/api/wa/orders/999999/confirm").status_code == 404
    assert all(o["status"] == "proposed" for o in client.get("/api/wa/orders", params={"status": "proposed"}).json())


def test_messages_conversations_send_status(client, db):
    sent = client.post("/api/wa/send", json={"customer_id": 4, "body": "Aapka maal ready hai"}).json()
    assert sent["to"] == "919810000004" and sent["direction"] == "out" and sent["customer_id"] == 4
    assert client.post("/api/wa/send", json={"customer_id": 4}).status_code == 422
    assert client.post("/api/wa/send", json={"customer_id": 999, "body": "x"}).status_code == 404
    msgs = client.get("/api/wa/messages", params={"customer_id": 4}).json()
    assert msgs == sorted(msgs, key=lambda m: m["id"]) and msgs[-1]["id"] == sent["id"]
    assert client.get("/api/wa/messages", params={"since_id": sent["id"]}).json() == []
    by_phone = client.get("/api/wa/messages", params={"phone": "+91 98100 00004"}).json()
    assert {m["customer_id"] for m in by_phone} == {4}
    convs = client.get("/api/wa/conversations").json()
    kapoor = next(c for c in convs if c["customer_id"] == 4)
    assert kapoor["name"] == "Mrs. Kapoor" and kapoor["count"] == len(msgs) and kapoor["inbound_count"] >= 1
    assert any(c["key"].startswith("p") for c in convs)  # the unknown-number text order
    assert convs == sorted(convs, key=lambda c: -c["last_id"])
    outbox = client.get("/api/wa/outbox").json()
    assert outbox and all(m["direction"] == "out" for m in outbox)
    st = client.get("/api/wa/status").json()
    assert st["configured"] is False and st["mode"] == "simulator"
    assert st["webhook_url"].endswith("/webhooks/whatsapp") and st["outbox_total"] > 0


def test_simulate_inbound_validation(client):
    assert client.post("/api/wa/simulate-inbound", json={"type": "text", "body": "x"}).status_code == 422
    assert client.post("/api/wa/simulate-inbound", json={"from_phone": "1", "type": "video"}).status_code == 422
    assert client.post("/api/wa/simulate-inbound", json={"from_phone": VERMA_PHONE, "type": "text"}).status_code == 422
    assert client.post("/api/wa/simulate-inbound", json={"customer_id": 5, "type": "text",
                                                         "body": "x"}).status_code == 422  # no phone on file
    r = client.post("/api/wa/simulate-inbound", json={"customer_id": VERMA, "type": "text", "body": "do maggi"})
    assert r.json()["routed"] == "wa_order" and r.json()["customer_id"] == VERMA
