"""The phrase bank: ~25 short fixed lines with stable ids, pre-generated at startup so the client can
play an acknowledgement the instant the merchant stops speaking, long before the real reply is ready.

  * `PHRASES`: id -> Phrase(text, kind, pace). Ids are stable (the frontend refers to them).
  * `start_warmup()`: called once from the app lifespan. Warms the audio cache in the background,
    two clips at a time, and fails quietly. Skipped under DEMO_MODE=on or without a Sarvam key.
  * `view()`: payload of GET /api/voice/phrases.
  * `ack_for(situation, ...)`: which phrase id a reply should suggest as `speech.ack`.

No gendered first-person verbs ("dekhte hain", not "dekhta hoon"): the default voice is female.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from services import tts_cache, voice_style

log = logging.getLogger("awaaz.phrases")

CONCURRENCY = 2
LANGUAGE = "hi-IN"


@dataclass(frozen=True)
class Phrase:
    id: str
    text: str
    kind: str  # ack | done | unclear | light | pay
    pace: float = 1.0


def _p(id_: str, text: str, kind: str, pace: float) -> tuple[str, Phrase]:
    return id_, Phrase(id_, text, kind, pace)


PHRASES: dict[str, Phrase] = dict([
    # acknowledgements: brisk
    _p("ack_ji", "Ji.", "ack", 1.05),
    _p("ack_haan_ji", "Haan ji.", "ack", 1.05),
    _p("ack_ek_second", "Ek second.", "ack", 1.05),
    _p("ack_achha", "Achha.", "ack", 1.05),
    _p("ack_dekhte_hain", "Dekhte hain.", "ack", 1.05),
    _p("ack_theek_hai", "Theek hai.", "ack", 1.05),
    _p("ack_boliye", "Boliye ji.", "ack", 1.05),
    _p("ack_bilkul", "Bilkul ji.", "ack", 1.05),
    # confirmations
    _p("done_ho_gaya", "Ho gaya.", "done", 1.05),
    _p("done_ho_gaya_ji", "Ho gaya ji.", "done", 1.05),
    _p("done_lijiye", "Lijiye.", "done", 1.05),
    _p("done_likh_liya", "Likh liya.", "done", 1.05),
    _p("done_kar_diya", "Ji, kar diya.", "done", 1.05),
    _p("done_taiyaar", "Taiyaar hai ji.", "done", 1.0),
    # soft errors
    _p("unclear_dobara", "Samajh nahi aaya, dobara bolna?", "unclear", 1.0),
    _p("unclear_phir_se", "Phir se bolna ji.", "unclear", 1.0),
    _p("unclear_saaf", "Thoda saaf bolna ji?", "unclear", 1.0),
    _p("unclear_sunai_nahi", "Kuch sunai nahi diya, dobara?", "unclear", 1.0),
    # light ones
    _p("light_aur_kuch", "Aur kuch?", "light", 1.05),
    _p("light_bas_itna", "Bas itna ji?", "light", 1.05),
    _p("light_fatafat", "Ek dam fatafat.", "light", 1.05),
    _p("light_koi_baat_nahi", "Koi baat nahi ji.", "light", 1.0),
    _p("light_shukriya", "Shukriya ji.", "light", 1.0),
    # payment
    _p("pay_aa_gaya", "Payment aa gaya.", "pay", 0.97),
])

_ACKS = ["ack_ji", "ack_haan_ji", "ack_achha", "ack_theek_hai", "ack_bilkul"]
_WAIT = ["ack_ek_second", "ack_dekhte_hain"]
_DONE = ["done_ho_gaya", "done_ho_gaya_ji", "done_lijiye", "done_likh_liya", "done_kar_diya"]
_SITUATIONS: dict[str, list[str]] = {
    "added": _ACKS,  # items put in the cart
    "removed": _DONE,
    "changed": _DONE,
    "money": _WAIT,  # a bill / udhaar is being proposed
    "checkout": ["done_taiyaar", "done_lijiye"],
    "paid": ["pay_aa_gaya"],
    "unclear": ["unclear_dobara", "unclear_phir_se", "unclear_saaf"],
    "silent": ["unclear_sunai_nahi"],
    "cancelled": ["ack_theek_hai", "ack_achha"],
    "done": _DONE,
    "wait": _WAIT,
}


def ack_for(situation: str, *, seed: Any = None, session: Optional[str] = None) -> Optional[str]:
    """Phrase id to suggest for a situation; varies per session, deterministic with a seed."""
    options = _SITUATIONS.get(situation)
    if not options:
        return None
    return voice_style.pick(options, key=f"ack:{situation}", seed=seed, session=session)


# ---------------------------------------------------------------------------
# warming and the endpoint payload
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {"task": None, "done": 0}


def _key(p: Phrase) -> str:
    return tts_cache.key_of_line(p.text, LANGUAGE, None, p.pace)


def cached_count() -> int:
    return sum(1 for p in PHRASES.values() if tts_cache.get_cached(_key(p)))


def ready() -> bool:
    """True when every phrase has audio on disk."""
    return cached_count() == len(PHRASES)


def view() -> dict[str, Any]:
    """Payload of GET /api/voice/phrases: {ready, phrases: {id: {text, audio_url, kind}}}.
    audio_url is null until that clip is cached (and always null without TTS: use browser speech)."""
    out = {pid: {"text": p.text, "audio_url": tts_cache.get_cached(_key(p)), "kind": p.kind}
           for pid, p in PHRASES.items()}
    return {"ready": all(v["audio_url"] for v in out.values()), "phrases": out}


async def warm_cache() -> int:
    """Generate every missing clip, CONCURRENCY at a time. Returns the number of clips on disk after.
    Quiet on failure: a clip that cannot be made stays null."""
    if not tts_cache.available():
        return cached_count()
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(p: Phrase) -> None:
        if tts_cache.get_cached(_key(p)):
            return
        async with gate:
            try:
                await tts_cache.ensure(p.text, LANGUAGE, None, p.pace)
            except Exception:  # noqa: BLE001
                log.info("phrase warm-up failed for %s", p.id)

    try:
        await asyncio.gather(*(one(p) for p in PHRASES.values()))
    except Exception:  # noqa: BLE001
        log.info("phrase warm-up stopped early")
    _state["done"] = cached_count()
    return _state["done"]


def start_warmup() -> Optional["asyncio.Task"]:
    """Start the background warm-up once (safe to call again: no-op while running or when skipped)."""
    if not tts_cache.available():
        return None
    task = _state.get("task")
    if task is not None and not task.done():
        return task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    _state["task"] = loop.create_task(warm_cache())
    return _state["task"]
