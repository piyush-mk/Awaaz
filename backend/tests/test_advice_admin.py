"""Admin: provider health (no key leaks), status, demo checklist and reset-demo."""
import base64
import json

import httpx
import pytest

from routers import admin
from services import events, health, http, llm, openrouter, sarvam
from tests.test_advice_common import make_client_fixture, settings_with

client = make_client_fixture()

SECRETS = ["sk-SECRET-sarvam", "or-SECRET-openrouter", "wa-SECRET-token", "wa-SECRET-app"]
KEYED = dict(sarvam_api_key=SECRETS[0], openrouter_api_key=SECRETS[1], wa_token=SECRETS[2],
             wa_phone_number_id="1234567890", wa_app_secret=SECRETS[3], demo_mode="auto")


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    health.reset()
    monkeypatch.setattr(http, "TRANSPORT", None)
    yield
    health.reset()
    monkeypatch.setattr(http, "TRANSPORT", None)


def use_settings(monkeypatch, **kw):
    s = settings_with(**kw)
    for mod in (health, admin, sarvam, llm, openrouter):
        monkeypatch.setattr(mod, "settings", s)
    return s


def test_health_demo_mode_on(client):
    j = client.get("/api/admin/health").json()
    assert j["status"] == "ok" and j["demo_mode"] == "on" and j["live_checked"] is False
    states = {n: s["state"] for n, s in j["services"].items()}
    assert states["db"] == "live"
    assert all(v == "fixture" for n, v in states.items() if n != "db")
    assert j["services"]["whatsapp"]["effective"] == "simulator"
    assert j["providers"]["sarvam"] == {"configured": False, "mode": "fixture"}  # legacy block kept
    assert j["db"]["products"] == 40
    # DEMO_MODE=on never pings, even with ?live=1
    assert client.get("/api/admin/health", params={"live": 1}).json()["pinged"] == ["db"]


def test_health_missing_keys_in_auto_mode(client, monkeypatch):
    use_settings(monkeypatch, sarvam_api_key="", openrouter_api_key="", wa_token="", demo_mode="auto")
    j = client.get("/api/admin/health", params={"live": 1}).json()
    assert j["pinged"] == ["db"]  # no keys: nothing external is called
    states = {n: s["state"] for n, s in j["services"].items()}
    assert states["db"] == "live"
    assert all(v == "missing_key" for n, v in states.items() if n != "db")
    assert j["summary"] == {"live": 1, "missing_key": 7}
    assert j["services"]["sarvam_tts"]["effective"] == "fixture"
    assert j["services"]["whatsapp"]["effective"] == "simulator"


def _healthy_handler(req: httpx.Request):
    path = req.url.path
    if path.endswith("/text-to-speech"):
        return httpx.Response(200, json={"audios": [base64.b64encode(b"mp3").decode()]})
    if path.endswith("/speech-to-text"):
        return httpx.Response(200, json={"transcript": "namaste", "language_code": "hi-IN"})
    if path.endswith("/credits"):
        return httpx.Response(200, json={"data": {"total_credits": 10.0, "total_usage": 3.71}})
    if "chat/completions" in path:
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    if req.url.host == "graph.facebook.com":
        return httpx.Response(200, json={"display_phone_number": "+91 98100 00001"})
    return httpx.Response(404, json={"error": "unexpected"})


def test_live_pings_report_live_and_never_leak(client, monkeypatch):
    use_settings(monkeypatch, **KEYED)
    seen = []

    def handler(req):
        seen.append(req)
        return _healthy_handler(req)

    http.TRANSPORT = httpx.MockTransport(handler)
    r = client.get("/api/admin/health", params={"live": 1})
    j = r.json()
    assert j["status"] == "ok" and j["live_checked"] is True
    assert set(j["pinged"]) == {"db", "sarvam_tts", "sarvam_chat", "sarvam_vision", "openrouter_chat",
                                "openrouter_vision", "whatsapp", "sarvam_stt"}
    for name in ("sarvam_stt", "sarvam_tts", "sarvam_chat", "sarvam_vision", "openrouter_chat",
                 "openrouter_vision", "whatsapp"):
        s = j["services"][name]
        assert s["state"] == "live" and s["last_latency_ms"] is not None and s["last_error"] is None, name
    tts = [q for q in seen if q.url.path.endswith("/text-to-speech")][0]
    assert json.loads(tts.content)["text"] == "Namaste"  # one-word TTS
    chat = [q for q in seen if q.url.path == "/v1/chat/completions" and q.url.host == "api.sarvam.ai"][0]
    assert json.loads(chat.content)["max_tokens"] == 1  # one-token chat
    orc = [q for q in seen if q.url.host == "openrouter.ai" and q.url.path.endswith("/chat/completions")]
    assert sorted(json.loads(q.content)["max_tokens"] for q in orc) == [1, 5]  # 1-token chat, tiny vision
    assert j["services"]["openrouter_chat"]["credits_remaining"] == pytest.approx(6.29)
    assert "credits_remaining" not in j["services"]["openrouter_vision"]
    for secret in SECRETS:
        assert secret not in r.text
    # without ?live=1 nothing is called, but the last results are still reported
    seen.clear()
    again = client.get("/api/admin/health").json()
    assert seen == [] and again["services"]["sarvam_tts"]["last_latency_ms"] is not None


