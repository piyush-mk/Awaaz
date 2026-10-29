"""Inbound WhatsApp routing (shared by the Meta webhook and the simulator endpoint).

One entry point, `process(db, Inbound)`, so a real customer message and the in-app simulator take the
exact same path:

  1. dedupe by wa_id, find the customer by phone, save media under cache/wa
  2. audio -> STT (services.sarvam.stt), image -> vision 'parchi'; the transcript / list becomes the body
  3. store the inbound Message and publish `wa_message` (direction "in") on the `wa` channel
  4. route:
       * short text "galat/wrong/nahi"  -> latest KhataEntry disputed, `khata_disputed` on `store`
       * short text "sahi/ok/theek/haan" -> latest KhataEntry confirmed_by_customer, `khata_confirmed`
       * audio / image / order-like text -> PendingAction(kind="wa_order", status "proposed"), packing
         list + UPI pay link replied to the customer, `wa_order` on `store`
       * "hi" -> a short greeting that tells the customer what they can send

The caller owns the transaction (commit after `process`).
"""
from __future__ import annotations

import logging
import mimetypes
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from config import settings
from models import Customer, Message, PendingAction
from services import catalog, events, khata, quantity, sarvam, vision
from services import whatsapp as wa
from services.clock import now_local

log = logging.getLogger("awaaz.wa_orders")

DISPUTE_WORDS = {"galat", "ghalat", "wrong", "nahi", "nahin", "nhi", "no", "incorrect", "jhooth", "गलत", "नहीं"}
CONFIRM_WORDS = {"sahi", "sahee", "ok", "okay", "theek", "thik", "haan", "han", "ha", "yes", "correct",
                 "right", "👍", "सही", "ठीक", "हाँ", "हां"}
GREETINGS = {"hi", "hii", "hello", "hey", "namaste", "namaskar", "नमस्ते"}
MAX_REPLY_WORDS = 6


@dataclass
class Inbound:
    phone: str
    type: str = "text"  # text | audio | image | other
    body: str = ""  # text, caption, or (simulator audio) a typed transcript
    media_id: Optional[str] = None  # Meta media id, downloaded via the Graph API
    media_bytes: Optional[bytes] = None
    mime: str = ""
    filename: str = ""
    wa_id: Optional[str] = None
    context_id: Optional[str] = None
    channel: str = "wa"  # "wa" real webhook, "sim" simulator
    demo_phrase: Optional[str] = None
    profile_name: Optional[str] = None


# ---------------------------------------------------------------------------
# text classification
# ---------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    out = []
    for raw in (text or "").lower().replace("_", " ").split():
        t = raw.strip(".,!?;:'\"()[]{}-*~")
        if t:
            out.append(t)
    return out


def classify_reply(text: str) -> Optional[str]:
    """'dispute' | 'confirm' | None for a short customer reply to a khata confirmation."""
    toks = _tokens(text)
    if not toks or len(toks) > MAX_REPLY_WORDS:
        return None
    if any(t in DISPUTE_WORDS for t in toks):
        return "dispute"
    if any(t in CONFIRM_WORDS for t in toks):
        return "confirm"
    return None


# ---------------------------------------------------------------------------
# order building
# ---------------------------------------------------------------------------


def _qty_text(qty: float, unit: str) -> str:
    return f"{qty:g} {unit}".strip()


def packing_list_text(name: str, lines: list[dict], unmatched: list[dict], total: float, pay: str) -> str:
    rows = [f"{i}. {l['name']} x {_qty_text(l['qty'], l.get('unit') or '')} - ₹{khata.fmt_inr(l['line_total'])}"
            for i, l in enumerate(lines, 1)]
    text = f"Namaste {name}! Aapka order mil gaya:\n" + "\n".join(rows)
    text += f"\nKul: ₹{khata.fmt_inr(total)}"
    if unmatched:
        text += "\nYe abhi nahi mile, dukaan se puchh kar bataenge: " + ", ".join(u["name"] for u in unmatched)
    text += (f"\nPaise bhejein (UPI): {pay}\nYa ₹{khata.fmt_inr(total)} {settings.merchant_upi_vpa} par bhej dein."
             "\nPayment ke baad hum pack karke bhej dete hain.")
    return text


