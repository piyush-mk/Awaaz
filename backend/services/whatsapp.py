"""WhatsApp outbox: the one entry point every feature uses to message a customer or supplier.

Contract (stable; Agent B owns the internals and may extend, never change signatures):
    notify(db, to, body, type="text", customer_id=None, supplier_id=None, media_ref=None) -> Message

`notify` is synchronous, performs no network I/O, writes an outbox row (channel "sim") and publishes
a `wa_message` event on the `wa` channel so the in-app simulator updates instantly. Real delivery
through the Meta Cloud API (updating `channel`, `wa_id` and `status`) is added by Agent B behind this
same function, so callers never depend on Meta being reachable.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from models import Message
from services import events


def notify(
    db: Session,
    to: Optional[str],
    body: str,
    type: str = "text",
    customer_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    media_ref: Optional[str] = None,
) -> Message:
    """Queue an outgoing WhatsApp message and announce it on the `wa` event channel."""
    message = Message(
        channel="sim",
        to=to,
        direction="out",
        type=type,
        body=body,
        media_ref=media_ref,
        status="queued",
        customer_id=customer_id,
        supplier_id=supplier_id,
    )
    db.add(message)
    db.flush()
    events.publish(
        "wa",
        "wa_message",
        {
            "id": message.id,
            "to": to,
            "type": type,
            "body": body,
            "media_ref": media_ref,
            "customer_id": customer_id,
            "supplier_id": supplier_id,
        },
    )
    return message
