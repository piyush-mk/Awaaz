"""Server-Sent Events: GET /api/events?channel=store (single uvicorn worker)."""
from typing import Optional

from fastapi import APIRouter, Header, Query
from fastapi.responses import StreamingResponse

from services import events

router = APIRouter()


@router.get("/events")
async def stream(channel: str = Query("store", min_length=1, max_length=64),
                 last_event_id: Optional[str] = Header(None, alias="Last-Event-ID")):
    """Live events for the Soundbox, app and WhatsApp simulator."""
    try:
        after = int(last_event_id) if last_event_id else 0
    except ValueError:
        after = 0
    return StreamingResponse(
        events.sse_stream(channel, after), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
