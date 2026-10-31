"""OpenRouter backup provider: client, chain order, cost capture, key hygiene (no network)."""
import dataclasses
import json

import httpx
import pytest

import config
from services import health, http, llm, openrouter, sarvam, tts_cache, vision
from services.types import LLMUnavailable, ProviderError

KEY = "or-SECRET-key-123"
MODULES = (openrouter, llm, vision, sarvam, health, tts_cache)


def use(monkeypatch, **kw):
    s = dataclasses.replace(config.settings, sarvam_api_key="sk-test", openrouter_api_key=KEY,
                            demo_mode="auto", **kw)
    for mod in MODULES:
        monkeypatch.setattr(mod, "settings", s)
    monkeypatch.setattr(openrouter, "RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(llm, "RETRY_BACKOFF_SECONDS", 0)
    return s


@pytest.fixture
def live(monkeypatch):
    use(monkeypatch)
    health.reset()
    yield
    monkeypatch.setattr(http, "TRANSPORT", None)
    health.reset()


def mock(handler):
    http.TRANSPORT = httpx.MockTransport(handler)


TOOL_REPLY = {
    "model": "anthropic/claude-haiku-5.5",
    "choices": [{"message": {"content": None, "tool_calls": [{
        "id": "call_1", "type": "function",
        "function": {"name": "add_to_cart", "arguments": "{\"items\": [{\"name\": \"Maggi\", \"qty\": 2}]}"}}]}}],
    "usage": {"prompt_tokens": 120, "completion_tokens": 30, "cost": 0.000135},
}
TOOLS = [{"type": "function", "function": {"name": "add_to_cart", "parameters": {"type": "object"}}}]


# --- config ---

def test_settings_defaults_and_removed_providers():
    s = config.load_settings()
    assert s.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert s.openrouter_model == "anthropic/claude-haiku-5.5"
    assert s.openrouter_vision_model == "google/gemini-3.1-flash-lite"
    assert s.has_openrouter is False  # conftest blanks the key
    assert not hasattr(s, "paytm_api_key") and not hasattr(s, "xai_key")


# --- chat ---

@pytest.mark.anyio
async def test_chat_parses_tool_calls_and_sends_expected_request(live):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=TOOL_REPLY)

    mock(handler)
    r = await openrouter.chat([{"role": "user", "content": "do maggi"}], tools=TOOLS)
    assert r.source == "openrouter"
    call = r.data.tool_calls[0]
    assert call.name == "add_to_cart" and call.id == "call_1"
    assert call.arguments == {"items": [{"name": "Maggi", "qty": 2}]}  # JSON string was parsed
    req = seen[0]
    assert req.url.host == "openrouter.ai" and req.url.path == "/api/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert req.headers["http-referer"] == "https://github.com/piyush-mk/Awaaz"
    assert req.headers["x-title"] == "Awaaz"
    body = json.loads(req.content)
    assert body["model"] == "anthropic/claude-haiku-5.5" and body["temperature"] == 0
    assert body["max_tokens"] == 800 and body["usage"] == {"include": True}
    assert body["tools"] == TOOLS and body["tool_choice"] == "auto"


@pytest.mark.anyio
async def test_chat_plain_text_and_max_tokens_override(live):
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": " namaste "}}]})

    mock(handler)
    r = await openrouter.chat([{"role": "user", "content": "hi"}], max_tokens=1)
    assert r.data.content == "namaste" and r.data.tool_calls == [] and r.meta.get("cost") is None
    assert seen[0]["max_tokens"] == 1 and "tools" not in seen[0]


@pytest.mark.anyio
async def test_chat_cost_and_tokens_captured_from_usage(live):
    mock(lambda req: httpx.Response(200, json=TOOL_REPLY))
    r = await openrouter.chat([{"role": "user", "content": "x"}], tools=TOOLS)
    assert r.meta["cost"] == pytest.approx(0.000135)
    assert r.meta["prompt_tokens"] == 120 and r.meta["completion_tokens"] == 30
    assert r.meta["model"] == "anthropic/claude-haiku-5.5"


