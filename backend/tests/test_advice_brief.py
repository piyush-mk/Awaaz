"""F8 morning brief: facts, deterministic template, LLM number verification, audio, play event."""
import pytest

from services import brief, events, insights, llm
from services.types import ChatOut, Result, ToolCall  # noqa: F401
from tests.test_advice_common import make_client_fixture, pin_dhanteras

client = make_client_fixture()


@pytest.fixture(autouse=True)
def festival(monkeypatch):
    pin_dhanteras(monkeypatch, 8)
    brief.clear_cache()
    yield
    brief.clear_cache()


def test_facts_match_seed(db):
    f = insights.build_facts(db)
    assert f["yesterday"]["total"] == 8420 and f["yesterday"]["delta_pct"] == 12.0
    assert f["yesterday"]["same_weekday_last_week"]["total"] == 7518
    assert len(f["top_items"]) == 3
    assert f["festival"]["name"] == "Dhanteras" and f["festival"]["days_away"] == 8
    ghee = next(r for r in f["festival"]["at_risk"] if r["short_name"] == "ghee")
    assert ghee["multiplier"] == 4.0 and ghee["cover_days"] == pytest.approx(2.0, abs=0.2)
    assert f["missed_sales"][0]["product_name"] == "Kurkure" and f["missed_sales"][0]["count"] == 6
    assert f["udhaar"]["total_outstanding"] > 8000
    assert any(e["name"] == "Doodh" for e in f["expiring"])
    assert f["cash_gap"] is None  # yesterday's galla was exact


def test_brief_today_template_without_keys(client):
    r = client.get("/api/brief/today")
    assert r.status_code == 200
    j = r.json()
    assert j["source"] == "rules"
    text = j["text"]
    assert "8,420" in text and "ghee" in text.lower() and "Dhanteras" in text
    assert "12%" in text
    assert 3 <= len(j["sentences"]) <= 4
    assert "8420 rupaye" in j["spoken_text"] and "percent" in j["spoken_text"]
    assert j["audio_base64"] == "" and j["audio_url"] is None  # no key: browser voice
    assert j["facts"]["yesterday"]["total"] == 8420


def test_deck_style_sentence_present(client):
    text = client.get("/api/brief/today").json()["text"]
    assert text.startswith("Kal ₹8,420 ki sale hui")
    assert "Dhanteras se pehle ghee sirf do din ka bacha hai" in text


def test_verify_numbers(db):
    facts = insights.build_facts(db)
    ok, bad = brief.verify_numbers("Kal ₹8,420 ki sale hui, 12% zyada. Ghee 4 guna.", facts)
    assert ok and bad == []
    ok, bad = brief.verify_numbers("Kal ₹9,999 ki sale hui.", facts)
    assert not ok and 9999.0 in bad
    ok, _ = brief.verify_numbers("Kal paanch hazaar ki sale hui.", facts)
    assert not ok  # spelled-out unknown numbers are caught too


def _fake_llm(monkeypatch, content, source="sarvam"):
    async def fake(messages, tools=None, tool_choice="auto", response_format=None, timeout=4.0):
        fake.calls.append(messages)
        return Result(ChatOut(content=content), source, 7)
    fake.calls = []
    monkeypatch.setattr(llm, "complete", fake)
    return fake


@pytest.mark.anyio
async def test_hallucinated_number_is_discarded(db, monkeypatch):
    fake = _fake_llm(monkeypatch, "Kal ₹9,999 ki sale hui. Ghee do din ka hai.")
    out = await brief.generate(db)
    assert fake.calls, "the LLM must have been tried"
    assert out["source"] == "rules"
    assert "8,420" in out["text"] and "9,999" not in out["text"]


@pytest.mark.anyio
async def test_verified_llm_text_is_used(db, monkeypatch):
    good = "Kal ₹8,420 ki sale hui, pichle Budhvaar se 12% zyada. Dhanteras se pehle ghee sirf 2 din ka bacha hai."
    fake = _fake_llm(monkeypatch, good)
    out = await brief.generate(db)
    assert out["source"] == "sarvam" and out["text"] == good
    system = fake.calls[0][0]["content"]
    assert "invent" in system.lower()  # the prompt forbids inventing numbers
    again = await brief.generate(db)  # second call is served from the cache
    assert len(fake.calls) == 1 and again["text"] == good


@pytest.mark.anyio
async def test_llm_failure_falls_back(db, monkeypatch):
    async def boom(*a, **k):
        raise llm.LLMUnavailable("no provider", "llm")
    monkeypatch.setattr(llm, "complete", boom)
    out = await brief.generate(db)
    assert out["source"] == "rules" and "8,420" in out["text"]


def test_speak_and_play(client):
    spoken = client.post("/api/brief/speak").json()
    assert "8,420" in spoken["text"] and spoken["audio_base64"] == ""
    custom = client.post("/api/brief/speak", json={"text": "Namaste ₹250"}).json()
    assert custom["text"] == "Namaste ₹250" and "250 rupaye" in custom["spoken_text"]
    last = events.bus.replay("store")[-1]["id"] if events.bus.replay("store") else 0
    played = client.post("/api/brief/play").json()
    assert played["published"] is True
    ev = [e for e in events.bus.replay("store", last) if e["type"] == "brief_ready"]
    assert ev and ev[-1]["data"]["yesterday_total"] == 8420 and "8,420" in ev[-1]["data"]["text"]
