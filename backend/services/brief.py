"""Morning brief: 3-4 short Hinglish sentences built from `insights.build_facts`.

Two writers, one rule: the brief may only contain numbers that exist in the facts.
  1. LLM (`services.llm.complete`, sarvam-105b) writes the sentences from the facts JSON;
     every digit sequence in its output is checked against the facts and the whole text is
     discarded on a single unknown number (see `verify_numbers`).
  2. The deterministic template (`template_sentences`) is the fallback and also the style
     reference: "Kal ₹8,420 ki sale hui. Dhanteras se pehle ghee sirf do din ka bacha hai."
Audio goes through `services.tts_cache.get_speech`, which never raises.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from services import insights, llm, sarvam, tts_cache
from services.insights import days_phrase, fmt_mult, hindi_count, inr
from services.types import LLMUnavailable, ProviderError, Timer

LLM_TIMEOUT = 8.0
MAX_CHARS = 600

# Spelled-out numbers the verifier understands (ek/do are skipped: they are ordinary words).
_WORD_NUMBERS = {"teen": 3, "chaar": 4, "char": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6, "saat": 7,
                 "aath": 8, "nau": 9, "das": 10, "bees": 20, "pachas": 50, "sau": 100, "hazaar": 1000,
                 "hazar": 1000, "lakh": 100000}

_cache: dict[str, tuple[str, str, int]] = {}  # facts hash -> (text, source, latency_ms)


# ---------------------------------------------------------------------------
# template
# ---------------------------------------------------------------------------


def _sale_sentence(facts: dict) -> str:
    y = facts["yesterday"]
    s = f"Kal {inr(y['total'])} ki sale hui"
    d = y.get("delta_pct")
    if d is not None and y["same_weekday_last_week"]["total"] > 0:
        wk = y["weekday"]
        if abs(d) < 1:
            s += f", pichle {wk} jitni hi"
        elif d > 0:
            s += f", pichle {wk} se {d:g}% zyada"
        else:
            s += f", pichle {wk} se {abs(d):g}% kam"
    return s + "."


def _stock_sentence(facts: dict) -> Optional[str]:
    fest = facts.get("festival")
    if fest and fest.get("at_risk"):
        first = fest["at_risk"][0]  # lowest cover first, so ghee leads at Dhanteras
        cover = first.get("cover_days")
        mult = fmt_mult(first["multiplier"])
        name = first["short_name"]
        if cover is not None and cover <= insights.COVER_ALERT_DAYS + 1:
            return (f"{fest['name']} se pehle {name} {days_phrase(cover)} ka bacha hai,"
                    f" aur demand {mult} guna ho sakti hai.")
        return (f"{fest['name']} {fest['date_short']} ko hai, {name} ki demand {mult} guna ho sakti hai;"
                f" abhi se order bana lein.")
    low = facts.get("low_cover") or []
    if low:
        names = " aur ".join(r["short_name"] for r in low[:2])
        if low[0]["cover_days"] < 0.75:
            return f"{names} aaj hi khatam ho sakte hain."
        return f"{names} {hindi_count(insights.COVER_ALERT_DAYS)} din se kam ke bache hain."
    return None


def _extra_sentences(facts: dict) -> list[str]:
    """Candidate follow-up lines in priority order: galla gap, overdue udhaar, missed sale, expiry."""
    out: list[str] = []
    gap = facts.get("cash_gap")
    if gap:
        word = "kam" if gap["diff"] < 0 else "zyada"
        out.append(f"Kal galla {inr(abs(gap['diff']))} {word} nikla.")
    od = (facts.get("udhaar") or {}).get("overdue") or []
    if od:
        top = od[0]
        out.append(f"{top['name']} ka {inr(top['balance'])} udhaar {top['days_outstanding']} din se baaki hai.")
    ms = facts.get("missed_sales") or []
    if ms and ms[0]["count"] >= 2:
        m = ms[0]
        out.append(f"{m['product_name']} is hafte {m['count']} baar maanga gaya"
                   + (", stock mein nahi hai." if not m.get("product_id") else "."))
    ex = facts.get("expiring") or []
    if ex:
        e = ex[0]
        when = "kal" if e["days_left"] == 1 else ("aaj" if e["days_left"] <= 0 else f"{hindi_count(e['days_left'])} din mein")
        out.append(f"{e['short_name']} {when} expire hoga, {inr(e['claim_amount'])} ka maal.")
    return out


def template_sentences(facts: dict) -> list[str]:
    sentences = [_sale_sentence(facts)]
    stock = _stock_sentence(facts)
    if stock:
        sentences.append(stock)
    sentences.extend(_extra_sentences(facts)[:4 - len(sentences)])
    return sentences[:4]


# ---------------------------------------------------------------------------
# number verification
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _walk_numbers(obj: Any, out: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        v = abs(float(obj))
        out.update({v, round(v), round(v, 1)})
    elif isinstance(obj, str):
        for tok in _NUM_RE.findall(obj):
            try:
                out.add(abs(float(tok.replace(",", ""))))
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_numbers(v, out)


def allowed_numbers(facts: dict) -> set[float]:
    out: set[float] = set()
    _walk_numbers(facts, out)
    return out


def numbers_in(text: str) -> list[float]:
    vals = []
    for tok in _NUM_RE.findall(text):
        try:
            vals.append(float(tok.replace(",", "")))
        except ValueError:
            pass
    return vals


def verify_numbers(text: str, facts: dict) -> tuple[bool, list[float]]:
    """True when every number in `text` (digits, and spelled numbers above 2) is in the facts.
    Returns (ok, offending_numbers)."""
    allowed = allowed_numbers(facts)
    bad = [n for n in numbers_in(text) if not any(abs(n - a) < 1e-6 for a in allowed)]
    for word in re.findall(r"[a-z]+", text.lower()):
        n = _WORD_NUMBERS.get(word)
        if n is not None and not any(abs(n - a) < 1e-6 for a in allowed):
            bad.append(float(n))
    return (not bad), bad


# ---------------------------------------------------------------------------
# LLM writer
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "Tum Ramesh General Store ki dukaan ke AI sahayak ho aur subah ki brief bol rahe ho. Neeche JSON 'facts' hain. "
    "Sirf unhi facts se 3 ya 4 chhote Hinglish (roman script) vaakya likho jo bolne mein aasaan hon.\n"
    "KADE NIYAM:\n"
    "1. Koi bhi number invent, round, jodna-ghatana ya anumaan mat karo. Sirf wahi numbers likho jo facts mein "
    "bilkul waise hi diye hain. Number hamesha digits mein likho (jaise 8,420, 12, 4), shabdon mein nahi.\n"
    "2. Rupaye ₹ ke saath likho, jaise ₹8,420.\n"
    "3. Jo facts mein nahi hai woh mat likho. Naya product, naam ya wajah mat banao.\n"
    "4. Pehla vaakya kal ki sale aur pichle hafte se tulna. Phir sabse zaroori cheez: tyohaar se pehle jo "
    "maal kam padne wala hai. Phir ek ya do aur zaroori baatein (udhaar, missed sale, expiry, galla).\n"
    "5. Bullet, emoji, heading ya list mat banao. Sirf seedhe vaakya.\n"
    "Style ka namoona: 'Kal ₹8,420 ki sale hui, pichle Budhvaar se 12% zyada. Dhanteras se pehle ghee sirf do din "
    "ka bacha hai.' (namoone ke numbers copy mat karo; apne facts ke numbers use karo.)"
)


def _clean_llm_text(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^[\s\-*•\d.)]+", "", text, flags=re.M)  # strip list markers
    return re.sub(r"\s+", " ", text).strip().strip('"')


async def llm_sentences(facts: dict) -> tuple[Optional[str], str, int]:
    """(text, source, latency_ms); text is None when the LLM is unavailable or its output was
    rejected (unknown number, empty, too long, too many sentences)."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "facts:\n" + json.dumps(facts, ensure_ascii=False, default=str)}]
    try:
        res = await llm.complete(messages, timeout=LLM_TIMEOUT)
    except (LLMUnavailable, ProviderError):
        return None, "rules", 0
    except Exception:  # never let the brief fail because of the LLM
        return None, "rules", 0
    text = _clean_llm_text(res.data.content)
    if not text or len(text) > MAX_CHARS:
        return None, "rules", res.latency_ms
    if len(re.findall(r"[.!?।]", text)) > 6:
        return None, "rules", res.latency_ms
    ok, _bad = verify_numbers(text, facts)
    if not ok:
        return None, "rules", res.latency_ms
    return text, res.source, res.latency_ms


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def spoken_version(text: str) -> str:
    """Text as it should be read aloud: rupee amounts via speak_rupees, % as 'percent'."""
    return sarvam.prepare_tts_text(text).replace("%", " percent")


