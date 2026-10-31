"""Non-blocking speech for replies: the response never waits for TTS.

`request(text, ...)` returns the `speech` object every voice-bearing response and event carries:

    {text, pace, pending, key, audio_url, ack}

  * audio already cached  -> pending false, audio_url set
  * not cached            -> pending true, key set, audio_url null. One background task per key
                             (duplicates coalesce) generates the clip, bounded by
                             `tts_cache.TIMEOUT_SECONDS`, then publishes on channel `store`:
                             `speech_ready {session_id, key, audio_url, text, source}`.
                             `source` is "sarvam" or "fixture"; for fixture / no key / failure
                             audio_url is null and the client speaks `text` with browser speech.
  * speak=false / no text -> pending false, key null, audio_url null

`ack` is the id of a phrase-bank clip (services/phrases.py) the client may play instantly.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from services import events, tts_cache, voice_style

log = logging.getLogger("awaaz.speech")

_tasks: dict[str, "asyncio.Task"] = {}  # key -> the single generation task (also keeps a strong ref)
_waiters: dict[str, dict[str, str]] = {}  # key -> {session_id: display text} to notify when ready


async def _run(key: str, text: str, language: str, speaker: Optional[str], pace: float) -> None:
    try:
        sp = await tts_cache.ensure(text, language, speaker, pace)
        url, source = sp.url, ("sarvam" if sp.url else "fixture")
    except asyncio.CancelledError:
        _tasks.pop(key, None)
        _waiters.pop(key, None)
        raise
    except Exception:  # noqa: BLE001  (never raises into the event loop)
        log.exception("speech task failed")
        url, source = None, "fixture"
    # No await below: waiters registered before this point are all notified, later ones start a new task.
    waiting = _waiters.pop(key, {})
    _tasks.pop(key, None)
    for session_id, shown in waiting.items():
        try:
            events.publish("store", "speech_ready", {"session_id": session_id or None, "key": key,
                                                     "audio_url": url, "text": shown, "source": source})
        except Exception:  # noqa: BLE001
            log.exception("could not publish speech_ready")


def request(text: str, *, kind: Optional[str] = None, pace: Optional[float] = None,
            session_id: Optional[str] = None, speak: bool = True, ack: Optional[str] = None,
            language: str = "hi-IN") -> dict:
    """The `speech` object for a reply (see module docstring). Schedules generation when needed."""
    text = (text or "").strip()
    pace = round(pace if pace is not None else voice_style.pace_for(kind, text), 2)
    base = {"text": text, "pace": pace, "pending": False, "key": None, "audio_url": None, "ack": ack}
    if not (speak and text):
        return base
    speaker = None  # the configured default
    key = tts_cache.key_of_line(text, language, speaker, pace)
    base["key"] = key
    url = tts_cache.get_cached(key)
    if url:
        base["audio_url"] = url
        return base
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # called outside an event loop: nothing can be scheduled
        return {**base, "key": None}
    base["pending"] = True
    _waiters.setdefault(key, {})[session_id or ""] = text
    old = _tasks.get(key)
    if old is not None and (old.done() or old.get_loop() is not loop):
        _tasks.pop(key, None)  # stale (finished, or from a loop that is gone)
    if key not in _tasks:
        _tasks[key] = loop.create_task(_run(key, text, language, speaker, pace))
    return base


def spoken_of(speech: Optional[dict]) -> Optional[str]:
    """audio_url for the legacy `audio_url` response field (null while pending)."""
    return speech.get("audio_url") if speech else None


def pending_keys() -> list[str]:
    return list(_tasks)
