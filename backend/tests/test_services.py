"""Provider clients against a mock transport (no network), fallbacks, bus, cache."""
import asyncio
import base64
import dataclasses
import json

import httpx
import pytest

import config
from services import events, fixtures, http, llm, openrouter, sarvam, tts_cache, vision
from services.types import LLMUnavailable, ProviderError

LIVE = dataclasses.replace(config.settings, sarvam_api_key="sk-test", openrouter_api_key="ok-test",
                           demo_mode="auto")


@pytest.fixture
def live(monkeypatch):
    """Pretend keys exist (still no network: a mock transport answers)."""
    for mod in (sarvam, llm, vision, openrouter, tts_cache):
        monkeypatch.setattr(mod, "settings", LIVE)
    monkeypatch.setattr(http, "TRANSPORT", None)
    yield
    monkeypatch.setattr(http, "TRANSPORT", None)


def mock(handler):
    http.TRANSPORT = httpx.MockTransport(handler)


# --- speech helpers ---

def test_format_indian_number():
    assert sarvam.format_indian_number(249) == "249"
    assert sarvam.format_indian_number(9999) == "9999"
    assert sarvam.format_indian_number(10000) == "10,000"
    assert sarvam.format_indian_number(123456) == "1,23,456"
    assert sarvam.format_indian_number(1234567) == "12,34,567"


def test_speak_rupees():
    assert sarvam.speak_rupees(249) == "249 rupaye"
    assert sarvam.speak_rupees(10000) == "10,000 rupaye"
    assert sarvam.speak_rupees(249.5) == "249 rupaye 50 paise"
    assert sarvam.prepare_tts_text("Total ₹12500 hua") == "Total 12,500 rupaye hua"
    assert sarvam.prepare_tts_text("Rs. 294 dena hai") == "294 rupaye dena hai"
    assert sarvam.prepare_tts_text("bill 123456 hai") == "bill 1,23,456 hai"


# --- STT ---

@pytest.mark.anyio
async def test_stt_fixture_without_key():
    r = await sarvam.stt(b"x", "a.webm", demo_phrase="2")
    assert r.source == "fixture"
    assert r.data["transcript"] == fixtures.DEMO_PHRASES["2"]
    assert (await sarvam.stt(b"x", "a.webm")).data["transcript"] == fixtures.DEMO_PHRASES["1"]
    assert (await sarvam.stt(b"x", demo_phrase="ek ghee")).data["transcript"] == "ek ghee"


@pytest.mark.anyio
async def test_stt_text_passthrough():
    r = await sarvam.stt(b"", text="do maggi")
    assert r.source == "rules" and r.data["transcript"] == "do maggi"


@pytest.mark.anyio
async def test_stt_single_call_with_keyterms(live):
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        return httpx.Response(200, json={"transcript": "do maggi", "language_code": "hi-IN"})

    mock(handler)
    r = await sarvam.stt(b"AUDIO", "clip.webm", keyterms=["Maggi", "Surf Excel"])
    assert r.source == "sarvam" and r.data["transcript"] == "do maggi"
    assert len(calls) == 1  # one call only
    req = calls[0]
    assert req.url.path == "/speech-to-text"
    assert req.headers["api-subscription-key"] == "sk-test"
    body = req.content.decode("latin-1")
    assert 'name="model"' in body and "saaras:v4" in body
    assert 'name="keyterms"' in body and '["Maggi", "Surf Excel"]' in body
    assert 'name="language_code"' in body and "hi-IN" in body


@pytest.mark.anyio
async def test_stt_failure_falls_back_to_fixture(live):
    mock(lambda req: httpx.Response(500, text="boom"))
    r = await sarvam.stt(b"x", "a.webm", demo_phrase="4")
    assert r.source == "fixture" and r.data["transcript"] == fixtures.DEMO_PHRASES["4"]


# --- TTS ---