@pytest.mark.anyio
async def test_chat_bad_tool_json_is_provider_error(live):
    bad = {"choices": [{"message": {"tool_calls": [{"function": {"name": "x", "arguments": "{oops"}}]}}]}
    mock(lambda req: httpx.Response(200, json=bad))
    with pytest.raises(ProviderError) as ei:
        await openrouter.chat([{"role": "user", "content": "x"}])
    assert ei.value.provider == "openrouter"


@pytest.mark.anyio
async def test_chat_requires_key(monkeypatch):
    use(monkeypatch)
    monkeypatch.setattr(openrouter, "settings", dataclasses.replace(config.settings, openrouter_api_key=""))
    with pytest.raises(ProviderError, match="not configured"):
        await openrouter.chat([{"role": "user", "content": "x"}])


# --- retry ---

@pytest.mark.anyio
@pytest.mark.parametrize("status", [429, 503])
async def test_retries_once_on_429_or_503(live, status):
    n = {"calls": 0}

    def handler(req):
        n["calls"] += 1
        return httpx.Response(status) if n["calls"] == 1 else httpx.Response(200, json=TOOL_REPLY)

    mock(handler)
    r = await openrouter.chat([{"role": "user", "content": "x"}])
    assert r.source == "openrouter" and n["calls"] == 2


@pytest.mark.anyio
async def test_never_retries_more_than_once_or_on_other_errors(live):
    n = {"calls": 0}

    def always(status):
        def handler(req):
            n["calls"] += 1
            return httpx.Response(status, text="nope")
        return handler

    mock(always(429))
    with pytest.raises(ProviderError) as ei:
        await openrouter.chat([{"role": "user", "content": "x"}])
    assert ei.value.status == 429 and n["calls"] == 2
    n["calls"] = 0
    mock(always(500))
    with pytest.raises(ProviderError):
        await openrouter.chat([{"role": "user", "content": "x"}])
    assert n["calls"] == 1


# --- key hygiene ---

@pytest.mark.anyio
async def test_key_never_appears_in_error_strings(live):
    mock(lambda req: httpx.Response(401, json={"error": f"bad key {KEY} for {req.headers['authorization']}"}))
    with pytest.raises(ProviderError) as ei:
        await openrouter.chat([{"role": "user", "content": "x"}])
    assert KEY not in str(ei.value) and "***" in str(ei.value) and ei.value.status == 401
    with pytest.raises(ProviderError) as ei:
        await openrouter.vision(b"img", "image/png", "describe")
    assert KEY not in str(ei.value)

    def boom(req):
        raise httpx.ConnectError(f"cannot reach host with {KEY}")

    mock(boom)
    with pytest.raises(ProviderError) as ei:
        await openrouter.chat([{"role": "user", "content": "x"}])
    assert KEY not in str(ei.value) and ei.value.provider == "openrouter"

    def slow(req):
        raise httpx.ReadTimeout(f"timed out {KEY}")

    mock(slow)
    with pytest.raises(ProviderError) as ei:
        await openrouter.chat([{"role": "user", "content": "x"}])
    assert KEY not in str(ei.value) and ei.value.status == 408


@pytest.mark.anyio
async def test_chain_errors_do_not_leak_key(live):
    mock(lambda req: httpx.Response(500, text=f"upstream echoes {req.headers.get('authorization')}"
                                    f" {req.headers.get('api-subscription-key')}"))
    with pytest.raises(LLMUnavailable) as ei:
        await llm.complete([{"role": "user", "content": "x"}])
    assert KEY not in str(ei.value) and "sarvam:" in str(ei.value) and "openrouter:" in str(ei.value)


# --- vision ---

GOOD_VISION = {"model": "google/gemini-3.1-flash-lite",
               "choices": [{"message": {"content": "```json\n[{\"name\": \"Maggi\", \"quantity\": 3}]\n```"}}],
               "usage": {"prompt_tokens": 900, "completion_tokens": 40, "cost": 0.00102}}


