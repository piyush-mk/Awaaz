"""OpenRouter client: backup provider for chat/tool calling and vision.

Chain position: Sarvam is primary; OpenRouter answers when Sarvam is missing or fails
(see llm.py and vision.py). OpenAI-compatible `POST {base}/chat/completions`.

Cost control: the shared account has little credit, so max_tokens stays modest
(chat 800, vision 2500), temperature is 0, and there is exactly one retry, only on
HTTP 429/503. `usage.include` makes OpenRouter return the dollar `usage.cost`, which is
recorded in `Result.meta` (`cost`, `prompt_tokens`, `completion_tokens`, `model`).
The API key is scrubbed from every error string.
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Optional

import httpx

from config import settings
from services import http, sarvam
from services.types import ChatOut, ProviderError, Result, Timer

PROVIDER = "openrouter"
RETRY_BACKOFF_SECONDS = 0.6
RETRY_STATUSES = (429, 503)
CHAT_MAX_TOKENS = 800
VISION_MAX_TOKENS = 2500
REFERER = "https://github.com/piyush-mk/Awaaz"
TITLE = "Awaaz"


def _require_key() -> None:
    if not settings.openrouter_api_key:
        raise ProviderError("OPENROUTER_API_KEY is not configured", PROVIDER)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json",
            "HTTP-Referer": REFERER, "X-Title": TITLE}


def _scrub(text: str) -> str:
    key = settings.openrouter_api_key
    return text.replace(key, "***") if key else text


def _error(resp: httpx.Response) -> ProviderError:
    return ProviderError(_scrub(http.error_text(resp)), PROVIDER, resp.status_code)


async def _post(payload: dict[str, Any], timeout: float) -> httpx.Response:
    """POST /chat/completions; retry once on 429/503; network errors become ProviderError."""
    url = f"{settings.openrouter_base_url}/chat/completions"
    attempt = 0
    while True:
        try:
            async with http.client(timeout=timeout) as c:
                resp = await c.post(url, headers=_headers(), json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"timeout: {exc.__class__.__name__}", PROVIDER, 408) from None
        except httpx.HTTPError as exc:
            raise ProviderError(f"network error: {exc.__class__.__name__}", PROVIDER) from None
        if resp.status_code in RETRY_STATUSES and attempt < 1:
            attempt += 1
            await asyncio.sleep(RETRY_BACKOFF_SECONDS)
            continue
        return resp


def _usage_meta(body: dict[str, Any]) -> dict[str, Any]:
    """Model, dollar cost and token counts from the response's `usage` block."""
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    meta: dict[str, Any] = {"model": body.get("model")}
    for key, name in (("cost", "cost"), ("prompt_tokens", "prompt_tokens"),
                      ("completion_tokens", "completion_tokens")):
        if usage.get(key) is not None:
            meta[name] = usage[key]
    return meta


def _json_body(resp: httpx.Response) -> dict[str, Any]:
    try:
        body = resp.json()
    except ValueError as exc:
        raise ProviderError("response was not JSON", PROVIDER) from exc
    if not isinstance(body, dict):
        raise ProviderError("response was not a JSON object", PROVIDER)
    return body


async def chat(messages: list[dict[str, Any]], tools: Optional[list[dict]] = None,
               tool_choice: Any = "auto", response_format: Optional[dict] = None,
               timeout: float = 4.0, max_tokens: int = CHAT_MAX_TOKENS) -> Result[ChatOut]:
    """One chat completion (default anthropic/claude-haiku-5.5), temperature 0."""
    _require_key()
    payload: dict[str, Any] = {
        "model": settings.openrouter_model, "messages": messages, "temperature": 0,
        "max_tokens": max_tokens, "usage": {"include": True},
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    if response_format:
        payload["response_format"] = response_format
    with Timer() as t:
        resp = await _post(payload, timeout)
    if resp.status_code != 200:
        raise _error(resp)
    body = _json_body(resp)
    return Result(sarvam.parse_chat_response(body, PROVIDER), PROVIDER, t.ms, _usage_meta(body))


async def vision(image_bytes: bytes, mime: str, prompt: str, schema: Optional[dict] = None,
                 timeout: float = 40.0, max_tokens: int = VISION_MAX_TOKENS) -> Result[str]:
    """Ask the vision model (default google/gemini-3.1-flash-lite) about an image.
    Returns data = the raw text reply; the JSON schema travels inside the prompt."""
    _require_key()
    text = prompt
    if schema:
        text += "\n\nReturn ONLY JSON matching this schema, no prose:\n" + json.dumps(schema)
    b64 = base64.b64encode(image_bytes).decode()
    payload: dict[str, Any] = {
        "model": settings.openrouter_vision_model, "temperature": 0, "max_tokens": max_tokens,
        "usage": {"include": True},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
    }
    with Timer() as t:
        resp = await _post(payload, timeout)
    if resp.status_code != 200:
        raise _error(resp)
    body = _json_body(resp)
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("vision response had no content", PROVIDER) from exc
    return Result(content if isinstance(content, str) else json.dumps(content), PROVIDER, t.ms,
                  _usage_meta(body))


async def credits(timeout: float = 8.0) -> Optional[dict[str, float]]:
    """Remaining account credit in dollars: {total_credits, total_usage, remaining}.
    Returns None on any problem (no key, DEMO_MODE=on, HTTP or parse error). Never raises."""
    if not settings.openrouter_api_key or settings.fixtures_only:
        return None
    try:
        async with http.client(timeout=timeout) as c:
            resp = await c.get(f"{settings.openrouter_base_url}/credits", headers=_headers())
        if resp.status_code != 200:
            return None
        data = resp.json()["data"]
        total, used = float(data["total_credits"]), float(data["total_usage"])
    except Exception:  # noqa: BLE001 - credits are advisory; never break a health check
        return None
    return {"total_credits": total, "total_usage": used, "remaining": round(total - used, 4)}