@pytest.mark.anyio
async def test_tts_payload_and_audio_parse(live):
    seen = []

    def handler(req: httpx.Request):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"audios": ["QUJD"]})

    mock(handler)
    r = await sarvam.tts("Total ₹10000", pace=1.1)
    assert r.data == "QUJD" and r.source == "sarvam"
    body = seen[0]
    assert body["text"] == "Total 10,000 rupaye"
    assert body["model"] == "bulbul:v3" and body["speaker"] == "ritu" and body["pace"] == 1.1
    assert body["output_audio_codec"] == "mp3"
    assert "inputs" not in body and body.get("language_code") == "hi-IN"


@pytest.mark.anyio
async def test_tts_retries_other_language_field_on_422(live, monkeypatch):
    monkeypatch.setattr(sarvam, "_tts_lang_field_idx", 0)
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(sorted(k for k in body if "language" in k))
        if "target_language_code" not in body:
            return httpx.Response(422, json={"detail": "missing"})
        return httpx.Response(200, json={"audios": ["QUJD"]})

    mock(handler)
    r = await sarvam.tts("namaste")
    assert r.data == "QUJD"
    assert seen == [["language_code"], ["target_language_code"]]


@pytest.mark.anyio
async def test_tts_without_key_raises():
    with pytest.raises(ProviderError):
        await sarvam.tts("namaste")


@pytest.mark.anyio
async def test_tts_cache_roundtrip(live, monkeypatch, tmp_path):
    monkeypatch.setattr(tts_cache, "settings", dataclasses.replace(LIVE, cache_dir=tmp_path))
    n = {"calls": 0}

    def handler(req):
        n["calls"] += 1
        return httpx.Response(200, json={"audios": [base64.b64encode(b"MP3DATA").decode()]})

    mock(handler)
    a = await tts_cache.get_speech("Bill ban gaya")
    b = await tts_cache.get_speech("Bill ban gaya")
    assert n["calls"] == 1 and not a.cached and b.cached
    assert base64.b64decode(b.audio_base64) == b"MP3DATA"
    assert b.url == f"/api/voice/tts/{b.key}.mp3"
    assert (tmp_path / "tts" / f"{b.key}.mp3").exists()


@pytest.mark.anyio
async def test_tts_cache_failure_gives_empty_audio(live, monkeypatch, tmp_path):
    monkeypatch.setattr(tts_cache, "settings", dataclasses.replace(LIVE, cache_dir=tmp_path))
    mock(lambda req: httpx.Response(500))
    s = await tts_cache.get_speech("kuch bhi")
    assert s.audio_base64 == "" and s.url is None


@pytest.mark.anyio
async def test_tts_cache_no_key_gives_empty_audio():
    s = await tts_cache.get_speech("kuch aur")
    assert s.audio_base64 == "" and s.url is None and s.source == "fixture"


# --- chat / llm ---

CHAT_OK = {"choices": [{"message": {"content": "", "tool_calls": [
    {"id": "c1", "type": "function", "function": {
        "name": "add_to_cart", "arguments": "{\"items\": [{\"name\": \"maggi\", \"qty\": 2}]}"}}]}}]}


@pytest.mark.anyio
async def test_chat_parses_tool_call_arguments_string(live):
    seen = []

    def handler(req: httpx.Request):
        seen.append((req, json.loads(req.content)))
        return httpx.Response(200, json=CHAT_OK)

    mock(handler)
    tools = [{"type": "function", "function": {"name": "add_to_cart", "parameters": {"type": "object"}}}]
    r = await sarvam.chat([{"role": "user", "content": "do maggi"}], tools=tools)
    call = r.data.tool_calls[0]
    assert call.name == "add_to_cart" and call.arguments == {"items": [{"name": "maggi", "qty": 2}]}
    req, body = seen[0]
    assert req.url.path == "/v1/chat/completions"
    assert req.headers["api-subscription-key"] == "sk-test"
    assert req.headers["authorization"] == "Bearer sk-test"
    assert body["model"] == "sarvam-105b" and body["reasoning_effort"] is None
    assert "reasoning_effort" in body  # explicit JSON null
    assert body["tool_choice"] == "auto"


@pytest.mark.anyio
async def test_chat_bad_tool_json_is_provider_error(live):
    bad = {"choices": [{"message": {"tool_calls": [{"function": {"name": "x", "arguments": "{oops"}}]}}]}
    mock(lambda req: httpx.Response(200, json=bad))
    with pytest.raises(ProviderError):
        await sarvam.chat([{"role": "user", "content": "x"}])


