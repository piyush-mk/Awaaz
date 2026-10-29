"""WhatsApp: Meta Cloud API webhook + the endpoints behind the in-app /wa simulator.

GET  /webhooks/whatsapp            Meta verification handshake
POST /webhooks/whatsapp            inbound messages and delivery receipts (X-Hub-Signature-256 checked
                                   with WA_APP_SECRET when it is set); processed after the 200 response
GET  /api/wa/status                configured?, mode live|simulator, last error, counters
GET  /api/wa/messages              ?since_id=&customer_id=&supplier_id=&phone=&limit=  (oldest first)
GET  /api/wa/conversations         one row per customer/supplier/phone with the last message
POST /api/wa/send                  merchant sends a manual message
POST /api/wa/simulate-inbound      play the customer: text | audio | image (same routing as the webhook)
GET  /api/wa/media/{name}          media saved from inbound messages (audio, images)
GET  /api/wa/orders                WhatsApp orders (PendingAction kind=wa_order)
POST /api/wa/orders/{id}/confirm|cancel
GET  /api/wa/outbox                outgoing messages only (legacy name)

Events: `wa` channel -> wa_message, wa_status; `store` channel -> wa_order, wa_order_updated,
khata_disputed, khata_confirmed (see services/whatsapp.py and services/wa_orders.py).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from models import Customer, Message, PendingAction, Supplier
from schemas import PendingActionOut
from services import events, khata
from services import whatsapp as wa
from services import wa_orders
from services.wa_orders import Inbound

log = logging.getLogger("awaaz.wa_router")

webhook_router = APIRouter()
router = APIRouter()


# ---------------------------------------------------------------------------
# Meta webhook
# ---------------------------------------------------------------------------


@webhook_router.get("")
def verify(hub_mode: str = Query("", alias="hub.mode"),
           hub_verify_token: str = Query("", alias="hub.verify_token"),
           hub_challenge: str = Query("", alias="hub.challenge")):
    """Meta calls this once when the webhook URL is registered."""
    if hub_mode == "subscribe" and hub_verify_token == settings.wa_verify_token:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("verification failed", status_code=403)


def signature_ok(raw: bytes, header: Optional[str], secret: str) -> bool:
    """X-Hub-Signature-256 = 'sha256=' + HMAC-SHA256(app secret, raw body)."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1].strip())


def parse_payload(payload: dict[str, Any]) -> tuple[list[Inbound], list[dict[str, Any]]]:
    """Cloud API webhook body -> (inbound messages, status receipts)."""
    inbound: list[Inbound] = []
    statuses: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
            for st in value.get("statuses") or []:
                statuses.append({"id": st.get("id"), "status": st.get("status"), "errors": st.get("errors")})
            for m in value.get("messages") or []:
                sender = str(m.get("from") or "")
                if not sender:
                    continue
                kind = m.get("type")
                inb = Inbound(phone=sender, wa_id=m.get("id"), channel="wa",
                              context_id=(m.get("context") or {}).get("id"), profile_name=names.get(sender))
                if kind == "text":
                    inb.body = (m.get("text") or {}).get("body", "")
                elif kind in ("audio", "voice"):
                    inb.type = "audio"
                    inb.media_id = (m.get("audio") or {}).get("id")
                    inb.mime = (m.get("audio") or {}).get("mime_type", "")
                    inb.filename = "voice.ogg"
                elif kind == "image":
                    inb.type = "image"
                    inb.media_id = (m.get("image") or {}).get("id")
                    inb.mime = (m.get("image") or {}).get("mime_type", "image/jpeg")
                    inb.body = (m.get("image") or {}).get("caption", "") or ""
                elif kind == "button":
                    b = m.get("button") or {}
                    inb.body = f"{b.get('text', '')} {b.get('payload', '')}".strip()
                elif kind == "interactive":
                    it = m.get("interactive") or {}
                    reply = it.get("button_reply") or it.get("list_reply") or {}
                    inb.body = f"{reply.get('title', '')} {reply.get('id', '')}".strip()
                else:
                    inb.type = "other"
                    inb.body = f"[{kind} message]"
                inbound.append(inb)
    return inbound, statuses


async def process_webhook(inbound: list[Inbound], statuses: list[dict[str, Any]]) -> None:
    """Runs after the 200 has been sent. Own DB session per item; never raises."""
    for st in statuses:
        db = SessionLocal()
        try:
            if st.get("id") and st.get("status"):
                wa.apply_status_update(db, st["id"], st["status"], st.get("errors"))
                db.commit()
        except Exception:  # noqa: BLE001
            log.exception("whatsapp status update failed")
            db.rollback()
        finally:
            db.close()
    for inb in inbound:
        db = SessionLocal()
        try:
            await wa_orders.process(db, inb)
            db.commit()
        except Exception:  # noqa: BLE001
            log.exception("whatsapp inbound processing failed")
            db.rollback()
        finally:
            db.close()


