"""In-process async pub/sub bus plus a Server-Sent-Events helper.

SINGLE-WORKER ASSUMPTION: subscribers and the bus live in this process's memory,
so uvicorn must run with one worker. With several workers an event published in
one would never reach a subscriber connected to another. For SSE behind Caddy use
`flush_interval -1`.

`publish` is safe to call from sync endpoints (threadpool) and from async code.
"""
from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict, deque
from typing import Any, AsyncIterator, Optional

from sqlalchemy import event as sa_event

HEARTBEAT_SECONDS = 15.0
REPLAY_SIZE = 50


class EventBus:
    """Channels of events. Each event: {id, channel, type, data}."""

    def __init__(self) -> None:
        self._subs: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(list)
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=REPLAY_SIZE))
        self._counter = 0
        self._lock = threading.Lock()

    def publish(self, channel: str, event_type: str, data: Optional[dict[str, Any]] = None) -> dict:
        """Deliver an event to every subscriber of `channel`; returns the event."""
        with self._lock:
            self._counter += 1
            event = {"id": self._counter, "channel": channel, "type": event_type, "data": data or {}}
            self._history[channel].append(event)
            subs = list(self._subs[channel])
        for loop, queue in subs:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:  # loop closed
                self.unsubscribe(channel, queue)
        return event

    def subscribe(self, channel: str) -> asyncio.Queue:
        """Register a queue for the running loop (call from async code)."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subs[channel].append((asyncio.get_running_loop(), queue))
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subs[channel] = [(lp, q) for lp, q in self._subs[channel] if q is not queue]

    def replay(self, channel: str, after_id: int = 0) -> list[dict]:
        with self._lock:
            return [e for e in self._history[channel] if e["id"] > after_id]

    def subscriber_count(self, channel: str) -> int:
        with self._lock:
            return len(self._subs[channel])

    def reset(self) -> None:
        with self._lock:
            self._subs.clear()
            self._history.clear()


bus = EventBus()


def publish(channel: str, event_type: str, data: Optional[dict[str, Any]] = None) -> dict:
    """Module-level shortcut for `bus.publish`."""
    return bus.publish(channel, event_type, data)


def publish_after_commit(db: Any, channel: str, event_type: str, data: Optional[dict[str, Any]] = None) -> None:
    """Publish once `db` has committed, so a screen that refetches on this event reads the new data.
    If the transaction rolls back, nothing is announced."""
    if not db.in_transaction():
        bus.publish(channel, event_type, data)
        return
    sa_event.listen(db, "after_commit", lambda _session: bus.publish(channel, event_type, data), once=True)


def format_sse(event: dict) -> str:
    """Wire format: id / event / data lines followed by a blank line."""
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"


async def sse_stream(channel: str, last_event_id: int = 0,
                     heartbeat: float = HEARTBEAT_SECONDS) -> AsyncIterator[str]:
    """Async generator of SSE frames for `channel`. Replays events after
    `last_event_id`, then streams live ones with a comment heartbeat."""
    queue = bus.subscribe(channel)
    try:
        yield "retry: 2000\n\n"
        # No id line: an id here would reset the browser's Last-Event-ID, and the next reconnect would replay old events.
        yield f"event: hello\ndata: {json.dumps({'channel': channel})}\n\n"
        for event in bus.replay(channel, last_event_id):
            yield format_sse(event)
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield format_sse(event)
    finally:
        bus.unsubscribe(channel, queue)