@pytest.mark.anyio
async def test_llm_retries_once_on_503(live, monkeypatch):
    monkeypatch.setattr(llm, "RETRY_BACKOFF_SECONDS", 0)
    n = {"calls": 0}

    def handler(req):
        n["calls"] += 1
        return httpx.Response(503) if n["calls"] == 1 else httpx.Response(200, json=CHAT_OK)

    mock(handler)
    r = await llm.complete([{"role": "user", "content": "do maggi"}])
    assert r.source == "sarvam" and n["calls"] == 2


@pytest.mark.anyio
async def test_llm_falls_through_to_openrouter(live, monkeypatch):
    monkeypatch.setattr(llm, "RETRY_BACKOFF_SECONDS", 0)
    hosts = []

    def handler(req: httpx.Request):
        hosts.append(req.url.host)
        if req.url.host == "api.sarvam.ai":
            return httpx.Response(500)
        assert req.headers["authorization"] == "Bearer ok-test"
        return httpx.Response(200, json=CHAT_OK)

    mock(handler)
    r = await llm.complete([{"role": "user", "content": "do maggi"}])
    assert r.source == "openrouter" and r.data.tool_calls[0].name == "add_to_cart"
    assert "api.sarvam.ai" in hosts


@pytest.mark.anyio
async def test_llm_raises_when_all_fail(live, monkeypatch):
    monkeypatch.setattr(llm, "RETRY_BACKOFF_SECONDS", 0)
    mock(lambda req: httpx.Response(500))
    with pytest.raises(LLMUnavailable):
        await llm.complete([{"role": "user", "content": "x"}])


@pytest.mark.anyio
async def test_llm_unavailable_in_demo_mode_and_rules_fallback(db):
    with pytest.raises(LLMUnavailable):
        await llm.complete([{"role": "user", "content": "do maggi"}])
    r = await llm.complete_or_rules([{"role": "user", "content": "do maggi ek surf excel"}], db)
    assert r.source == "fixture"
    items = r.data.tool_calls[0].arguments["items"]
    assert {(i["name"], i["qty"]) for i in items} == {("Maggi", 2.0), ("Surf Excel", 1.0)}


# --- rules tool calls ---

@pytest.mark.parametrize("text,tool,check", [
    ("bas kitna hua", "checkout", lambda a: a == {}),
    ("verma ji ke khate mein paanch sau", "add_udhaar", lambda a: a["amount"] == 500 and a["customer_id"]),
    ("teen sau cash diya do sau paytm baaki khate mein", "split_payment",
     lambda a: a["cash"] == 300 and a["upi"] == 200 and a["khata"] is None),
    ("kurkure nahi hai", "missed_sale", lambda a: a["product"] == "kurkure"),
    ("do maggi", "add_to_cart", lambda a: a["items"][0]["qty"] == 2),
])
def test_rules_tool_calls(db, text, tool, check):
    calls = fixtures.rules_tool_calls(text, db)
    assert calls[0].name == tool and check(calls[0].arguments)


def test_stock_context_uses_restock(db):
    assert fixtures.rules_tool_calls("das packet maggi", db, context="stock")[0].name == "restock"


def test_every_demo_phrase_parses(db):
    for key, phrase in fixtures.DEMO_PHRASES.items():
        assert fixtures.rules_tool_calls(phrase, db), key


# --- vision ---

@pytest.mark.anyio
@pytest.mark.parametrize("task", vision.TASKS)
async def test_vision_fixtures_per_task(task):
    r = await vision.extract_json_from_image(b"img", "image/jpeg", task)
    assert r.source == "fixture" and r.data


@pytest.mark.anyio
async def test_vision_purchase_bill_fixture_shape():
    r = await vision.extract_json_from_image(b"img", "image/jpeg", "purchase_bill")
    assert r.data["supplier"] == "Rajesh Distributors"
    surf = next(x for x in r.data["lines"] if x["name"].startswith("Surf"))
    assert surf["rate"] == 45.0 and surf["scheme_text"] == "Buy 10 Get 1 Free" and surf["free_qty"] == 0
    assert set(surf) >= {"name", "qty", "unit", "rate", "mrp", "batch", "expiry", "scheme_text", "free_qty"}