@pytest.mark.anyio
async def test_vision_returns_raw_text_with_schema_in_prompt(live):
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=GOOD_VISION)

    mock(handler)
    schema = {"type": "array"}
    r = await openrouter.vision(b"img", "image/jpeg", "Count items.", schema)
    assert r.source == "openrouter" and r.data == GOOD_VISION["choices"][0]["message"]["content"]  # untouched
    assert r.meta["cost"] == pytest.approx(0.00102) and r.meta["prompt_tokens"] == 900
    body = seen[0]
    assert body["model"] == "google/gemini-3.1-flash-lite" and body["temperature"] == 0
    assert body["max_tokens"] == 2500 and body["usage"] == {"include": True}
    text_part, image_part = body["messages"][0]["content"]
    assert text_part["text"].startswith("Count items.")
    assert "Return ONLY JSON matching this schema, no prose:" in text_part["text"]
    assert json.dumps(schema) in text_part["text"]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.anyio
async def test_vision_without_schema_and_no_content(live):
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": []})

    mock(handler)
    with pytest.raises(ProviderError, match="no content"):
        await openrouter.vision(b"i", "image/png", "Reply with one word.", max_tokens=5)
    assert seen[0]["max_tokens"] == 5
    assert seen[0]["messages"][0]["content"][0]["text"] == "Reply with one word."


# --- chain order: llm ---

@pytest.mark.anyio
async def test_llm_sarvam_failure_falls_to_openrouter(live):
    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        return httpx.Response(500) if req.url.host == "api.sarvam.ai" else httpx.Response(200, json=TOOL_REPLY)

    mock(handler)
    r = await llm.complete([{"role": "user", "content": "do maggi"}], tools=TOOLS)
    assert r.source == "openrouter" and r.data.tool_calls[0].name == "add_to_cart"
    assert hosts == ["api.sarvam.ai", "openrouter.ai"]


@pytest.mark.anyio
async def test_llm_sarvam_success_never_touches_openrouter(live):
    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        return httpx.Response(200, json=TOOL_REPLY)

    mock(handler)
    r = await llm.complete([{"role": "user", "content": "do maggi"}])
    assert r.source == "sarvam" and hosts == ["api.sarvam.ai"]


@pytest.mark.anyio
async def test_llm_openrouter_alone_when_no_sarvam_key(monkeypatch):
    use(monkeypatch)
    s = dataclasses.replace(config.settings, openrouter_api_key=KEY, demo_mode="auto")
    monkeypatch.setattr(llm, "settings", s)
    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        return httpx.Response(200, json=TOOL_REPLY)

    mock(handler)
    r = await llm.complete([{"role": "user", "content": "x"}])
    monkeypatch.setattr(http, "TRANSPORT", None)
    assert r.source == "openrouter" and hosts == ["openrouter.ai"]


@pytest.mark.anyio
async def test_llm_both_fail_rules_under_auto_and_raises_under_off(live, monkeypatch, db):
    mock(lambda req: httpx.Response(500))
    msgs = [{"role": "user", "content": "do maggi ek surf excel"}]
    with pytest.raises(LLMUnavailable):
        await llm.complete(msgs)
    r = await llm.complete_or_rules(msgs, db)
    assert r.source == "rules" and r.data.tool_calls[0].name == "add_to_cart"
    off = dataclasses.replace(llm.settings, demo_mode="off")
    monkeypatch.setattr(llm, "settings", off)
    with pytest.raises(LLMUnavailable):
        await llm.complete_or_rules(msgs, db)


# --- chain order: vision ---

@pytest.mark.anyio
async def test_vision_chain_sarvam_then_openrouter_then_fixture(live):
    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        return httpx.Response(500) if req.url.host == "api.sarvam.ai" else httpx.Response(200, json=GOOD_VISION)

    mock(handler)
    r = await vision.extract_json_from_image(b"img", "image/jpeg", "shelf")
    assert r.source == "openrouter" and r.data == [{"name": "Maggi", "quantity": 3}]
    assert r.meta["cost"] == pytest.approx(0.00102)
    assert hosts == ["api.sarvam.ai", "openrouter.ai"]

    hosts.clear()
    mock(lambda req: (hosts.append(req.url.host),
                      httpx.Response(500, text=KEY if req.url.host == "openrouter.ai" else "down"))[1])
    r = await vision.extract_json_from_image(b"img", "image/jpeg", "parchi")
    assert r.source == "fixture" and hosts == ["api.sarvam.ai", "openrouter.ai"]
    assert len(r.meta["errors"]) == 2 and KEY not in json.dumps(r.meta)