@webhook_router.post("")
async def inbound(request: Request, background: BackgroundTasks):
    raw = await request.body()
    secret = settings.wa_app_secret
    if secret and not signature_ok(raw, request.headers.get("X-Hub-Signature-256"), secret):
        raise HTTPException(status_code=403, detail="invalid X-Hub-Signature-256")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="body is not valid JSON")
    messages, statuses = parse_payload(payload if isinstance(payload, dict) else {})
    background.add_task(process_webhook, messages, statuses)
    return {"status": "ok", "messages": len(messages), "statuses": len(statuses)}


# ---------------------------------------------------------------------------
# serialisation
# ---------------------------------------------------------------------------


def message_dict(m: Message) -> dict[str, Any]:
    return {
        "id": m.id, "channel": m.channel, "direction": m.direction, "type": m.type, "to": m.to,
        "from": m.sender, "body": m.body, "media_ref": m.media_ref, "wa_id": m.wa_id, "status": m.status,
        "customer_id": m.customer_id, "supplier_id": m.supplier_id,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "error": wa.error_for(m.id) if m.status == "failed" else None,
    }


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return wa.status_summary(db)


@router.get("/messages")
def messages(since_id: int = Query(0, ge=0), customer_id: Optional[int] = None,
             supplier_id: Optional[int] = None, phone: Optional[str] = None,
             limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db)):
    q = db.query(Message)
    if since_id:
        q = q.filter(Message.id > since_id)
    if customer_id:
        q = q.filter(Message.customer_id == customer_id)
    if supplier_id:
        q = q.filter(Message.supplier_id == supplier_id)
    rows = q.order_by(Message.id.desc()).limit(limit * 3 if phone else limit).all()
    if phone:
        rows = [m for m in rows if wa.same_phone(m.to, phone) or wa.same_phone(m.sender, phone)][:limit]
    return [message_dict(m) for m in reversed(rows)]