async def audio_for(text: str) -> dict[str, Any]:
    """TTS payload for `text` (cached). Empty audio_base64 means: use the browser voice."""
    spoken = spoken_version(text)
    speech = await tts_cache.get_speech(spoken, speak_rupees=False)
    return {"audio_base64": speech.audio_base64, "audio_url": speech.url, "tts_source": speech.source,
            "cached": speech.cached, "spoken_text": spoken}


async def generate(db: Session, today: Optional[date] = None, use_llm: bool = True,
                   refresh: bool = False) -> dict[str, Any]:
    """Facts + brief text (no audio). Cached per facts hash so repeat calls skip the LLM."""
    facts = insights.build_facts(db, today)
    key = hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()[:24]
    text: Optional[str] = None
    source, latency = "rules", 0
    if use_llm and not refresh and key in _cache:
        text, source, latency = _cache[key]
    elif use_llm:
        with Timer() as t:
            text, source, latency = await llm_sentences(facts)
        if text:
            _cache[key] = (text, source, latency or t.ms)
    sentences = template_sentences(facts)
    template = " ".join(sentences)
    if not text:
        text, source = template, "rules"
    return {"date": facts["date"], "facts": facts, "text": text, "template_text": template,
            "sentences": [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()],
            "spoken_text": spoken_version(text), "source": source, "latency_ms": latency}


def clear_cache() -> None:
    _cache.clear()