@pytest.mark.anyio
async def test_vision_sarvam_success_skips_openrouter(live):
    hosts = []

    def handler(req):
        hosts.append(req.url.host)
        return httpx.Response(200, json=GOOD_VISION)

    mock(handler)
    r = await vision.extract_json_from_image(b"img", "image/jpeg", "shelf")
    assert r.source == "sarvam" and hosts == ["api.sarvam.ai"]


@pytest.mark.anyio
async def test_vision_both_fail_raises_under_off(live, monkeypatch):
    monkeypatch.setattr(vision, "settings", dataclasses.replace(vision.settings, demo_mode="off"))
    mock(lambda req: httpx.Response(500))
    with pytest.raises(ProviderError, match="openrouter"):
        await vision.extract_json_from_image(b"img", "image/jpeg", "shelf")


# --- DEMO_MODE=on makes no call ---

@pytest.mark.anyio
async def test_demo_mode_on_makes_no_external_call(monkeypatch, db):
    s = use(monkeypatch)
    on = dataclasses.replace(s, demo_mode="on")
    for mod in MODULES:
        monkeypatch.setattr(mod, "settings", on)
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=TOOL_REPLY)

    mock(handler)
    try:
        with pytest.raises(LLMUnavailable):
            await llm.complete([{"role": "user", "content": "x"}])
        r = await llm.complete_or_rules([{"role": "user", "content": "do maggi"}], db)
        assert r.source == "fixture"
        v = await vision.extract_json_from_image(b"img", "image/jpeg", "shelf")
        assert v.source == "fixture"
        assert await openrouter.credits() is None
        assert await health.run_live_checks(db) == ["db"]
        assert calls == []
    finally:
        monkeypatch.setattr(http, "TRANSPORT", None)


# --- credits ---

@pytest.mark.anyio
async def test_credits_remaining_is_total_minus_usage(live):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"data": {"total_credits": 10, "total_usage": 3.71}})

    mock(handler)
    c = await openrouter.credits()
    assert c["remaining"] == pytest.approx(6.29) and c["total_credits"] == 10
    assert seen[0].method == "GET" and seen[0].url.path == "/api/v1/credits"
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"


@pytest.mark.anyio
@pytest.mark.parametrize("make", [
    lambda req: httpx.Response(500),
    lambda req: httpx.Response(401, json={"error": "bad"}),
    lambda req: httpx.Response(200, text="not json"),
    lambda req: httpx.Response(200, json={"data": {}}),
    lambda req: httpx.Response(200, json={"data": {"total_credits": "x", "total_usage": None}}),
    lambda req: (_ for _ in ()).throw(httpx.ConnectError("down")),
])
async def test_credits_returns_none_on_any_failure(live, make):
    mock(make)
    assert await openrouter.credits() is None


@pytest.mark.anyio
async def test_credits_none_without_key(monkeypatch):
    use(monkeypatch)
    monkeypatch.setattr(openrouter, "settings", dataclasses.replace(config.settings, openrouter_api_key=""))
    assert await openrouter.credits() is None


# --- health ---

def test_health_missing_key_without_openrouter_key(monkeypatch):
    use(monkeypatch)
    blank = dataclasses.replace(config.settings, openrouter_api_key="", sarvam_api_key="sk-test", demo_mode="auto")
    monkeypatch.setattr(health, "settings", blank)
    health.reset()
    for name in ("openrouter_chat", "openrouter_vision"):
        st = health.state_of(name)
        assert st["state"] == "missing_key" and st["configured"] is False and st["effective"] == "fixture"
    assert health.state_of("openrouter_chat")["model"] == "anthropic/claude-haiku-5.5"
    assert health.state_of("openrouter_vision")["model"] == "google/gemini-3.1-flash-lite"
    assert health.state_of("openrouter_chat")["credits_remaining"] is None
    assert set(health.snapshot()) == {"sarvam_stt", "sarvam_tts", "sarvam_chat", "sarvam_vision",
                                      "openrouter_chat", "openrouter_vision", "whatsapp", "db"}


def test_health_scrub_removes_openrouter_key(monkeypatch):
    use(monkeypatch)
    assert KEY not in health.scrub(f"oops {KEY} oops")