@router.get("/outbox")
def outbox(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(Message).filter(Message.direction == "out").order_by(Message.id.desc()).limit(limit).all()
    return [message_dict(m) for m in rows]


@router.get("/conversations")
def conversations(db: Session = Depends(get_db)):
    customers = {c.id: c for c in db.query(Customer).all()}
    suppliers = {s.id: s for s in db.query(Supplier).all()}
    convs: dict[str, dict[str, Any]] = {}
    for m in db.query(Message).order_by(Message.id).all():
        phone = m.sender if m.direction == "in" else m.to
        if m.customer_id:
            key = f"c{m.customer_id}"
        elif m.supplier_id:
            key = f"s{m.supplier_id}"
        else:
            key = f"p{wa.normalize_phone(phone) or phone or 'unknown'}"
        conv = convs.setdefault(key, {"key": key, "customer_id": m.customer_id, "supplier_id": m.supplier_id,
                                      "name": None, "phone": phone, "count": 0, "inbound_count": 0})
        conv["count"] += 1
        conv["inbound_count"] += 1 if m.direction == "in" else 0
        conv["phone"] = conv["phone"] or phone
        conv["last_message"] = message_dict(m)
        conv["last_at"] = conv["last_message"]["created_at"]
        conv["last_id"] = m.id
    for conv in convs.values():
        if conv["customer_id"] in customers:
            c = customers[conv["customer_id"]]
            conv["name"] = c.name
            conv["phone"] = c.phone or conv["phone"]
        elif conv["supplier_id"] in suppliers:
            s = suppliers[conv["supplier_id"]]
            conv["name"] = s.name
            conv["phone"] = s.phone or conv["phone"]
        else:
            conv["name"] = conv["phone"] or "Unknown"
    return sorted(convs.values(), key=lambda c: -c["last_id"])


class SendIn(BaseModel):
    to: Optional[str] = None
    customer_id: Optional[int] = None
    supplier_id: Optional[int] = None
    body: str = ""
    type: str = "text"
    media_ref: Optional[str] = None


@router.post("/send")
def send(payload: SendIn, db: Session = Depends(get_db)):
    """Merchant sends a manual message (simulator always; Meta too when configured)."""
    to = payload.to
    if payload.customer_id:
        cust = db.get(Customer, payload.customer_id)
        if cust is None:
            raise HTTPException(404, "customer not found")
        to = to or cust.phone
    if payload.supplier_id:
        sup = db.get(Supplier, payload.supplier_id)
        if sup is None:
            raise HTTPException(404, "supplier not found")
        to = to or sup.phone
    if not payload.body and not payload.media_ref:
        raise HTTPException(422, "body or media_ref is required")
    msg = wa.notify(db, to, payload.body, type=payload.type, customer_id=payload.customer_id,
                    supplier_id=payload.supplier_id, media_ref=payload.media_ref)
    db.commit()
    db.refresh(msg)
    return message_dict(msg)


# ---------------------------------------------------------------------------
# simulator: play the customer
# ---------------------------------------------------------------------------


@router.post("/simulate-inbound")
async def simulate_inbound(request: Request, db: Session = Depends(get_db)):
    """The simulator's customer side. multipart/form-data or JSON with:
    from_phone | customer_id, type text|audio|image, body (text, caption, or a typed transcript for
    audio), file (audio/image upload; JSON may send media_base64), demo_phrase (fixture STT phrase 1-10)."""
    ctype = request.headers.get("content-type", "")
    upload = None
    if ctype.startswith("application/json"):
        data = await request.json()
        if not isinstance(data, dict):
            raise HTTPException(422, "JSON object expected")
    else:
        form = await request.form()
        data = {k: v for k, v in form.items() if isinstance(v, str)}
        upload = form.get("file")
    msg_type = str(data.get("type") or "text").lower()
    if msg_type not in ("text", "audio", "image"):
        raise HTTPException(422, "type must be text, audio or image")
    phone = data.get("from_phone") or data.get("from") or data.get("phone")
    if not phone and data.get("customer_id"):
        cust = db.get(Customer, int(data["customer_id"]))
        if cust is None:
            raise HTTPException(404, "customer not found")
        phone = cust.phone
    if not phone:
        raise HTTPException(422, "from_phone or a customer_id with a phone is required")
    inb = Inbound(phone=str(phone), type=msg_type, body=str(data.get("body") or data.get("text") or ""),
                  channel="sim", demo_phrase=data.get("demo_phrase"), profile_name=data.get("name"))
    if upload is not None and hasattr(upload, "read"):
        inb.media_bytes = await upload.read()
        inb.mime = getattr(upload, "content_type", "") or ""
        inb.filename = getattr(upload, "filename", "") or ""
    elif data.get("media_base64"):
        try:
            inb.media_bytes = base64.b64decode(data["media_base64"])
        except Exception:  # noqa: BLE001
            raise HTTPException(422, "media_base64 is not valid base64")
        inb.mime = str(data.get("mime") or "")
        inb.filename = str(data.get("filename") or "")
    if msg_type == "text" and not inb.body:
        raise HTTPException(422, "body is required for text messages")
    result = await wa_orders.process(db, inb)
    db.commit()
    return {"simulated": True, **result}


@router.get("/media/{name}")
def media(name: str):
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(404, "not found")
    path = wa.wa_media_dir() / name
    if not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path)


# ---------------------------------------------------------------------------
# WhatsApp orders (F13)
# ---------------------------------------------------------------------------


@router.get("/orders", response_model=list[PendingActionOut])
def orders(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(PendingAction).filter(PendingAction.kind == "wa_order")
    if status:
        q = q.filter(PendingAction.status == status)
    return q.order_by(PendingAction.id.desc()).limit(50).all()


def _order_or_404(db: Session, action_id: int) -> PendingAction:
    action = db.get(PendingAction, action_id)
    if action is None or action.kind != "wa_order":
        raise HTTPException(404, "order not found")
    return action


def _resolve_order(db: Session, action: PendingAction, new_status: str, text: str) -> PendingAction:
    if action.status != "proposed":
        raise HTTPException(409, f"order is already {action.status}")
    from services.clock import now_local

    action.status = new_status
    action.resolved_at = now_local()
    action.result = {"status": new_status}
    p = action.payload or {}
    wa.notify(db, p.get("phone"), text, customer_id=p.get("customer_id"))
    events.publish("store", "wa_order_updated", {"action_id": action.id, "status": new_status,
                                                 "customer_id": p.get("customer_id"),
                                                 "customer": p.get("customer"), "total": p.get("total")})
    db.commit()
    return action


@router.post("/orders/{action_id}/confirm", response_model=PendingActionOut)
def confirm_order(action_id: int, db: Session = Depends(get_db)):
    action = _order_or_404(db, action_id)
    total = khata.fmt_inr((action.payload or {}).get("total", 0))
    return _resolve_order(db, action, "confirmed",
                          f"Aapka order (₹{total}) pack ho raha hai. Jaldi bhej rahe hain. Dhanyavaad!")


@router.post("/orders/{action_id}/cancel", response_model=PendingActionOut)
def cancel_order(action_id: int, db: Session = Depends(get_db)):
    action = _order_or_404(db, action_id)
    return _resolve_order(db, action, "cancelled",
                          "Maaf kijiye, aapka order abhi poora nahi ho paaya. Dukaan aapko batayegi.")
