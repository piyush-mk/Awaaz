"""F15 Ask your munim: rules router without keys, LLM tool path with a mocked model."""
import pytest

from services import llm, munim
from services.clock import today_local
from services.types import ChatOut, Result, ToolCall
from tests.test_advice_common import make_client_fixture

client = make_client_fixture()


def ask(client, text):
    r = client.post("/api/munim/ask", json={"text": text})
    assert r.status_code == 200
    return r.json()


def test_top_item_this_week(client):
    j = ask(client, "is hafte sabse zyada kya bika")
    assert j["source"] == "rules" and j["tools"][0]["name"] == "top_items"
    assert j["tools"][0]["args"]["period"] == "week"
    top = j["table"]["rows"][0][1]
    assert top in j["answer"] and j["answer"].startswith("Is hafte sabse zyada bika")
    assert j["table"]["columns"][:2] == ["rank", "item"]
    assert j["audio_base64"] == "" and "rupaye" in j["spoken_text"]


def test_verma_ji_balance_is_850(client):
    j = ask(client, "verma ji ka kitna baaki hai")
    assert j["tools"][0]["name"] == "who_owes"
    assert j["tools"][0]["data"]["customers"][0]["balance"] == 850
    assert "₹850" in j["answer"] and "Verma ji" in j["answer"]
    assert j["spoken_text"].count("850 rupaye") == 1


def test_stock_of_ghee(client):
    j = ask(client, "kitna stock hai ghee")
    d = j["tools"][0]["data"]["matches"][0]
    assert j["tools"][0]["name"] == "stock_of" and d["stock"] == 3 and d["cover_days"] == pytest.approx(2.0, abs=0.2)
    assert "Amul Ghee" in j["answer"]


def test_who_owes_everyone_and_today_sale(client):
    j = ask(client, "kis kis ka udhaar baaki hai")
    assert j["tools"][0]["name"] == "who_owes" and len(j["tools"][0]["data"]["customers"]) == 10
    assert j["table"]["rows"][0][0] == "Khan sahab"
    j = ask(client, "aaj ki sale")
    assert j["tools"][0]["name"] == "sales_summary"
    assert j["tools"][0]["data"]["total"] == client.get("/api/dashboard").json()["today_sales"]


@pytest.mark.parametrize("text,tool", [
    ("kya khatam ho raha hai", "low_stock"), ("kaunsa maal expire hone wala hai", "expiry_soon"),
    ("kul udhaar kitna hai", "udhaar_total"), ("kal galla kaisa tha", "cash_gap"),
    ("kal kitni sale hui", "sales_summary"),
])
def test_other_rules(client, text, tool):
    assert ask(client, text)["tools"][0]["name"] == tool


def test_unknown_question_is_polite(client):
    j = ask(client, "mausam kaisa hai")
    assert j["understood"] is False and j["tools"] == [] and "samajh nahi aaya" in j["answer"]


def test_audio_question_uses_fixture_stt(client):
    r = client.post("/api/munim/ask", files={"audio": ("q.webm", b"xx", "audio/webm")},
                    headers={"X-Demo-Phrase": "verma ji ka kitna baaki hai"})
    j = r.json()
    assert r.status_code == 200 and j["transcript"] == "verma ji ka kitna baaki hai"
    assert j["stt_source"] == "fixture" and "₹850" in j["answer"]
    default = client.post("/api/munim/ask", files={"audio": ("q.webm", b"xx", "audio/webm")}).json()
    assert default["tools"][0]["name"] == "top_items"


def test_input_validation_and_aliases(client):
    assert client.post("/api/munim/ask", json={"text": "  "}).status_code == 422
    assert client.post("/api/ask", json={"text": "aaj ki sale"}).status_code == 200
    assert client.post("/api/brief/ask", data={"text": "aaj ki sale"}).status_code == 200
    assert client.get("/api/munim/examples").json()["examples"]


def test_tools_are_read_only():
    assert set(munim.TOOLS) == {"sales_summary", "top_items", "stock_of", "who_owes", "low_stock",
                                "expiry_soon", "udhaar_total", "cash_gap"}
    names = {t["function"]["name"] for t in munim.TOOL_SCHEMAS}
    assert names == set(munim.TOOLS)


def _mock_llm(monkeypatch, tool_calls, rephrase=None):
    async def fake(messages, tools=None, tool_choice="auto", response_format=None, timeout=4.0):
        if tools:
            return Result(ChatOut(tool_calls=tool_calls), "sarvam", 5)
        return Result(ChatOut(content=rephrase or ""), "sarvam", 5)
    monkeypatch.setattr(llm, "complete", fake)


@pytest.mark.anyio
async def test_llm_tool_call_then_verified_rephrase(db, monkeypatch):
    _mock_llm(monkeypatch, [ToolCall("who_owes", {"customer": "Verma ji"})],
              rephrase="Verma ji ka ₹850 udhaar baaki hai, aur 3 baar der se chukaya hai.")
    out = await munim.ask(db, "verma ji ka hisaab batao")
    assert out["source"] == "sarvam" and out["tools"][0]["name"] == "who_owes"
    assert out["answer"] == "Verma ji ka ₹850 udhaar baaki hai, aur 3 baar der se chukaya hai."


@pytest.mark.anyio
async def test_llm_hallucinated_rephrase_keeps_deterministic_answer(db, monkeypatch):
    _mock_llm(monkeypatch, [ToolCall("who_owes", {"customer": "Verma ji"})],
              rephrase="Verma ji ka ₹1,850 baaki hai.")
    out = await munim.ask(db, "verma ji ka hisaab batao")
    assert "₹850" in out["answer"] and "1,850" not in out["answer"]


@pytest.mark.anyio
async def test_llm_unknown_or_write_tool_is_ignored(db, monkeypatch):
    _mock_llm(monkeypatch, [ToolCall("add_udhaar", {"customer": "Verma ji", "amount": 500})])
    out = await munim.ask(db, "aaj ki sale")
    assert out["source"] == "rules" and out["tools"][0]["name"] == "sales_summary"
    assert out["tools"][0]["data"]["period"] == "today"
    assert out["tools"][0]["data"]["to"] == today_local().isoformat()


@pytest.mark.anyio
async def test_llm_bad_arguments_do_not_crash(db, monkeypatch):
    _mock_llm(monkeypatch, [ToolCall("top_items", {"period": "pichle saal", "n": "kuch"})])
    out = await munim.ask(db, "kuch bhi")
    assert out["tools"][0]["name"] == "top_items" and out["tools"][0]["data"] is not None
