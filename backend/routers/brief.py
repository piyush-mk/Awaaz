"""Morning brief, reorder and Ask-your-munim (Phase 1, Agent D). Mounted at /api.

GET  /api/brief/today              facts + Hinglish text + audio (sarvam-105b, template fallback)
POST /api/brief/speak              audio for the brief (or for any `text`), replayable
POST /api/brief/play               publishes `brief_ready` on the `store` channel (Soundbox plays it)
GET  /api/reorder                  purchase-order drafts and sent POs
POST /api/reorder/draft            per-supplier PO suggestions (cover x festival multiplier)
POST /api/reorder/{id}/send        WhatsApp the PO to the supplier
POST /api/munim/ask                Ask your munim (text or audio); aliases /api/ask, /api/brief/ask
GET  /api/munim/examples           example questions for the UI
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from services import brief as brief_svc
from services import catalog, events, munim, reorder, sarvam
from services.clock import now_local

router = APIRouter()


# ---------------------------------------------------------------------------
# morning brief
# ---------------------------------------------------------------------------


async def _brief_payload(db: Session, llm: bool, refresh: bool, audio: bool) -> dict[str, Any]:
    out = await brief_svc.generate(db, use_llm=llm, refresh=refresh)
    out["generated_at"] = now_local().isoformat(timespec="seconds")
    if audio:
        out.update(await brief_svc.audio_for(out["text"]))
    else:
        out.update({"audio_base64": "", "audio_url": None, "tts_source": None, "cached": False})
    return out


@router.get("/brief/today")
async def brief_today(llm: bool = True, refresh: bool = False, audio: bool = True,
                      db: Session = Depends(get_db)):
    """Today's brief: `facts` (structured), `text` (Hinglish, 3-4 sentences), `spoken_text`,
    `audio_base64` / `audio_url` (empty = use the browser voice) and `source` (sarvam|paytm|rules)."""
    return await _brief_payload(db, llm, refresh, audio)


class SpeakIn(BaseModel):
    text: Optional[str] = Field(None, description="speak this instead of today's brief")


@router.post("/brief/speak")
async def brief_speak(body: Optional[SpeakIn] = None, db: Session = Depends(get_db)):
    """Replay: audio for today's brief (cached TTS), or for `text` if given."""
    if body and body.text and body.text.strip():
        text = body.text.strip()
        return {"text": text, **(await brief_svc.audio_for(text))}
    out = await brief_svc.generate(db)
    return {"text": out["text"], "source": out["source"], **(await brief_svc.audio_for(out["text"]))}


@router.post("/brief/play")
async def brief_play(db: Session = Depends(get_db)):
    """Tell the Soundbox emulator to play the brief: publishes `brief_ready` on `store`."""
    out = await _brief_payload(db, True, False, True)
    event = events.publish("store", "brief_ready", {
        "date": out["date"], "text": out["text"], "spoken_text": out["spoken_text"],
        "audio_url": out["audio_url"], "tts_source": out["tts_source"], "source": out["source"],
        "yesterday_total": out["facts"]["yesterday"]["total"]})
    return {"published": True, "event_id": event["id"], **out}


# ---------------------------------------------------------------------------
# reorder
# ---------------------------------------------------------------------------


class ReorderDraftIn(BaseModel):
    supplier_id: Optional[int] = Field(None, description="only draft the PO for this supplier")


class ReorderEdit(BaseModel):
    product_id: int
    qty: float = Field(..., ge=0, description="new quantity; 0 removes the line")


class ReorderSendIn(BaseModel):
    edits: list[ReorderEdit] = Field(default_factory=list)
    note: Optional[str] = None


def _raise(exc: reorder.ReorderError):
    raise HTTPException(status_code=exc.status, detail=exc.message)


@router.post("/reorder/draft")
def reorder_draft(body: Optional[ReorderDraftIn] = None, db: Session = Depends(get_db)):
    """Suggest purchase orders per supplier. Each is stored as PendingAction(kind='purchase_order')."""
    drafts = reorder.draft_orders(db, supplier_id=body.supplier_id if body else None)
    orders = reorder.save_drafts(db, drafts)
    db.commit()
    return {"orders": orders, "count": len(orders), "unassigned": drafts["unassigned"],
            "generated_at": now_local().isoformat(timespec="seconds")}


@router.get("/reorder")
def reorder_list(status: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    """Drafts (status=proposed), sent (status=confirmed) and cancelled purchase orders."""
    orders = reorder.list_orders(db, status, limit)
    return {"orders": orders, "count": len(orders)}


@router.post("/reorder/{order_id}/send")
def reorder_send(order_id: int, body: Optional[ReorderSendIn] = None, db: Session = Depends(get_db)):
    """Send the PO to the supplier on WhatsApp. Optional `edits` change quantities first."""
    try:
        return reorder.send_order(db, order_id, [e.model_dump() for e in body.edits] if body else None,
                                  body.note if body else None)
    except reorder.ReorderError as exc:
        db.rollback()
        _raise(exc)


# ---------------------------------------------------------------------------
# Ask your munim
# ---------------------------------------------------------------------------


@router.get("/ask/examples")
@router.get("/munim/examples")
def munim_examples():
    return {"examples": munim.EXAMPLE_QUESTIONS}


@router.post("/munim/ask")
@router.post("/ask")
@router.post("/brief/ask")
async def munim_ask(request: Request, speak: bool = True, llm: bool = True,
                    x_demo_phrase: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Ask a question by text or voice.

    JSON: {"text": "is hafte sabse zyada kya bika"}  or  multipart: `audio` file / `text` field.
    Returns the spoken `answer`, the data `table`, the tool results and audio (empty = browser voice)."""
    ctype = request.headers.get("content-type", "")
    text: Optional[str] = None
    audio: Optional[tuple[bytes, str]] = None
    if "application/json" in ctype:
        body = await request.json()
        text = (body.get("text") or body.get("question") or "") if isinstance(body, dict) else ""
        speak = bool(body.get("speak", speak)) if isinstance(body, dict) else speak
    elif "multipart/form-data" in ctype or "application/x-www-form-urlencoded" in ctype:
        form = await request.form()
        text = str(form.get("text") or form.get("question") or "")
        upload = form.get("audio")
        if upload is not None and hasattr(upload, "read"):
            audio = (await upload.read(), getattr(upload, "filename", None) or "audio.webm")
    if not (text and text.strip()) and audio is None:
        raise HTTPException(status_code=422, detail="Send `text` or an `audio` file")

    transcript, stt_source = (text or "").strip(), "rules"
    if not transcript and audio is not None:
        phrase = x_demo_phrase or munim.EXAMPLE_QUESTIONS[0]  # fixture STT: a sensible demo question
        stt = await sarvam.stt(audio[0], audio[1], keyterms=catalog.keyterms(db), demo_phrase=phrase)
        transcript, stt_source = stt.data["transcript"], stt.source
    result = await munim.ask(db, transcript, use_llm=llm)
    result.update({"transcript": transcript, "stt_source": stt_source})
    if speak:
        result.update(await brief_svc.audio_for(result["answer"]))
    else:
        result.update({"audio_base64": "", "audio_url": None, "tts_source": None})
    return result