def create_order(db: Session, customer: Optional[Customer], phone: str, lines: list[Any],
                 unmatched: list[dict], transcript: str, input_type: str, source: str, latency_ms: int,
                 media_ref: Optional[str], profile_name: Optional[str] = None) -> tuple[PendingAction, Message]:
    """Persist the draft order, reply with the packing list, announce it to the merchant."""
    line_dicts = [l.model_dump() for l in lines]
    total = round(sum(float(l["line_total"]) for l in line_dicts), 2)
    name = (customer.name if customer else None) or profile_name or "ji"
    pay = khata.upi_link(settings.merchant_upi_vpa, settings.merchant_name, total, "WhatsApp order")
    text = packing_list_text(name, line_dicts, unmatched, total, pay)
    action = PendingAction(
        kind="wa_order", status="proposed", source=source, latency_ms=latency_ms,
        payload={
            "customer_id": customer.id if customer else None,
            "customer": customer.name if customer else (profile_name or phone),
            "phone": phone, "lines": line_dicts, "unmatched": unmatched, "total": total,
            "transcript": transcript, "input_type": input_type, "media_ref": media_ref,
            "pay_link": pay, "upi_vpa": settings.merchant_upi_vpa, "packing_list": text,
        })
    db.add(action)
    db.flush()
    reply = wa.notify(db, phone, text, customer_id=customer.id if customer else None)
    events.publish("store", "wa_order", {
        "action_id": action.id, "customer_id": customer.id if customer else None,
        "customer": action.payload["customer"], "phone": phone, "total": total,
        "lines": [{"name": l["name"], "qty": l["qty"], "unit": l.get("unit"), "line_total": l["line_total"]}
                  for l in line_dicts],
        "unmatched": unmatched, "transcript": transcript, "input_type": input_type,
        "pay_link": pay, "packing_list": text, "reply_message_id": reply.id,
    })
    return action, reply


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------


def _save_media(data: bytes, mime: str, filename: str) -> str:
    ext = ""
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1][:5]
    elif mime:
        ext = mimetypes.guess_extension(mime.split(";")[0].strip()) or ""
    name = f"{uuid.uuid4().hex[:16]}{ext}"
    (wa.wa_media_dir() / name).write_bytes(data)
    return f"/api/wa/media/{name}"


def _msg_event(m: Message) -> dict[str, Any]:
    return {"id": m.id, "to": m.to, "from": m.sender, "type": m.type, "body": m.body, "media_ref": m.media_ref,
            "customer_id": m.customer_id, "supplier_id": m.supplier_id, "direction": "in",
            "channel": m.channel, "created_at": m.created_at.isoformat() if m.created_at else None}


