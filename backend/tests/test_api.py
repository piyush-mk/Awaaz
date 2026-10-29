"""Legacy endpoints keep their shapes; Phase 1 stubs answer 501."""
import pytest
from fastapi.testclient import TestClient

import main
import seed as seed_module


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c
    seed_module.seed(reset=True, verbose=False)  # undo mutations for other modules


def test_root_and_health(client):
    assert client.get("/").json()["status"] == "ok"
    assert client.get("/health").json() == {"status": "healthy"}


def test_inventory_shape(client):
    rows = client.get("/api/inventory").json()
    assert len(rows) == 40
    assert set(rows[0]) == {"product_id", "name", "name_hi", "category", "unit", "price", "gst_rate",
                            "quantity", "threshold", "status"}
    colgate = next(r for r in rows if r["name"] == "Colgate")
    assert colgate["quantity"] == 12 and colgate["price"] == 45


def test_alerts_and_dashboard_without_fake_offset(client):
    alerts = client.get("/api/alerts").json()
    assert alerts["count"] == 3
    assert {a["name"] for a in alerts["alerts"]} == {"Tata Salt", "Aashirvaad Atta 5kg", "Vim Bar"}
    dash = client.get("/api/dashboard").json()
    assert set(dash) == {"total_stock_value", "today_sales", "low_stock_count", "top_selling",
                         "recent_transactions"}
    assert dash["today_sales"] == 7270.0 and dash["low_stock_count"] == 3
    assert len(dash["top_selling"]) == 5 and len(dash["recent_transactions"]) == 20


def test_transactions_shape(client):
    rows = client.get("/api/transactions?limit=3").json()
    assert len(rows) == 3
    assert set(rows[0]) == {"id", "product_id", "product_name", "product_name_hi", "quantity_change",
                            "type", "amount", "timestamp"}


def test_voice_parse_text_and_demo_phrase(client):
    r = client.post("/api/voice/parse", data={"transcript": "do maggi ek surf excel chaar colgate"}).json()
    assert set(r) >= {"transcript", "items", "demo_mode"}
    assert [(i["name"], i["quantity"]) for i in r["items"]] == [("Maggi", 2), ("Surf Excel", 1), ("Colgate", 4)]
    r2 = client.post("/api/voice/parse", files={"audio": ("a.webm", b"xx", "audio/webm")},
                     headers={"X-Demo-Phrase": "5"}).json()
    assert r2["demo_mode"] is True
    assert [(i["name"], i["quantity"]) for i in r2["items"]] == [("Patanjali Honey", 1), ("Colgate", 2)]
    assert client.post("/api/voice/parse").status_code == 422


def test_tts_falls_back_to_empty_audio(client):
    r = client.post("/api/voice/tts", json={"text": "Bill ban gaya"}).json()
    assert r["audio_base64"] == "" and r["text"] == "Bill ban gaya"
    assert client.get("/api/voice/tts/../../etc.mp3").status_code == 404
    assert client.get("/api/voice/tts/" + "0" * 32 + ".mp3").status_code == 404


def test_photo_parse_demo(client):
    r = client.post("/api/photo/parse", files={"image": ("s.jpg", b"img", "image/jpeg")}).json()
    assert r["demo_mode"] is True
    assert {i["name"] for i in r["items"]} == {"Maggi", "Parle-G", "Colgate", "Surf Excel"}


def test_bill_generate_is_mrp_inclusive_249(client):
    items = client.post("/api/voice/parse", data={"transcript": "do maggi ek surf excel chaar colgate"}).json()["items"]
    bill = client.post("/api/bill/generate", json=items).json()
    assert bill["grand_total"] == 249.0
    assert round(bill["subtotal"] + bill["total_gst"], 2) == 249.0
    assert bill["upi_string"].startswith("upi://pay?pa=") and "am=249.00" in bill["upi_string"]
    assert set(bill["items"][0]) == {"product_id", "name", "name_hi", "quantity", "unit", "unit_price",
                                     "subtotal", "gst_rate", "gst_amount", "total"}
    assert client.post("/api/bill/generate", json=[{**items[0], "product_id": 999}]).status_code == 404


