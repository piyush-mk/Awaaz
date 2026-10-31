"""LLM provider chain: Sarvam (sarvam-105b) -> OpenRouter -> raise LLMUnavailable.

Callers catch `LLMUnavailable` and fall back to the rules parser
(`services/quantity.py` / `fixtures.rules_tool_calls`); `complete_or_rules` does
that for you. Sarvam gets one retry with backoff on HTTP 503/429 and on timeouts;
OpenRouter retries itself once on 429/503 (credit is limited, so never more).
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from config import settings
from services import fixtures, openrouter, sarvam
from services.types import ChatOut, LLMUnavailable, ProviderError, Result, Timer

RETRY_BACKOFF_SECONDS = 0.4


async def _guarded(call, retries: int = 1) -> Result[ChatOut]:
    """Run an async provider call, retrying once on 503/timeout; map httpx errors."""
    attempt = 0
    while True:
        try:
            return await call()
        except httpx.TimeoutException as exc:
            err = ProviderError(f"timeout: {exc.__class__.__name__}", "llm", 408)
        except httpx.HTTPError as exc:
            err = ProviderError(f"network error: {exc.__class__.__name__}", "llm")
        except ProviderError as exc:
            err = exc
        retryable = err.status in (503, 408, 429)
        if attempt >= retries or not retryable:
            raise err
        attempt += 1
        await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)


async def complete(messages: list[dict[str, Any]], tools: Optional[list[dict]] = None,
                   tool_choice: Any = "auto", response_format: Optional[dict] = None,
                   timeout: float = 4.0) -> Result[ChatOut]:
    """Chat completion via the provider chain. Raises LLMUnavailable if all fail."""
    if settings.fixtures_only:
        raise LLMUnavailable("DEMO_MODE=on: external LLM calls disabled", "llm")
    errors: list[str] = []
    if settings.has_sarvam:
        try:
            return await _guarded(lambda: sarvam.chat(messages, tools, tool_choice,
                                                      response_format, timeout))
        except ProviderError as exc:
            errors.append(f"sarvam: {exc}")
    if settings.has_openrouter:
        try:
            return await _guarded(lambda: openrouter.chat(messages, tools, tool_choice,
                                                          response_format, timeout), retries=0)
        except ProviderError as exc:
            errors.append(f"openrouter: {exc}")
    raise LLMUnavailable("; ".join(errors) or "no LLM provider configured", "llm")


async def complete_or_rules(messages: list[dict[str, Any]], db: Session,
                            tools: Optional[list[dict]] = None, context: str = "counter",
                            timeout: float = 4.0) -> Result[ChatOut]:
    """Try the provider chain; on failure answer with the rules-based tool calls
    (source='rules'). With DEMO_MODE=off the LLMUnavailable error propagates."""
    try:
        return await complete(messages, tools=tools, timeout=timeout)
    except LLMUnavailable:
        if not settings.fixtures_allowed:
            raise
        with Timer() as t:
            out = fixtures.llm_fixture(messages, db, context)
        return Result(out, "fixture" if settings.fixtures_only else "rules", t.ms)
