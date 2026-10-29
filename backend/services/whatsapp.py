"""WhatsApp outbox: the one entry point every feature uses to message a customer or supplier.

Contract (stable; Agent B owns the internals and may extend, never change signatures):
    notify(db, to, body, type="text", customer_id=None, supplier_id=None, media_ref=None) -> Message

`notify` is synchronous and performs no network I/O. It writes an outbox row (channel "sim") and
publishes a `wa_message` event on the `wa` channel so the in-app simulator updates instantly.

Real delivery (Meta WhatsApp Cloud API) is added behind the same function: when WA_TOKEN and
WA_PHONE_NUMBER_ID are configured and the recipient has a phone, the message is ALSO sent through the
Graph API. The send is scheduled to run right after the caller's transaction commits (SQLAlchemy
`after_commit`), on a background thread, so it never blocks the request and never raises into callers.
On success the row becomes channel="wa", wa_id=<wamid>, status="sent". On failure the row stays in the
simulator (channel "sim") with status="failed" and a clear reason (see `error_for`, the `wa_status`
event and GET /api/wa/status). The 24-hour customer-service window is the usual cause on a test number.

Events on the `wa` channel:
    wa_message  {id, to, type, body, media_ref, customer_id, supplier_id}   (direction out when absent)
    wa_status   {id, status, channel, wa_id, error}                          (after a real send attempt)
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import re
import threading
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Customer, KhataEntry, Message, Supplier
from services import events, http
from services.clock import now_local

log = logging.getLogger("awaaz.whatsapp")

GRAPH_BASE = "https://graph.facebook.com/v21.0"
WINDOW_CLOSED_CODE = 131047  # "Re-engagement message": more than 24h since the user last wrote
NOT_ALLOWED_CODE = 131030  # recipient not in the test number's allowed list
WINDOW_REASON = ("24-hour window closed: the customer must send a message to the shop number first "
                 "(ask them to send 'hi'). Message kept in the simulator.")

# Filled by the module for GET /api/wa/status and the simulator.
STATE: dict[str, Any] = {"last_error": None, "last_error_at": None, "sent": 0, "failed": 0}
_ERRORS: dict[int, str] = {}  # message id -> failure reason (bounded)
_KHATA_LINKS: dict[int, int] = {}  # message id -> KhataEntry id whose wa_status follows delivery
_MAX_TRACKED = 500


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def normalize_phone(raw: Optional[str], default_cc: str = "91") -> Optional[str]:
    """Digits-only E.164 without '+': '98100 00002' -> '919810000002'. None if unusable."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10:
        digits = default_cc + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = default_cc + digits[1:]
    if not 8 <= len(digits) <= 15:
        return None
    return digits


def e164(raw: Optional[str]) -> Optional[str]:
    """'+919810000002' form of `normalize_phone`."""
    digits = normalize_phone(raw)
    return f"+{digits}" if digits else None


def same_phone(a: Optional[str], b: Optional[str]) -> bool:
    """True when two phone strings refer to the same number (compares the last 10 digits)."""
    da, db_ = normalize_phone(a), normalize_phone(b)
    return bool(da and db_ and da[-10:] == db_[-10:])


def find_customer_by_phone(db: Session, phone: Optional[str]) -> Optional[Customer]:
    target = normalize_phone(phone)
    if not target:
        return None
    for c in db.query(Customer).filter(Customer.phone.isnot(None)).order_by(Customer.id).all():
        if same_phone(c.phone, target):
            return c
    return None


def find_supplier_by_phone(db: Session, phone: Optional[str]) -> Optional[Supplier]:
    target = normalize_phone(phone)
    if not target:
        return None
    for s in db.query(Supplier).filter(Supplier.phone.isnot(None)).order_by(Supplier.id).all():
        if same_phone(s.phone, target):
            return s
    return None


def error_for(message_id: int) -> Optional[str]:
    """Why a delivery failed (None if it did not or the process restarted)."""
    return _ERRORS.get(message_id)


def link_khata_entry(message_id: int, entry_id: int) -> None:
    """Make delivery results update `KhataEntry.wa_status` for that entry."""
    if len(_KHATA_LINKS) > _MAX_TRACKED:
        _KHATA_LINKS.clear()
    _KHATA_LINKS[message_id] = entry_id


def _remember_error(message_id: int, reason: str) -> None:
    if len(_ERRORS) > _MAX_TRACKED:
        _ERRORS.clear()
    _ERRORS[message_id] = reason
    STATE["last_error"] = reason
    STATE["last_error_at"] = now_local().isoformat(timespec="seconds")
    STATE["failed"] += 1


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.wa_token}"}


def explain_error(resp: httpx.Response) -> tuple[str, Optional[int]]:
    """Human reason + Meta error code from a failed Graph response."""
    code: Optional[int] = None
    detail = http.error_text(resp, 240)
    try:
        err = resp.json().get("error") or {}
        code = err.get("code")
        detail = err.get("error_data", {}).get("details") or err.get("message") or detail
    except Exception:  # noqa: BLE001 - non-JSON body
        pass
    if code == WINDOW_CLOSED_CODE:
        return WINDOW_REASON, code
    if code == NOT_ALLOWED_CODE:
        return ("Recipient is not on the allowed list of the WhatsApp test number "
                "(add them in the Meta dashboard). Message kept in the simulator."), code
    if code == 190:
        return "WhatsApp access token is invalid or expired (WA_TOKEN).", code
    return f"WhatsApp send failed: {detail}"[:300], code


