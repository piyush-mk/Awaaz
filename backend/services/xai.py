"""xAI Grok vision (fallback for Sarvam gemma4). Same call shape as the old routers/photo.py."""
from __future__ import annotations

import base64
import json
from typing import Optional

from config import settings
from services import http
from services.types import ProviderError, Result, Timer


async def vision(image_bytes: bytes, mime: str, prompt: str, json_schema: Optional[dict] = None,
                 timeout: float = 40.0) -> Result[str]:
    """Ask grok-4.3 about an image. Returns data = raw text reply."""
    if not settings.xai_key:
        raise ProviderError("XAI_KEY is not configured", "xai")
    text = prompt
    if json_schema:
        text += "\n\nReturn ONLY JSON matching this schema:\n" + json.dumps(json_schema)
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": settings.xai_vision_model, "max_tokens": 2048,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
    }
    with Timer() as t:
        async with http.client(timeout=timeout) as c:
            resp = await c.post(f"{settings.xai_base_url}/v1/chat/completions",
                                headers={"Authorization": f"Bearer {settings.xai_key}",
                                         "Content-Type": "application/json"}, json=payload)
    if resp.status_code != 200:
        raise ProviderError(http.error_text(resp), "xai", resp.status_code)
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("xai response had no content", "xai") from exc
    return Result(content, "xai", t.ms)