def test_bill_confirm_deducts_stock_and_counts_sale(client):
    before = client.get("/api/dashboard").json()["today_sales"]
    items = client.post("/api/voice/parse", data={"transcript": "do maggi ek surf excel chaar colgate"}).json()["items"]
    bill = client.post("/api/bill/generate", json=items).json()
    done = client.post("/api/bill/confirm", json={"items": bill["items"], "grand_total": bill["grand_total"]})
    assert done.status_code == 200
    body = done.json()
    assert body["success"] and body["grand_total"] == 249.0
    assert {s["name"]: s["new_quantity"] for s in body["updated_stock"]} == {
        "Maggi": 10, "Surf Excel": 14, "Colgate": 8}
    assert client.get("/api/dashboard").json()["today_sales"] == before + 249


def test_confirm_rejects_oversell(client):
    items = client.post("/api/voice/parse", data={"transcript": "das tata namak"}).json()["items"]
    bill = client.post("/api/bill/generate", json=items).json()
    r = client.post("/api/bill/confirm", json={"items": bill["items"], "grand_total": bill["grand_total"]})
    assert r.status_code == 400 and "Insufficient stock" in r.json()["detail"]


def test_restock_and_manual_edit(client):
    items = client.post("/api/voice/parse", data={"transcript": "das packet maggi"}).json()["items"]
    r = client.post("/api/inventory/restock", json={"items": items}).json()
    assert r["success"] and r["updated"][0]["new_quantity"] == r["updated"][0]["old_quantity"] + 10
    e = client.put("/api/inventory/4", json={"quantity": 20}).json()
    assert e["new_quantity"] == 20 and e["status"] == "high"
    assert client.put("/api/inventory/9999", json={"quantity": 1}).status_code == 404


def test_add_product(client):
    r = client.post("/api/inventory/add-product", json={"name": "Lays Magic Masala", "quantity": 12,
                                                       "unit": "packet", "price": 20, "gst_rate": 12}).json()
    assert r["success"] and r["quantity"] == 12


@pytest.mark.parametrize("method,path", [
    ("post", "/api/agent/utterance"), ("post", "/api/cart"), ("get", "/api/cart/abc"),
    ("post", "/api/cart/abc/checkout"), ("post", "/api/payments/ORD1/simulate"),
    ("get", "/api/invoices"), ("get", "/r/sometoken"), ("get", "/api/khata/customers"),
    ("post", "/webhooks/whatsapp"), ("get", "/api/wa/outbox"), ("post", "/api/purchases/scan"),
    ("post", "/api/galla/scan"), ("get", "/api/brief/today"), ("post", "/api/reorder/draft"),
    ("get", "/api/stock/cover"), ("post", "/api/actions/1/confirm"), ("post", "/api/ask"),
])
def test_phase1_stubs_return_501(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 501
    assert "not implemented" in r.json()["detail"].lower()


def test_whatsapp_verify_handshake(client):
    ok = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "awaaz-verify",
                                                  "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                   "hub.challenge": "42"})
    assert bad.status_code == 403


def test_admin_health_skeleton(client):
    h = client.get("/api/admin/health").json()
    assert h["status"] == "ok" and h["demo_mode"] == "on"
    assert h["db"]["products"] >= 40
    assert h["providers"]["sarvam"] == {"configured": False, "mode": "fixture"}
    assert h["providers"]["whatsapp"]["mode"] == "simulator"


def test_cors_allows_localhost_5173(client):
    r = client.options("/api/inventory", headers={"Origin": "http://localhost:5173",
                                                  "Access-Control-Request-Method": "GET"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_reset_demo_restores_numbers(client):
    r = client.post("/api/admin/reset-demo").json()
    assert r["seeded"] is True
    assert client.get("/api/dashboard").json()["today_sales"] == 7270.0