# ---------------------------------------------------------------------------
# media resolution
# ---------------------------------------------------------------------------


def wa_media_dir() -> Path:
    d = settings.cache_dir / "wa"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_media(ref: Optional[str]) -> Optional[tuple[str, Any]]:
    """('url', https-url) | ('file', Path) | None for a Message.media_ref."""
    if not ref:
        return None
    ref = str(ref)
    if ref.startswith(("http://", "https://")):
        return "url", ref
    name = ref.rsplit("/", 1)[-1]
    if ref.startswith("/api/voice/tts/"):
        from services import tts_cache  # local import: keeps module import light

        p = tts_cache.path_for(name.rsplit(".", 1)[0])
        if p.exists():
            return "file", p
    if ref.startswith("/api/wa/media/"):
        p = wa_media_dir() / name
        if p.exists():
            return "file", p
    try:
        p = Path(ref)
        if p.is_file():
            return "file", p
    except OSError:
        pass
    if ref.startswith("/"):
        return "url", settings.public_base_url.rstrip("/") + ref
    return None


async def _upload_media(client: httpx.AsyncClient, path: Path, mime: str) -> str:
    resp = await client.post(
        f"{GRAPH_BASE}/{settings.wa_phone_number_id}/media", headers=_auth(),
        data={"messaging_product": "whatsapp", "type": mime},
        files={"file": (path.name, path.read_bytes(), mime)})
    if resp.status_code >= 400:
        raise _SendError(*explain_error(resp))
    media_id = resp.json().get("id")
    if not media_id:
        raise _SendError("WhatsApp media upload returned no id", None)
    return str(media_id)


class _SendError(Exception):
    def __init__(self, reason: str, code: Optional[int]):
        super().__init__(reason)
        self.reason = reason
        self.code = code


async def build_payload(client: httpx.AsyncClient, msg_type: str, to: str, body: Optional[str],
                        media_ref: Optional[str]) -> dict[str, Any]:
    """Graph API message body for our Message fields (uploads local media first)."""
    payload: dict[str, Any] = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}
    media = _resolve_media(media_ref) if msg_type in ("audio", "image", "doc", "document") else None
    if media is None:
        if not body:
            raise _SendError(f"{msg_type} message has no usable media and no text", None)
        payload.update(type="text", text={"preview_url": True, "body": body})
        return payload
    kind, value = media
    graph_type = {"doc": "document"}.get(msg_type, msg_type)
    holder: dict[str, Any] = {}
    if kind == "url":
        holder["link"] = value
    else:
        mime = mimetypes.guess_type(value.name)[0] or ("audio/mpeg" if graph_type == "audio"
                                                       else "application/octet-stream")
        holder["id"] = await _upload_media(client, value, mime)
    if graph_type in ("image", "document") and body:
        holder["caption"] = body
    if graph_type == "document":
        holder["filename"] = Path(str(media_ref)).name or "document"
    payload.update(type=graph_type, **{graph_type: holder})
    return payload


# ---------------------------------------------------------------------------
# delivery
# ---------------------------------------------------------------------------


async def deliver(message_id: int) -> bool:
    """Send one outbox row through the Graph API. NEVER raises; returns True on success.

    No-op (False) when keys are absent, the row is gone/already sent, or no phone is known."""
    if not settings.has_whatsapp:
        return False
    db = SessionLocal()
    try:
        msg = db.get(Message, message_id)
        if msg is None or msg.direction != "out" or msg.channel == "wa":
            return False
        phone = normalize_phone(msg.to)
        if not phone and msg.customer_id:
            cust = db.get(Customer, msg.customer_id)
            phone = normalize_phone(cust.phone) if cust else None
        if not phone and msg.supplier_id:
            sup = db.get(Supplier, msg.supplier_id)
            phone = normalize_phone(sup.phone) if sup else None
        if not phone:
            return False
        ok, wa_id, reason = False, None, None
        try:
            async with http.client(timeout=20.0) as client:
                payload = await build_payload(client, msg.type or "text", phone, msg.body, msg.media_ref)
                resp = await client.post(f"{GRAPH_BASE}/{settings.wa_phone_number_id}/messages",
                                         headers={**_auth(), "Content-Type": "application/json"},
                                         json=payload)
            if resp.status_code >= 400:
                reason, _ = explain_error(resp)
            else:
                wa_id = ((resp.json().get("messages") or [{}])[0]).get("id")
                ok = True
        except _SendError as exc:
            reason = exc.reason
        except Exception as exc:  # noqa: BLE001 - network errors, timeouts, bad JSON
            reason = f"WhatsApp send error: {exc.__class__.__name__}"
        if ok:
            msg.channel, msg.wa_id, msg.status = "wa", wa_id, "sent"
            STATE["sent"] += 1
        else:
            msg.status = "failed"
            _remember_error(msg.id, reason or "unknown error")
            log.warning("whatsapp delivery failed for message %s: %s", msg.id, reason)
        _sync_khata(db, msg)
        db.commit()
        events.publish("wa", "wa_status", {"id": msg.id, "status": msg.status, "channel": msg.channel,
                                           "wa_id": msg.wa_id, "error": None if ok else reason})
        return ok
    except Exception:  # noqa: BLE001 - delivery must never raise
        log.exception("whatsapp deliver crashed for message %s", message_id)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        db.close()


