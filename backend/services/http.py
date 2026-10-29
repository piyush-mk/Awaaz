"""One place to build httpx clients so tests can swap in a mock transport."""
from __future__ import annotations

from typing import Optional

import httpx

# Tests set this to an `httpx.MockTransport`; production leaves it None.
TRANSPORT: Optional[httpx.AsyncBaseTransport] = None


def client(timeout: float = 15.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, transport=TRANSPORT)


def error_text(resp: httpx.Response, limit: int = 300) -> str:
    """Short, key-free description of a failed response."""
    return f"HTTP {resp.status_code}: {resp.text[:limit]}"
