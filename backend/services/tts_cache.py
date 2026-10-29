"""Disk cache for TTS audio keyed by hash(text, language, speaker, pace).

Repeated phrases ("Payment prapt hua") play instantly. When TTS is unavailable
(no key, API error, DEMO_MODE=on) the result has empty audio and `url=None`, which
tells the UI to use the browser's speechSynthesis instead.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Optional

from config import settings
from services import sarvam
from services.types import ProviderError, Source

CACHE_SUBDIR = "tts"
URL_PREFIX = "/api/voice/tts"  # served by routers/voice.py


def cache_dir():
    d = settings.cache_dir / CACHE_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_key(text: str, language: str, speaker: str, pace: float = 1.0) -> str:
    raw = f"{text}|{language}|{speaker}|{pace:.2f}|{settings.sarvam_tts_model}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


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


async def get_speech(text: str, language: str = "hi-IN", speaker: Optional[str] = None,
                     pace: float = 1.0, speak_rupees: bool = True) -> Speech:
    """Speech for `text`, from cache when possible. Never raises: failure yields
    an empty-audio Speech so callers can fall back to browser TTS."""
    speaker = speaker or settings.sarvam_tts_speaker
    spoken = sarvam.prepare_tts_text(text) if speak_rupees else text
    key = cache_key(spoken, language, speaker, pace)
    hit = read_cached(key)
    if hit is not None:
        return Speech(base64.b64encode(hit).decode(), f"{URL_PREFIX}/{key}.mp3", key, True, "sarvam", 0)
    if settings.fixtures_only or not settings.has_sarvam:
        return Speech("", None, key, False, "fixture", 0)
    try:
        result = await sarvam.tts(spoken, language=language, speaker=speaker, pace=pace)
    except ProviderError:
        return Speech("", None, key, False, "fixture", 0)
    audio_b64 = result.data
    if not audio_b64:
        return Speech("", None, key, False, "fixture", result.latency_ms)
    try:
        path_for(key).write_bytes(base64.b64decode(audio_b64))
    except Exception:
        return Speech(audio_b64, None, key, False, "sarvam", result.latency_ms)
    return Speech(audio_b64, f"{URL_PREFIX}/{key}.mp3", key, False, "sarvam", result.latency_ms)
