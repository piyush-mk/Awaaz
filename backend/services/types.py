"""Shared small types for provider services.

Every AI-facing service returns a `Result`: the payload plus where it came from
and how long it took. The UI shows `source` and `latency_ms` as a chip.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, Optional, TypeVar

Source = Literal["sarvam", "openrouter", "rules", "fixture", "failed"]  # failed: speech that could not be transcribed

T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    """Envelope returned by every provider call."""

    data: T
    source: Source
    latency_ms: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def envelope(self) -> dict[str, Any]:
        """JSON-friendly {data, source, latency_ms} (matches schemas.AIResult)."""
        return {"data": self.data, "source": self.source, "latency_ms": self.latency_ms}


@dataclass
class ToolCall:
    """One LLM tool call with its JSON arguments already decoded."""

    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass
class ChatOut:
    """Parsed chat completion: text and/or tool calls."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class ProviderError(RuntimeError):
    """A provider call failed (network, HTTP status, bad shape, missing key)."""

    def __init__(self, message: str, provider: str = "", status: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.status = status


class LLMUnavailable(ProviderError):
    """No LLM provider answered; callers should fall back to the rules parser."""


class Timer:
    """`with Timer() as t: ...; t.ms` -> elapsed milliseconds."""

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        self.ms = 0
        return self

    def __exit__(self, *exc) -> None:
        self.ms = int((time.perf_counter() - self._start) * 1000)

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)