async def process(db: Session, inb: Inbound) -> dict[str, Any]:
    """Store and route one inbound message. Never raises for provider problems."""
    phone = wa.normalize_phone(inb.phone) or inb.phone
    if inb.wa_id:
        dup = db.query(Message).filter(Message.wa_id == inb.wa_id, Message.direction == "in").first()
        if dup is not None:
            return {"routed": "duplicate", "message_id": dup.id}
    customer = wa.find_customer_by_phone(db, phone)
    supplier = None if customer else wa.find_supplier_by_phone(db, phone)
    result: dict[str, Any] = {"routed": "stored", "customer_id": customer.id if customer else None,
                              "from": phone}

    # --- media -----------------------------------------------------------
    data = inb.media_bytes
    media_error: Optional[str] = None
    if inb.type in ("audio", "image") and data is None and inb.media_id:
        try:
            data, mime = await wa.download_media(inb.media_id)
            inb.mime = inb.mime or mime
        except Exception as exc:  # noqa: BLE001
            media_error = str(exc)[:200]
            log.warning("media download failed: %s", media_error)
    media_ref = _save_media(data, inb.mime, inb.filename) if data else None

    # --- understanding -----------------------------------------------------
    body = inb.body or ""
    understood: Optional[tuple[list, list, str, str, int]] = None  # lines, unmatched, transcript, source, ms
    if inb.type == "audio":
        stt = await sarvam.stt(data or b"", inb.filename or "voice.ogg", keyterms=catalog.keyterms(db),
                               demo_phrase=inb.demo_phrase, text=inb.body or None)
        transcript = stt.data.get("transcript", "")
        body = transcript
        outcome = quantity.parse_order_full(transcript, db)
        understood = (outcome.lines, outcome.unmatched, transcript, stt.source, stt.latency_ms)
        result["transcript"] = transcript
    elif inb.type == "image":
        vis = await vision.extract_json_from_image(data or b"", inb.mime or "image/jpeg", "parchi")
        listing = ", ".join(f"{r['qty']:g} {r.get('unit') or ''} {r['name']}".replace("  ", " ").strip()
                            for r in vis.data)
        outcome = quantity.parse_order_full(listing, db)
        body = (inb.body + "\n" if inb.body else "") + listing
        understood = (outcome.lines, outcome.unmatched, listing, vis.source, vis.latency_ms)
        result["transcript"] = listing
    if media_error:
        body = (body + " " if body else "") + "[media could not be downloaded]"

    # --- store + announce ------------------------------------------------
    message = Message(
        channel=inb.channel, to=None, sender=phone, direction="in", type=inb.type if inb.type != "other" else "text",
        body=body, media_ref=media_ref, wa_id=inb.wa_id, status="received",
        customer_id=customer.id if customer else None, supplier_id=supplier.id if supplier else None)
    db.add(message)
    db.flush()
    events.publish("wa", "wa_message", _msg_event(message))
    result["message_id"] = message.id
    result["input_type"] = inb.type

    # --- routing ---------------------------------------------------------
    if inb.type == "text":
        verdict = classify_reply(body)
        entry = khata.latest_open_entry(db, customer.id) if (customer and verdict) else None
        if entry is not None and not _replyable(entry):
            entry = None
        if verdict and entry is not None:
            return _handle_khata_reply(db, customer, entry, verdict, body, phone, result)
        toks = _tokens(body)
        if toks and len(toks) <= 2 and all(t in GREETINGS for t in toks):
            reply = wa.notify(db, phone, "Namaste! Order ke liye voice note ya parchi ki photo bhejein, "
                              "hum pack karke bhej denge.", customer_id=customer.id if customer else None)
            result.update(routed="greeting", reply_message_id=reply.id)
            return result
        if verdict is None and toks:
            outcome = quantity.parse_order_full(body, db)
            if outcome.lines:
                understood = (outcome.lines, outcome.unmatched, body, "rules", 0)

    if understood is not None:
        lines, unmatched, transcript, source, ms = understood
        if lines:
            action, reply = create_order(db, customer, phone, lines, unmatched, transcript, inb.type, source,
                                         ms, media_ref, inb.profile_name)
            result.update(routed="wa_order", action_id=action.id, total=action.payload["total"],
                          reply_message_id=reply.id, lines=action.payload["lines"], unmatched=unmatched)
            return result
        reply = wa.notify(db, phone, "Maaf kijiye, samajh nahi aaya. Dobara voice note ya saaf photo bhejein.",
                          customer_id=customer.id if customer else None)
        result.update(routed="unrecognized", reply_message_id=reply.id)
    return result


def _replyable(entry: Any) -> bool:
    """A sahi/galat reply only refers to an entry that is unanswered or was written in the last 3 days."""
    if not entry.confirmed_by_customer and not khata.is_disputed(entry):
        return True
    return bool(entry.at and (now_local() - entry.at).total_seconds() < 3 * 86400)


def _handle_khata_reply(db: Session, customer: Customer, entry: Any, verdict: str, body: str, phone: str,
                        result: dict[str, Any]) -> dict[str, Any]:
    bal = khata.balance(db, customer.id)
    if verdict == "dispute":
        khata.set_confirmation(db, entry, False, note=f"customer said: {body[:80]}")
        reply = wa.notify(db, phone, f"Theek hai {customer.name}, humne note kar liya. "
                          f"{settings.merchant_name} aapse jaldi baat karenge.", customer_id=customer.id)
        events.publish("store", "khata_disputed", {
            "entry_id": entry.id, "customer_id": customer.id, "customer": customer.name,
            "amount": entry.amount, "balance": bal, "text": body,
            "message": f"{customer.name} ne ₹{khata.fmt_inr(abs(entry.amount))} ki entry ko galat bataya."})
        result.update(routed="khata_dispute", entry_id=entry.id, reply_message_id=reply.id)
    else:
        khata.set_confirmation(db, entry, True)
        reply = wa.notify(db, phone, "Dhanyavaad! Entry confirm ho gayi.", customer_id=customer.id)
        events.publish("store", "khata_confirmed", {
            "entry_id": entry.id, "customer_id": customer.id, "customer": customer.name,
            "amount": entry.amount, "balance": bal})
        result.update(routed="khata_confirm", entry_id=entry.id, reply_message_id=reply.id)
    return result
