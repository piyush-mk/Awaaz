"""Fast path, non-blocking speech, the phrase bank and DEMO_MODE guarantees. Everything is mocked:
no key, no network (the fake TTS sleeps instead of calling Sarvam)."""
import asyncio
import base64
import dataclasses
import time

import pytest
from fastapi.testclient import TestClient

import config
import main
import seed as seed_module
import services.counter as counter_mod
from services import events, phrases, sarvam, speech, tts_cache, voice_style
from services.types import ChatOut, Result

PHRASE = "do maggi ek surf excel chaar colgate"
MP3 = base64.b64encode(b"ID3-fake-mp3").decode()


@pytest.fixture(scope="module")
def client():
    seed_module.seed(reset=True, verbose=False)
    with TestClient(main.app) as c:
        yield c
    seed_module.seed(reset=True, verbose=False)


@pytest.fixture(autouse=True)
def quiet_memory():
    voice_style.reset_memory()
    yield


def say(client, text, session, **kw):
    r = client.post("/api/agent/utterance", data={"text": text, "session_id": session,
                                                  **{k: str(v) for k, v in kw.items()}})
    assert r.status_code == 200, r.text
    return r.json()


def last_event_id():
    ev = events.bus.replay("store", 0)
    return ev[-1]["id"] if ev else 0