def test_failed_pings_become_fallback_and_errors_are_scrubbed(client, monkeypatch):
    use_settings(monkeypatch, **KEYED)

    def handler(req):
        # a hostile upstream that echoes the key back in its error body
        return httpx.Response(401, json={"error": f"invalid key {SECRETS[0]} / {SECRETS[1]} / {SECRETS[2]}"})

    http.TRANSPORT = httpx.MockTransport(handler)
    r = client.get("/api/admin/health", params={"live": 1})
    j = r.json()
    assert j["status"] == "degraded"
    for name in ("sarvam_tts", "sarvam_chat", "openrouter_chat", "openrouter_vision", "whatsapp"):
        s = j["services"][name]
        assert s["state"] == "fallback" and s["effective"] in ("fixture", "simulator"), name
        assert s["last_error"] and "HTTP 401" in s["last_error"]
    assert "***" in j["services"]["sarvam_chat"]["last_error"]
    for secret in SECRETS:
        assert secret not in r.text
    assert j["services"]["sarvam_stt"]["state"] == "fallback"  # no TTS clip to feed it


def test_status_page_data(client):
    j = client.get("/api/admin/status").json()
    assert j["time_ist"].endswith("IST") and j["time_iso"][:4].isdigit()
    assert j["demo_mode"]["setting"] == "on" and j["demo_mode"]["effective"] == "fixtures"
    assert j["config"]["sarvam_key"] is False and j["config"]["whatsapp_configured"] is False
    assert j["counts"]["products"] == 40 and isinstance(j["counts"]["invoices_today"], int) and j["counts"]["invoices_today"] >= 0
    assert "commit" in j["build"] and j["services"]["db"]["state"] == "live"
    assert j["config"]["models"]["llm"] == "sarvam-105b"
    assert j["config"]["openrouter_key"] is False
    assert j["config"]["openrouter_model"] == "anthropic/claude-haiku-5.5"
    assert j["config"]["openrouter_vision_model"] == "google/gemini-3.1-flash-lite"
    assert "api_key" not in json.dumps(j).lower().replace("sarvam_key", "")


def test_status_never_returns_key_values(client, monkeypatch):
    use_settings(monkeypatch, **KEYED)
    r = client.get("/api/admin/status")
    assert r.json()["config"]["sarvam_key"] is True and r.json()["demo_mode"]["effective"] == "live_with_fallback"
    for secret in SECRETS:
        assert secret not in r.text


def test_demo_checklist_passes_on_fresh_seed(client):
    j = client.get("/api/admin/demo-checklist").json()
    assert j["ready"] is True and j["failed"] == []
    by_id = {i["id"]: i for i in j["items"]}
    assert by_id["cart_249"]["actual"] == 249 and by_id["galla_6850"]["actual"] == 6850
    assert by_id["yesterday_8420"]["actual"] == 8420 and by_id["verma_850"]["actual"] == 850
    assert by_id["surf_rate_42"]["actual"] == 42 and by_id["kurkure_absent"]["actual"] == 0
    assert 1.8 <= by_id["ghee_cover_2d"]["actual"] <= 2.2
    assert "sarvam_key" in j["warnings"]  # advisory only, does not block "ready"
    assert "openrouter_key" in j["warnings"]


def test_reset_demo_restores_seed_numbers(client):
    client.post("/api/stock/missed", json={"product_name": "Kurkure"})
    client.post("/api/stock/prices", json={"items": [{"name": "bread", "price": 99}]})
    broken = client.get("/api/admin/demo-checklist").json()
    assert broken["ready"] is False and "kurkure_asked_6" in broken["failed"]
    last = max([e["id"] for e in events.bus.replay("store")] or [0])
    r = client.post("/api/admin/reset-demo").json()
    assert r["seeded"] is True
    assert [e for e in events.bus.replay("store", last) if e["type"] == "demo_reset"]
    ok = client.get("/api/admin/demo-checklist").json()
    assert ok["ready"] is True
    assert client.get("/api/dashboard").json()["today_sales"] == 7270.0
    v2 = client.get("/api/dashboard/v2").json()
    assert v2["yesterday"]["sales"] == 8420 and len(v2["series"]) == 14
    bread = next(r for r in client.get("/api/stock").json()["items"] if r["name"] == "Bread")
    assert bread["price"] == 45
