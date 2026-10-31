"""Disk cache for TTS audio keyed by hash(text, language, speaker, pace).

Repeated phrases ("Payment prapt hua") play instantly. When TTS is unavailable
(no key, API error, DEMO_MODE=on) the result has empty audio and `url=None`, which
tells the UI to use the browser's speechSynthesis instead.

Two ways in:
  * `get_speech(text, ...)`: legacy, awaits generation (still bounded by TIMEOUT_SECONDS). Used by
    explicit "speak this" endpoints.
  * `key_for` / `get_cached` / `ensure`: the non-blocking API. A request path asks `get_cached`
    (a file check, microseconds); on a miss it starts `ensure` in a background task and answers
    at once (see `services/speech.py`). `ensure` never raises, is bounded by TIMEOUT_SECONDS and
    coalesces concurrent callers for one key into a single provider call.
Audio is mp3 at 16 kHz (`settings.sarvam_tts_sample_rate`), generated at the per-line pace.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

from config import settings
from services import sarvam, voice_style
from services.types import ProviderError, Source

log = logging.getLogger("awaaz.tts")

CACHE_SUBDIR = "tts"
URL_PREFIX = "/api/voice/tts"  # served by routers/voice.py
TIMEOUT_SECONDS = 6.0


def cache_dir():
    d = settings.cache_dir / CACHE_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def key_for(text: str, language: str = "hi-IN", speaker: Optional[str] = None, pace: float = 1.0) -> str:
    """Stable 32-hex key of the exact text sent to the engine (call it on already prepared text)."""
    speaker = speaker or settings.sarvam_tts_speaker
    raw = (f"{text}|{language}|{speaker}|{pace:.2f}|{settings.sarvam_tts_model}|"
           f"{settings.sarvam_tts_sample_rate}")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


cache_key = key_for  # old name


def url_for(key: str) -> str:
    return f"{URL_PREFIX}/{key}.mp3"


@dataclass
class Speech:
    audio_base64: str  # empty string means "use browser TTS"
    url: Optional[str]
    key: str
    cached: bool
    source: Source
    latency_ms: int = 0


def path_for(key: str):
    return cache_dir() / f"{key}.mp3"


def read_cached(key: str) -> Optional[bytes]:
    p = path_for(key)
    return p.read_bytes() if p.exists() and p.stat().st_size > 0 else None


def get_cached(key: str) -> Optional[str]:
    """Served URL of the clip when it is already on disk, else None. No network, no waiting."""
    p = path_for(key)
    try:
        return url_for(key) if p.exists() and p.stat().st_size > 0 else None
    except OSError:
        return None


def available() -> bool:
    """True when a TTS call could succeed (a key is set and DEMO_MODE is not on)."""
    return settings.has_sarvam and not settings.fixtures_only


_inflight: dict[str, "asyncio.Future[Speech]"] = {}


async def _generate(spoken: str, language: str, speaker: str, pace: float, key: str) -> Speech:
    """One provider call, written to the cache. Never raises."""
    try:
        result = await asyncio.wait_for(
            sarvam.tts(spoken, language=language, speaker=speaker, pace=pace), TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        log.info("tts timed out for key %s", key)
        return Speech("", None, key, False, "fixture", int(TIMEOUT_SECONDS * 1000))
    except (ProviderError, Exception) as exc:  # noqa: BLE001  (network, 4xx/5xx, bad shape)
        log.info("tts failed for key %s: %s", key, exc.__class__.__name__)
        return Speech("", None, key, False, "fixture", 0)
    audio_b64 = result.data
    if not audio_b64:
        return Speech("", None, key, False, "fixture", result.latency_ms)
    try:
        path_for(key).write_bytes(base64.b64decode(audio_b64))
    except Exception:  # noqa: BLE001
        return Speech(audio_b64, None, key, False, "sarvam", result.latency_ms)
    return Speech(audio_b64, url_for(key), key, False, "sarvam", result.latency_ms)


async def _speech_for_prepared(spoken: str, language: str, speaker: str, pace: float) -> Speech:
    key = key_for(spoken, language, speaker, pace)
    hit = read_cached(key)
    if hit is not None:
        return Speech(base64.b64encode(hit).decode(), url_for(key), key, True, "sarvam", 0)
    if not available():
        return Speech("", None, key, False, "fixture", 0)
    fut = _inflight.get(key)
    if fut is not None and (fut.done() or fut.get_loop() is not asyncio.get_running_loop()):
        fut = None  # stale: finished, or left behind by a loop that no longer exists
    if fut is None:
        fut = asyncio.ensure_future(_generate(spoken, language, speaker, pace, key))
        _inflight[key] = fut
        fut.add_done_callback(lambda _f, k=key: _inflight.pop(k, None))
    return await asyncio.shield(fut)


async def ensure(text: str, language: str = "hi-IN", speaker: Optional[str] = None,
                 pace: float = 1.0) -> Speech:
    """Generate (or fetch) the clip for a display line. Prepares the text with
    `voice_style.prepare_for_tts`, coalesces duplicate keys, never raises, bounded by TIMEOUT_SECONDS."""
    try:
        speaker = speaker or settings.sarvam_tts_speaker
        return await _speech_for_prepared(voice_style.prepare_for_tts(text), language, speaker, pace)
    except Exception:  # noqa: BLE001  (includes CancelledError of a shielded waiter being awaited twice)
        log.exception("tts ensure failed")
        return Speech("", None, key_for(text, language, speaker, pace), False, "fixture", 0)


def key_of_line(text: str, language: str = "hi-IN", speaker: Optional[str] = None,
                pace: float = 1.0) -> str:
    """The cache key `ensure(text, ...)` will use for a display line (prepares the text first)."""
    return key_for(voice_style.prepare_for_tts(text), language, speaker, pace)


async def get_speech(text: str, language: str = "hi-IN", speaker: Optional[str] = None,
                     pace: float = 1.0, speak_rupees: bool = True) -> Speech:
    """Speech for `text`, from cache when possible. Never raises: failure yields
    an empty-audio Speech so callers can fall back to browser TTS."""
    speaker = speaker or settings.sarvam_tts_speaker
    spoken = voice_style.prepare_for_tts(text) if speak_rupees else text
    try:
        return await _speech_for_prepared(spoken, language, speaker, pace)
    except Exception:  # noqa: BLE001
        log.exception("tts get_speech failed")
        return Speech("", None, key_for(spoken, language, speaker, pace), False, "fixture", 0)