@pytest.mark.anyio
async def test_vision_cash_fixture_is_6700():
    r = await vision.extract_json_from_image(b"img", "image/jpeg", "cash")
    assert r.data["total"] == 6700 and 0 < r.data["confidence"] <= 1
    assert set(r.data["denominations"]) == {"2000", "500", "200", "100", "50", "20", "10", "coins"}


@pytest.mark.anyio
async def test_vision_unknown_task():
    with pytest.raises(ValueError):
        await vision.extract_json_from_image(b"x", "image/png", "selfie")


@pytest.mark.anyio
async def test_vision_chain_sarvam_then_openrouter(live):
    hosts = []
    good = {"choices": [{"message": {"content": "```json\n[{\"name\": \"Maggi\", \"quantity\": 3}]\n```"}}]}

    def handler(req: httpx.Request):
        hosts.append(req.url.host)
        if req.url.host == "api.sarvam.ai":
            assert req.url.path == "/v2/chat/completions"
            body = json.loads(req.content)
            part = body["messages"][0]["content"][1]
            assert body["model"] == "gemma4" and part["type"] == "image_url"
            assert part["image_url"]["url"].startswith("data:image/jpeg;base64,")
            return httpx.Response(500)
        assert req.url.path == "/api/v1/chat/completions"
        assert json.loads(req.content)["model"] == "google/gemini-3.1-flash-lite"
        return httpx.Response(200, json=good)

    mock(handler)
    r = await vision.extract_json_from_image(b"img", "image/jpeg", "shelf")
    assert r.source == "openrouter" and r.data == [{"name": "Maggi", "quantity": 3}]
    assert hosts == ["api.sarvam.ai", "openrouter.ai"]


@pytest.mark.anyio
async def test_vision_all_fail_gives_fixture(live):
    mock(lambda req: httpx.Response(500))
    r = await vision.extract_json_from_image(b"img", "image/jpeg", "parchi")
    assert r.source == "fixture"


def test_parse_json_loose_and_normalize():
    assert vision.parse_json_loose("Here: {\"a\": 1} thanks") == {"a": 1}
    assert vision.parse_json_loose("```json\n[1,2]\n```") == [1, 2]
    with pytest.raises(ProviderError):
        vision.parse_json_loose("no json")
    cash = vision.normalize_result("cash", {"2000": 1, "500": 2, "coins": 30, "confidence": 2})
    assert cash["total"] == 3030 and cash["confidence"] == 1.0
    assert vision.cash_total({"500": 8, "100": 11, "coins": 0}) == 5100


# --- events bus ---

@pytest.mark.anyio
async def test_event_bus_publish_subscribe_and_replay():
    events.bus.reset()
    q = events.bus.subscribe("store")
    events.publish("store", "cart_updated", {"total": 249})
    events.publish("other", "ignored", {})
    got = await asyncio.wait_for(q.get(), 1)
    assert got["type"] == "cart_updated" and got["data"] == {"total": 249}
    assert q.empty()
    assert [e["type"] for e in events.bus.replay("store")] == ["cart_updated"]
    assert events.bus.replay("store", after_id=got["id"]) == []
    events.bus.unsubscribe("store", q)
    assert events.bus.subscriber_count("store") == 0


@pytest.mark.anyio
async def test_sse_stream_frames():
    events.bus.reset()
    events.publish("store", "payment_received", {"amount": 249})
    stream = events.sse_stream("store", heartbeat=0.05)
    frames = [await asyncio.wait_for(stream.__anext__(), 1) for _ in range(3)]
    assert frames[0].startswith("retry:")
    assert "event: hello" in frames[1]
    assert "event: payment_received" in frames[2] and '"amount": 249' in frames[2]
    assert (await asyncio.wait_for(stream.__anext__(), 1)).startswith(": keep-alive")
    await stream.aclose()
    assert events.bus.subscriber_count("store") == 0


def test_publish_from_sync_thread_is_safe():
    events.bus.reset()
    assert events.publish("store", "x", {"n": 1})["id"] > 0