def _sync_khata(db: Session, msg: Message) -> None:
    entry_id = _KHATA_LINKS.pop(msg.id, None)
    if entry_id:
        entry = db.get(KhataEntry, entry_id)
        if entry is not None:
            entry.wa_status = "sent" if msg.status == "sent" else "failed"


def _run_in_thread(message_id: int) -> None:
    def runner() -> None:
        try:
            asyncio.run(deliver(message_id))
        except Exception:  # noqa: BLE001
            log.exception("whatsapp delivery thread crashed")

    threading.Thread(target=runner, name=f"wa-send-{message_id}", daemon=True).start()


# Tests replace this with a plain `list.append` and then `await deliver(id)` deterministically.
_schedule: Callable[[int], None] = _run_in_thread


def _will_deliver(msg: Message, db: Session) -> bool:
    """True when `deliver` will have a phone number and keys for this row."""
    if not settings.has_whatsapp:
        return False
    if normalize_phone(msg.to):
        return True
    if msg.customer_id:
        cust = db.get(Customer, msg.customer_id)
        if cust and normalize_phone(cust.phone):
            return True
    if msg.supplier_id:
        sup = db.get(Supplier, msg.supplier_id)
        if sup and normalize_phone(sup.phone):
            return True
    return False


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
    try:
        if _will_deliver(message, db):
            message_id = message.id
            sa_event.listen(db, "after_commit", lambda _session: _schedule(message_id), once=True)
    except Exception:  # noqa: BLE001 - real delivery is best effort; the sim copy already exists
        log.exception("could not schedule whatsapp delivery")
    return message


# ---------------------------------------------------------------------------
# inbound helpers (media download, status webhooks)
# ---------------------------------------------------------------------------


async def download_media(media_id: str) -> tuple[bytes, str]:
    """Graph API: GET /{media_id} for the temporary URL, then GET the bytes. Raises on failure."""
    if not settings.wa_token:
        raise RuntimeError("WA_TOKEN is not configured; cannot download WhatsApp media")
    async with http.client(timeout=30.0) as client:
        meta = await client.get(f"{GRAPH_BASE}/{media_id}", headers=_auth())
        if meta.status_code >= 400:
            raise RuntimeError(explain_error(meta)[0])
        info = meta.json()
        url = info.get("url")
        if not url:
            raise RuntimeError("media lookup returned no url")
        blob = await client.get(url, headers=_auth())
        if blob.status_code >= 400:
            raise RuntimeError(explain_error(blob)[0])
        return blob.content, info.get("mime_type") or blob.headers.get("content-type", "")


def apply_status_update(db: Session, wa_id: str, status: str, errors: Optional[list] = None) -> Optional[Message]:
    """Meta delivery receipt (sent|delivered|read|failed) for an outgoing message id."""
    msg = db.query(Message).filter(Message.wa_id == wa_id, Message.direction == "out").first()
    if msg is None:
        return None
    reason = None
    if status == "failed":
        err = (errors or [{}])[0] or {}
        reason = WINDOW_REASON if err.get("code") == WINDOW_CLOSED_CODE else (
            f"WhatsApp reported failure: {err.get('title') or err.get('message') or 'unknown'}")
        _remember_error(msg.id, reason)
    msg.status = status
    entry_id = _KHATA_LINKS.get(msg.id)
    entry = db.get(KhataEntry, entry_id) if entry_id else None
    if entry is not None:
        entry.wa_status = {"read": "delivered"}.get(status, status)
    events.publish("wa", "wa_status", {"id": msg.id, "status": status, "channel": msg.channel,
                                       "wa_id": wa_id, "error": reason})
    return msg


def status_summary(db: Session) -> dict[str, Any]:
    """Payload for GET /api/wa/status."""
    base = settings.public_base_url.rstrip("/")
    return {
        "configured": settings.has_whatsapp,
        "mode": "live" if settings.has_whatsapp else "simulator",
        "phone_number_id": settings.wa_phone_number_id or None,
        "app_secret_set": bool(settings.wa_app_secret),
        "webhook_url": f"{base}/webhooks/whatsapp",
        "verify_token_set": bool(settings.wa_verify_token),
        "last_error": STATE["last_error"],
        "last_error_at": STATE["last_error_at"],
        "sent": STATE["sent"],
        "failed": STATE["failed"],
        "outbox_total": db.query(Message).filter(Message.direction == "out").count(),
        "inbound_total": db.query(Message).filter(Message.direction == "in").count(),
        "window_note": ("Free-form messages only work within 24h of the customer's last message "
                        "to the shop number; each demo phone should send 'hi' first."),
    }
