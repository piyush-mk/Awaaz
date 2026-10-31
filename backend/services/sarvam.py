"""Sarvam AI client: speech-to-text, text-to-speech, chat (tool calling) and vision.

Every function returns a `Result` (data, source, latency_ms). Provider failures
raise `ProviderError`; the chain/fallback policy lives in llm.py / vision.py and,
for STT, here (fixture when keys are missing or DEMO_MODE=on).

API-CONTRACT UNCERTAINTY (verify with a live key on day 1):
  * vision(): the OpenAI-style `image_url` data-URI content part on
    `/v2/chat/completions` with model `gemma4` is unverified. It is isolated in
    `_vision_payload` so only that function changes if the format differs.
  * tts(): the language field is sent as `language_code`; on HTTP 422 it retries
    once with `target_language_code` and remembers which one worked.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from typing import Any, Optional

from config import settings
from services import fixtures, http
from services.types import ChatOut, ProviderError, Result, Timer, ToolCall

_TTS_LANG_FIELDS = ["language_code", "target_language_code"]
_tts_lang_field_idx = 0  # index into _TTS_LANG_FIELDS that last worked
TTS_MAX_CHARS = 2400

log = logging.getLogger(__name__)


def _headers(json_body: bool = False) -> dict[str, str]:
    h = {"api-subscription-key": settings.sarvam_api_key}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _require_key() -> None:
    if not settings.sarvam_api_key:
        raise ProviderError("SARVAM_API_KEY is not configured", "sarvam")


# ---------------------------------------------------------------------------
# speech to text
# ---------------------------------------------------------------------------


async def stt(audio_bytes: bytes, filename: str = "audio.webm", language: str = "hi-IN",
              keyterms: Optional[list[str]] = None, demo_phrase: Optional[str] = None,
              text: Optional[str] = None) -> Result[dict]:
    """Transcribe audio with one call. Returns data={'transcript', 'language_code'}.

    `text` is a passthrough transcript (typed input) and short-circuits the call.
    `demo_phrase` (the X-Demo-Phrase header) picks a fixture transcript when STT is
    unavailable (no key, DEMO_MODE=on, or a failed call with fixtures allowed)."""
    if text:
        return Result(fixtures.stt_fixture(text=text), "rules", 0)
    if settings.fixtures_only or not settings.has_sarvam:
        if not settings.fixtures_allowed:
            _require_key()
        return Result(fixtures.stt_fixture(demo_phrase), "fixture", 0)
    try:
        return await _stt_call(audio_bytes, filename, language, keyterms or [])
    except Exception as exc:
        if not settings.fixtures_allowed:
            raise exc if isinstance(exc, ProviderError) else ProviderError(str(exc), "sarvam")
        log.warning("speech to text failed: %s", str(exc)[:300])
        if demo_phrase:
            return Result(fixtures.stt_fixture(demo_phrase), "fixture", 0, {"error": str(exc)[:200]})
        # Real speech was not understood. Never swap in a canned order: it would bill what nobody said.
        return Result({"transcript": "", "language_code": language}, "failed", 0, {"error": str(exc)[:200]})


STT_MIME = {"webm": "audio/webm", "ogg": "audio/ogg", "oga": "audio/ogg", "opus": "audio/ogg", "m4a": "audio/mp4",
            "mp4": "audio/mp4", "aac": "audio/aac", "mp3": "audio/mpeg", "mpeg": "audio/mpeg", "wav": "audio/wav"}


async def _stt_call(audio_bytes: bytes, filename: str, language: str, keyterms: list[str]) -> Result[dict]:
    # By extension, not mimetypes: that can answer video/webm, or nothing at all on Windows.
    mime = STT_MIME.get(filename.rsplit(".", 1)[-1].lower(), "audio/webm")
    data = {"model": settings.sarvam_stt_model, "language_code": language}
    if settings.sarvam_stt_mode:
        data["mode"] = settings.sarvam_stt_mode
    terms = [t[:64] for t in keyterms[:50] if t]
    if terms and settings.sarvam_stt_model.startswith("saaras:v4"):  # the API rejects keyterms on older models
        data["keyterms"] = json.dumps(terms, ensure_ascii=False)
    with Timer() as t:
        async with http.client(timeout=20.0) as c:
            resp = await c.post(f"{settings.sarvam_base_url}/speech-to-text", headers=_headers(),
                                files={"file": (filename, audio_bytes, mime)}, data=data)
    if resp.status_code != 200:
        raise ProviderError(http.error_text(resp), "sarvam", resp.status_code)
    body = resp.json()
    return Result({"transcript": (body.get("transcript") or "").strip(),
                   "language_code": body.get("language_code") or language}, "sarvam", t.ms)


# ---------------------------------------------------------------------------
# text to speech
# ---------------------------------------------------------------------------


def format_indian_number(n: int) -> str:
    """12345 -> '12,345'; 1234567 -> '12,34,567'; below 10,000 stays plain (TTS reads 4 digits fine)."""
    if abs(n) < 10000:
        return str(n)
    s = str(abs(n))
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ("-" if n < 0 else "") + ",".join(groups + [tail])


def speak_rupees(amount: float) -> str:
    """Natural rupee phrase: 249 -> '249 rupaye'; 10000 -> '10,000 rupaye';
    249.5 -> '249 rupaye 50 paise'."""
    paise_total = int(round(abs(amount) * 100))
    rupees, paise = divmod(paise_total, 100)
    text = f"{format_indian_number(rupees)} rupaye"
    if paise:
        text += f" {paise} paise"
    return text


def prepare_tts_text(text: str) -> str:
    """Rewrite ₹ amounts and long numbers so Bulbul reads them naturally."""
    def money(m: re.Match) -> str:
        return speak_rupees(float(m.group(1).replace(",", "")))

    out = re.sub(r"(?:₹|Rs\.?)\s*([\d,]+(?:\.\d{1,2})?)", money, text)
    out = re.sub(r"(?<![\d,.])(\d{5,})(?![\d,])", lambda m: format_indian_number(int(m.group(1))), out)
    return out[:TTS_MAX_CHARS]


def _tts_speaker(speaker: Optional[str]) -> str:
    """Voice names differ by model and the API rejects the wrong kind: an old .env must not silence the app."""
    name = speaker or settings.sarvam_tts_speaker
    is_v4 = settings.sarvam_tts_model.startswith("bulbul:v4")
    if is_v4 and "_" not in name:
        return "simran_enhi_customer"
    if not is_v4 and "_" in name:
        return "ritu"
    return name


async def tts(text: str, language: str = "hi-IN", speaker: Optional[str] = None, pace: float = 1.0,
              codec: str = "mp3", sample_rate: Optional[int] = None) -> Result[str]:
    """Synthesize speech. Returns data = base64 audio (`audios[0]` of the response)."""
    global _tts_lang_field_idx
    _require_key()
    payload: dict[str, Any] = {
        "text": prepare_tts_text(text), "model": settings.sarvam_tts_model,
        "speaker": _tts_speaker(speaker), "pace": pace,
        "output_audio_codec": codec,
        "speech_sample_rate": sample_rate or settings.sarvam_tts_sample_rate,
    }
    with Timer() as t:
        async with http.client(timeout=15.0) as c:
            resp = None
            for attempt in range(2):
                field = _TTS_LANG_FIELDS[(_tts_lang_field_idx + attempt) % 2]
                body = {**payload, field: language}
                resp = await c.post(f"{settings.sarvam_base_url}/text-to-speech",
                                    headers=_headers(True), json=body)
                if resp.status_code != 422:
                    if resp.status_code == 200:
                        _tts_lang_field_idx = (_tts_lang_field_idx + attempt) % 2
                    break
    assert resp is not None
    if resp.status_code != 200:
        raise ProviderError(http.error_text(resp), "sarvam", resp.status_code)
    audios = resp.json().get("audios") or []
    if not audios:
        raise ProviderError("TTS response had no audios", "sarvam")
    return Result(audios[0], "sarvam", t.ms)


# ---------------------------------------------------------------------------
# chat (LLM with tool calling)
# ---------------------------------------------------------------------------


def parse_chat_response(body: dict[str, Any], provider: str = "sarvam") -> ChatOut:
    """OpenAI-style completion -> ChatOut. `function.arguments` is a JSON string."""
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("chat response had no choices", provider) from exc
    calls: list[ToolCall] = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ProviderError(f"tool arguments are not valid JSON: {str(raw)[:80]}", provider) from exc
        calls.append(ToolCall(name=fn.get("name", ""), arguments=args, id=tc.get("id", "")))
    return ChatOut(content=(message.get("content") or "").strip(), tool_calls=calls)


async def chat(messages: list[dict[str, Any]], tools: Optional[list[dict]] = None,
               tool_choice: Any = "auto", response_format: Optional[dict] = None,
               timeout: float = 4.0, temperature: float = 0.2, max_tokens: int = 600
               ) -> Result[ChatOut]:
    """One chat completion on sarvam-105b with reasoning off (`reasoning_effort: null`)."""
    _require_key()
    payload: dict[str, Any] = {
        "model": settings.sarvam_llm_model, "messages": messages, "temperature": temperature,
        "max_tokens": max_tokens, "reasoning_effort": None,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    if response_format:
        payload["response_format"] = response_format
    headers = {**_headers(True), "Authorization": f"Bearer {settings.sarvam_api_key}"}
    with Timer() as t:
        async with http.client(timeout=timeout) as c:
            resp = await c.post(f"{settings.sarvam_base_url}/v1/chat/completions",
                                headers=headers, json=payload)
    if resp.status_code != 200:
        raise ProviderError(http.error_text(resp), "sarvam", resp.status_code)
    return Result(parse_chat_response(resp.json()), "sarvam", t.ms)


# ---------------------------------------------------------------------------
# vision
# ---------------------------------------------------------------------------


def _vision_payload(image_bytes: bytes, mime: str, prompt: str,
                    json_schema: Optional[dict]) -> dict[str, Any]:
    """Request body for gemma4 (UNVERIFIED format: OpenAI-style image_url data URI).
    The JSON schema is embedded in the prompt rather than in response_format."""
    text = prompt
    if json_schema:
        text += "\n\nReturn ONLY JSON matching this schema:\n" + json.dumps(json_schema)
    b64 = base64.b64encode(image_bytes).decode()
    return {
        "model": settings.sarvam_vision_model, "temperature": 0, "max_tokens": 2048,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
    }


async def vision(image_bytes: bytes, mime: str, prompt: str,
                 json_schema: Optional[dict] = None, timeout: float = 30.0) -> Result[str]:
    """Ask Sarvam's vision model about an image. Returns data = the raw text reply."""
    _require_key()
    headers = {**_headers(True), "Authorization": f"Bearer {settings.sarvam_api_key}"}
    with Timer() as t:
        async with http.client(timeout=timeout) as c:
            resp = await c.post(f"{settings.sarvam_base_url}/v2/chat/completions", headers=headers,
                                json=_vision_payload(image_bytes, mime, prompt, json_schema))
    if resp.status_code != 200:
        raise ProviderError(http.error_text(resp), "sarvam", resp.status_code)
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("vision response had no content", "sarvam") from exc
    return Result(content if isinstance(content, str) else json.dumps(content), "sarvam", t.ms)