def wait_event(type_, after, key=None, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        for e in events.bus.replay("store", after):
            if e["type"] == type_ and (key is None or e["data"].get("key") == key):
                return e
        time.sleep(0.02)
    return None


@pytest.fixture
def same_words(monkeypatch):
    """Always the first variant, never the witty one: two identical requests then share one cache key."""
    monkeypatch.setattr(voice_style, "pick", lambda options, **kw: options[0])
    monkeypatch.setattr(voice_style, "WITTY_RATE", 0.0)


@pytest.fixture
def llm_spy(monkeypatch):
    calls = []

    async def fake(messages, db, tools=None, context="counter", timeout=4.0):
        calls.append(messages)
        return Result(ChatOut(), "rules", 1)

    monkeypatch.setattr(counter_mod.llm, "complete_or_rules", fake)
    return calls


@pytest.fixture
def live_tts(monkeypatch, tmp_path):
    """A fake Sarvam TTS behind a real cache directory. `box['delay']` seconds per call."""
    live = dataclasses.replace(config.settings, sarvam_api_key="sk-test", demo_mode="auto", cache_dir=tmp_path)
    monkeypatch.setattr(tts_cache, "settings", live)
    box = {"delay": 0.0, "calls": [], "running": 0, "peak": 0}

    async def fake_tts(text, language="hi-IN", speaker=None, pace=1.0, codec="mp3", sample_rate=None):
        box["calls"].append({"text": text, "pace": pace, "language": language})
        box["running"] += 1
        box["peak"] = max(box["peak"], box["running"])
        try:
            await asyncio.sleep(box["delay"])
        finally:
            box["running"] -= 1
        return Result(MP3, "sarvam", int(box["delay"] * 1000))

    monkeypatch.setattr(sarvam, "tts", fake_tts)
    return box


# --- fast path ----------------------------------------------------------------------------------------


def test_fast_path_skips_the_llm_for_the_demo_phrase(client, llm_spy):
    r = say(client, PHRASE, "fp-1")
    assert llm_spy == []  # the mocked llm was never called
    assert r["source"] == "rules"
    assert [(ln["name"], ln["qty"]) for ln in r["cart"]["lines"]] == [("Maggi", 2), ("Surf Excel", 1), ("Colgate", 4)]
    assert r["cart"]["total"] == 249.0
    t = r["timings"]
    assert t["llm_ms"] is None and t["stt_ms"] is None  # typed text: no STT, no LLM
    assert t["parse_ms"] is not None and t["total_ms"] == r["latency_ms"]


@pytest.mark.parametrize("text", [
    "ek colgate", "das packet maggi paanch kilo chawal do litre tel", "bees rupaye ki cheeni",
    "ek patanjali shahad do colgate", "maggi",
])
def test_fast_path_phrases(client, llm_spy, text):
    r = say(client, text, "fp-ok")
    assert llm_spy == [] and r["source"] == "rules" and r["cart"]["lines"]


@pytest.mark.parametrize("text", [
    "do maggi kurkure",  # an unmatched word
    "verma ji ke khate mein paanch sau",  # udhaar
    "do maggi udhaar mein",  # khata intent word next to items
    "maggi ka rate pachaas kar do",  # price
    "do chawal",  # loose or packed? ambiguous
    "bas kitna hua",  # checkout
    "kurkure nahi hai",
])
def test_slow_path_still_asks_the_llm(client, llm_spy, text):
    say(client, text, "fp-slow")
    assert len(llm_spy) == 1, text


def test_llm_is_called_when_the_switch_is_off(client, llm_spy, monkeypatch):
    monkeypatch.setattr(counter_mod, "settings", dataclasses.replace(counter_mod.settings, fast_path=False))
    r = say(client, PHRASE, "fp-off")
    assert len(llm_spy) == 1
    assert r["timings"]["llm_ms"] is not None
    assert r["cart"]["total"] == 249.0  # the old path gives the same cart


def test_price_phrase_is_not_mistaken_for_a_quantity_fix(client, llm_spy):
    say(client, "teen maggi", "fp-price")
    r = say(client, "maggi ka rate pachaas kar do", "fp-price")
    assert len(llm_spy) == 1  # sent to the LLM, not applied as "set Maggi quantity to 50"


def test_cart_fix_by_voice_is_fast_too(client, llm_spy):
    say(client, "teen maggi do colgate", "fp-fix")
    r = say(client, "maggi teen nahi do", "fp-fix")
    assert {ln["name"]: ln["qty"] for ln in r["cart"]["lines"]} == {"Maggi": 2, "Colgate": 2}
    r = say(client, "colgate hata do", "fp-fix")
    assert [ln["name"] for ln in r["cart"]["lines"]] == ["Maggi"]
    assert "Colgate" in r["spoken_text"]
    assert llm_spy == []  # all three utterances are fully explained by the rules


# --- non-blocking speech -------------------------------------------------------------------------------


def test_response_does_not_wait_for_tts_then_speech_ready_arrives(client, live_tts, llm_spy, same_words):
    live_tts["delay"] = 3.0  # a slow Bulbul: the response must not feel it
    mark = last_event_id()
    t0 = time.perf_counter()
    r = say(client, PHRASE, "sp-1")
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, elapsed
    sp = r["speech"]
    assert set(sp) == {"text", "pace", "pending", "key", "audio_url", "ack"}
    assert sp["pending"] is True and sp["key"] and sp["audio_url"] is None
    assert r["audio_url"] is None and r["spoken_text"] == sp["text"]  # legacy fields still there
    assert sp["ack"] in phrases.PHRASES and 0.9 <= sp["pace"] <= 1.1
    assert r["latency_ms"] < 1000 and r["timings"]["total_ms"] == r["latency_ms"]

    ev = wait_event("speech_ready", mark, key=sp["key"], timeout=6.0)
    assert ev is not None, "speech_ready never published"
    data = ev["data"]
    assert data["session_id"] == "sp-1" and data["text"] == sp["text"] and data["source"] == "sarvam"
    assert data["audio_url"] == f"/api/voice/tts/{sp['key']}.mp3"
    served = client.get(data["audio_url"])  # the served path keeps working
    assert served.status_code == 200 and served.content == base64.b64decode(MP3)
    assert served.headers["content-type"] == "audio/mpeg"
    # the pace of the line and the shorter mp3 settings reach Sarvam
    assert live_tts["calls"][0]["pace"] == sp["pace"]
    assert "₹" not in live_tts["calls"][0]["text"] and "rupaye" in live_tts["calls"][0]["text"]

    # the same line again is already cached: no waiting, no pending, no second provider call
    r2 = say(client, PHRASE, "sp-1b")
    assert r2["speech"]["pending"] is False and r2["speech"]["audio_url"] == data["audio_url"]
    assert r2["audio_url"] == data["audio_url"]
    assert len(live_tts["calls"]) == 1


def test_duplicate_keys_coalesce_into_one_provider_call(client, live_tts, same_words):
    live_tts["delay"] = 0.8
    mark = last_event_id()
    a = say(client, "ek colgate", "co-a")["speech"]
    b = say(client, "ek colgate", "co-b")["speech"]
    assert a["key"] == b["key"] and a["pending"] and b["pending"]
    ev_a = wait_event("speech_ready", mark, key=a["key"])
    assert ev_a is not None
    time.sleep(0.2)
    got = [e for e in events.bus.replay("store", mark) if e["type"] == "speech_ready" and e["data"]["key"] == a["key"]]
    assert sorted(e["data"]["session_id"] for e in got) == ["co-a", "co-b"]  # each session is told once
    assert len(live_tts["calls"]) == 1
    assert speech.pending_keys() == []


def test_tts_failure_publishes_null_audio_so_the_client_speaks(client, live_tts, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("bulbul down")

    monkeypatch.setattr(sarvam, "tts", boom)
    mark = last_event_id()
    sp = say(client, "do maggi", "fail-1")["speech"]
    assert sp["pending"] is True
    ev = wait_event("speech_ready", mark, key=sp["key"])
    assert ev["data"]["audio_url"] is None and ev["data"]["source"] == "fixture" and ev["data"]["text"]


@pytest.mark.anyio
async def test_ensure_is_bounded_by_the_timeout(live_tts, monkeypatch):
    live_tts["delay"] = 5.0
    monkeypatch.setattr(tts_cache, "TIMEOUT_SECONDS", 0.2)
    t0 = time.perf_counter()
    sp = await tts_cache.ensure("Bahut der laga di")
    assert time.perf_counter() - t0 < 1.0
    assert sp.url is None and sp.source == "fixture" and sp.audio_base64 == ""


def test_demo_mode_never_calls_tts(client, monkeypatch):
    called = []

    async def forbidden(*a, **k):
        called.append(1)
        raise AssertionError("TTS must not be called in DEMO_MODE=on")

    monkeypatch.setattr(sarvam, "tts", forbidden)
    assert config.settings.demo_mode == "on"
    mark = last_event_id()
    r = say(client, PHRASE, "demo-1")
    assert r["demo_mode"] is True
    sp = r["speech"]
    assert sp["pending"] is True and sp["key"] and sp["audio_url"] is None
    ev = wait_event("speech_ready", mark, key=sp["key"])
    assert ev is not None and ev["data"]["audio_url"] is None and ev["data"]["source"] == "fixture"
    assert called == []
    assert phrases.start_warmup() is None  # no warm-up in demo mode either


def test_speak_false_means_no_speech_work(client, live_tts):
    r = say(client, "ek colgate", "quiet-1", speak="false")
    assert r["speech"]["pending"] is False and r["speech"]["key"] is None and r["audio_url"] is None
    time.sleep(0.2)
    assert live_tts["calls"] == []


# --- checkout and payment carry the same speech object -----------------------------------------------------


def test_checkout_and_payment_speak_without_blocking(client, live_tts, same_words):
    live_tts["delay"] = 3.0
    say(client, PHRASE, "pay-1")
    mark = last_event_id()
    t0 = time.perf_counter()
    co = client.post("/api/cart/pay-1/checkout").json()
    assert time.perf_counter() - t0 < 1.0
    sp = co["speech"]
    assert sp["pending"] is True and sp["key"] and co["audio_url"] is None and co["spoken_text"] == sp["text"]
    assert "₹249" in sp["text"]
    ck = [e for e in events.bus.replay("store", mark) if e["type"] == "checkout"]
    assert ck and ck[0]["data"]["speech"]["key"] == sp["key"]

    mark = last_event_id()
    t0 = time.perf_counter()
    sim = client.post(f"/api/payments/{co['order_id']}/simulate").json()
    assert time.perf_counter() - t0 < 1.0
    assert sim["speech"]["pending"] is True and "₹249" in sim["spoken_text"]
    pr = [e for e in events.bus.replay("store", mark) if e["type"] == "payment_received"]
    assert pr and pr[0]["data"]["speech"]["key"] == sim["speech"]["key"] and pr[0]["data"]["audio_url"] is None
    # both clips finish in the background
    assert wait_event("speech_ready", mark, key=sim["speech"]["key"], timeout=8.0) is not None
    assert wait_event("speech_ready", 0, key=sp["key"], timeout=8.0) is not None


def test_confirming_by_voice_returns_speech_too(client, live_tts):
    say(client, "do maggi", "pay-2")
    say(client, "bas kitna hua", "pay-2")
    r = say(client, "haan", "pay-2")
    assert r["actions"][0]["status"] == "confirmed" and r["cart"]["status"] == "checked_out"
    assert r["speech"]["text"] == r["spoken_text"] and "₹24" in r["spoken_text"]
    assert "pending" in r["speech"] and "ack" in r["speech"]


# --- tts_cache API and the phrase bank --------------------------------------------------------------------------


def test_key_for_is_stable_and_pace_sensitive(live_tts):
    k = tts_cache.key_for("Ho gaya.", "hi-IN", "ritu", 1.05)
    assert k == tts_cache.key_for("Ho gaya.", "hi-IN", "ritu", 1.05) and len(k) == 32
    assert k != tts_cache.key_for("Ho gaya.", "hi-IN", "ritu", 1.0)
    assert k != tts_cache.key_for("Ho gaya ji.", "hi-IN", "ritu", 1.05)
    assert tts_cache.get_cached(k) is None


@pytest.mark.anyio
async def test_ensure_then_get_cached(live_tts):
    sp = await tts_cache.ensure("Ho gaya.", pace=1.05)
    assert sp.url and tts_cache.get_cached(sp.key) == sp.url
    again = await tts_cache.ensure("Ho gaya.", pace=1.05)
    assert again.cached and len(live_tts["calls"]) == 1


def test_phrases_endpoint_shape_without_tts(client):
    j = client.get("/api/voice/phrases").json()
    assert set(j) == {"ready", "phrases"} and j["ready"] is False
    assert len(j["phrases"]) >= 24
    for pid in ("ack_ji", "ack_haan_ji", "ack_ek_second", "done_ho_gaya", "unclear_dobara"):
        assert pid in j["phrases"]
    for pid, v in j["phrases"].items():
        assert set(v) == {"text", "audio_url", "kind"} and v["text"] and v["audio_url"] is None
        assert v["kind"] in {"ack", "done", "unclear", "light", "pay"}


@pytest.mark.anyio
async def test_warm_cache_fills_every_phrase_two_at_a_time(live_tts):
    live_tts["delay"] = 0.02
    assert phrases.ready() is False
    n = await phrases.warm_cache()
    assert n == len(phrases.PHRASES) and phrases.ready()
    assert live_tts["peak"] <= phrases.CONCURRENCY
    assert len(live_tts["calls"]) == len(phrases.PHRASES)
    out = phrases.view()
    assert out["ready"] is True and all(v["audio_url"] for v in out["phrases"].values())
    # the endpoint serves what the warm-up wrote
    key = tts_cache.key_of_line("Ji.", "hi-IN", None, 1.05)
    assert out["phrases"]["ack_ji"]["audio_url"] == f"/api/voice/tts/{key}.mp3"
    await phrases.warm_cache()
    assert len(live_tts["calls"]) == len(phrases.PHRASES)  # nothing is generated twice


@pytest.mark.anyio
async def test_warm_cache_fails_quietly(live_tts, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(sarvam, "tts", boom)
    assert await phrases.warm_cache() == 0
    assert phrases.ready() is False
