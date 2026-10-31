"""Provider health for /api/admin/health and the /status page.

States per provider:
  live         key present and the last check (if any) succeeded
  fallback     key present but the last live check failed: calls fall back to fixtures/rules
  fixture      DEMO_MODE=on: external calls are disabled on purpose
  missing_key  no key configured (calls use fixtures/rules, or fail with DEMO_MODE=off)

`effective` says what the app will actually use right now: live | fixture | simulator | none.
Live pings only run when asked (`?live=1`) AND the key exists AND DEMO_MODE is not `on`;
each is one tiny call (a one-word TTS, a one-token chat, a 1x1 image). Key values are
never returned: error text is scrubbed of every configured secret before it is stored.
"""
from __future__ import annotations

import asyncio
import base64
import time
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from services import http, openrouter, sarvam
from services.types import ProviderError

# last live-check result per provider, kept in memory: {name: {"ok", "latency_ms", "error", "at"}}
_last: dict[str, dict[str, Any]] = {}
# remaining OpenRouter credit in dollars from the last live check (None = unknown)
_credits: Optional[float] = None

PROVIDERS = ["sarvam_stt", "sarvam_tts", "sarvam_chat", "sarvam_vision", "openrouter_chat", "openrouter_vision", "whatsapp", "db"]

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _secrets() -> list[str]:
    return [s for s in (settings.sarvam_api_key, settings.openrouter_api_key, settings.wa_token,
                        settings.wa_app_secret) if s]


def scrub(message: str) -> str:
    """Remove every configured secret from a message and truncate it."""
    out = str(message)
    for s in _secrets():
        out = out.replace(s, "***")
    return out[:240]


def record(provider: str, ok: bool, latency_ms: Optional[int] = None, error: Optional[str] = None) -> None:
    """Remember a provider call outcome (live pings call this; other services may too)."""
    _last[provider] = {"ok": ok, "latency_ms": latency_ms, "error": scrub(error) if error else None,
                       "at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def reset() -> None:
    global _credits
    _last.clear()
    _credits = None


def _has_key(name: str) -> bool:
    return {"sarvam_stt": settings.has_sarvam, "sarvam_tts": settings.has_sarvam,
            "sarvam_chat": settings.has_sarvam, "sarvam_vision": settings.has_sarvam,
            "openrouter_chat": settings.has_openrouter, "openrouter_vision": settings.has_openrouter,
            "whatsapp": settings.has_whatsapp, "db": True}[name]


def _model(name: str) -> Optional[str]:
    return {"sarvam_stt": settings.sarvam_stt_model, "sarvam_tts": settings.sarvam_tts_model,
            "sarvam_chat": settings.sarvam_llm_model, "sarvam_vision": settings.sarvam_vision_model,
            "openrouter_chat": settings.openrouter_model,
            "openrouter_vision": settings.openrouter_vision_model}.get(name)


def state_of(name: str) -> dict[str, Any]:
    """Static + last-known status of one provider (no network)."""
    last = _last.get(name)
    if name == "db":
        state, effective = ("live" if last is None or last["ok"] else "fallback"), "live"
    elif settings.fixtures_only:
        state, effective = "fixture", ("simulator" if name == "whatsapp" else "fixture")
    elif not _has_key(name):
        state = "missing_key"
        effective = "simulator" if name == "whatsapp" else ("fixture" if settings.fixtures_allowed else "none")
    elif last is not None and not last["ok"]:
        state, effective = "fallback", ("simulator" if name == "whatsapp" else "fixture")
    else:
        state, effective = "live", "live"
    out = {"name": name, "state": state, "effective": effective, "configured": _has_key(name),
           "model": _model(name), "last_latency_ms": last["latency_ms"] if last else None,
           "last_error": last["error"] if last else None, "last_checked": last["at"] if last else None}
    if name == "openrouter_chat":
        out["credits_remaining"] = _credits  # dollars from the last live check, else None
    return out


async def _timed(name: str, coro) -> None:
    start = time.perf_counter()
    try:
        await coro
        record(name, True, int((time.perf_counter() - start) * 1000))
    except ProviderError as exc:
        record(name, False, int((time.perf_counter() - start) * 1000), str(exc))
    except Exception as exc:  # network errors etc.
        record(name, False, int((time.perf_counter() - start) * 1000), f"{exc.__class__.__name__}: {exc}")


async def _ping_tts(holder: dict) -> None:
    result = await sarvam.tts("Namaste")
    holder["audio"] = base64.b64decode(result.data)


async def _ping_stt(audio: bytes) -> None:
    """Round-trip the clip the TTS ping just made through STT."""
    await sarvam._stt_call(audio, "ping.mp3", "hi-IN", [])


async def _ping_chat() -> None:
    await sarvam.chat([{"role": "user", "content": "hi"}], timeout=10.0, max_tokens=1)


async def _ping_vision() -> None:
    await sarvam.vision(_TINY_PNG, "image/png", "Reply with one word.", timeout=20.0)


async def _ping_openrouter_chat() -> None:
    await openrouter.chat([{"role": "user", "content": "hi"}], timeout=10.0, max_tokens=1)


async def _ping_openrouter_vision() -> None:
    await openrouter.vision(_TINY_PNG, "image/png", "Reply with one word.", timeout=20.0, max_tokens=5)


async def _read_credits() -> None:
    """Remember the remaining OpenRouter credit (dollars); unknown stays None. Never raises."""
    global _credits
    info = await openrouter.credits()
    _credits = info["remaining"] if info else None


async def _ping_whatsapp() -> None:
    """Read-only: fetch the phone number's metadata (sends no message)."""
    async with http.client(timeout=10.0) as c:
        resp = await c.get(f"https://graph.facebook.com/v20.0/{settings.wa_phone_number_id}",
                           headers={"Authorization": f"Bearer {settings.wa_token}"},
                           params={"fields": "display_phone_number,verified_name"})
    if resp.status_code != 200:
        raise ProviderError(http.error_text(resp), "whatsapp", resp.status_code)


def ping_db(db: Session) -> None:
    start = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        record("db", True, int((time.perf_counter() - start) * 1000))
    except Exception as exc:
        record("db", False, None, f"{exc.__class__.__name__}: {exc}")


async def run_live_checks(db: Session) -> list[str]:
    """Ping every provider that has a key. Returns the names that were pinged."""
    ping_db(db)
    if settings.fixtures_only:
        return ["db"]
    holder: dict = {}
    jobs: list[tuple[str, Any]] = []
    if settings.has_sarvam:
        jobs += [("sarvam_tts", _ping_tts(holder)), ("sarvam_chat", _ping_chat()),
                 ("sarvam_vision", _ping_vision())]
    if settings.has_openrouter:
        jobs += [("openrouter_chat", _ping_openrouter_chat()),
                 ("openrouter_vision", _ping_openrouter_vision())]
    if settings.has_whatsapp:
        jobs.append(("whatsapp", _ping_whatsapp()))
    extra = [_read_credits()] if settings.has_openrouter else []
    await asyncio.gather(*[_timed(name, coro) for name, coro in jobs], *extra)
    names = ["db"] + [n for n, _ in jobs]
    if holder.get("audio"):
        await _timed("sarvam_stt", _ping_stt(holder["audio"]))
        names.append("sarvam_stt")
    elif settings.has_sarvam:
        record("sarvam_stt", False, None, "skipped: TTS clip unavailable to feed STT")
    return names


def snapshot() -> dict[str, dict[str, Any]]:
    return {name: state_of(name) for name in PROVIDERS}
