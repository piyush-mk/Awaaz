"""Voice agent (Agent A: Counter). The logic lives in services/counter.py.

POST /api/agent/utterance   multipart: audio file OR text (alias: transcript), context
                            (counter|stock|khata|ask), session_id, optional customer_id, speak.
                            Header X-Demo-Phrase picks a fixture transcript when STT is unavailable.
GET  /api/actions           list PendingActions (?status=&session_id=&kind=&limit=)
GET  /api/actions/{id}      one action
POST /api/actions/{id}/confirm | /cancel   commit or drop a proposed action
"""
import time
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from models import PendingAction
from services import catalog, counter, sarvam

router = APIRouter()
actions_router = APIRouter()

CONTEXTS = ("counter", "stock", "khata", "ask")


@router.post("/utterance")
async def utterance(
    audio: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    transcript: Optional[str] = Form(None),
    context: str = Form("counter"),
    session_id: str = Form("default"),
    customer_id: Optional[int] = Form(None),
    speak: bool = Form(True),
    x_demo_phrase: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """One spoken (or typed) utterance -> cart edits applied now, money/stock commits proposed.

    Response: {transcript, cart, actions[], applied[], spoken_text, audio_url, speech, source,
    stt_source, latency_ms, timings, demo_mode, session_id, ...}. `actions` are the PendingActions this
    utterance created or resolved; confirm them with POST /api/actions/{id}/confirm.

    The reply never waits for TTS. `speech` = {text, pace, pending, key, audio_url, ack}: when the clip
    is cached `pending` is false and `audio_url` is set (`audio_url`/`spoken_text` at the top level
    mirror it); otherwise `pending` is true and `speech_ready {session_id, key, audio_url|null, text,
    source}` follows on the `store` event channel (audio_url null: speak `text` with browser speech).
    `ack` is a phrase id from GET /api/voice/phrases the client may play at once.
    `timings` = {stt_ms, parse_ms, llm_ms, total_ms}, null where a stage was skipped. Utterances the
    rules parser fully explains skip the LLM (source "rules", FAST_PATH=off disables)."""
    started = time.perf_counter()
    if context not in CONTEXTS:
        raise HTTPException(422, f"context must be one of {', '.join(CONTEXTS)}")
    typed = (text or transcript or "").strip()
    if not typed and audio is None:
        raise HTTPException(422, "Provide audio or text")
    stt_ms: Optional[int] = None
    if typed:
        stt = await sarvam.stt(b"", text=typed)
    else:
        t_stt = time.perf_counter()
        data = await audio.read()  # type: ignore[union-attr]
        stt = await sarvam.stt(data, audio.filename or "audio.webm",  # type: ignore[union-attr]
                               keyterms=catalog.keyterms(db), demo_phrase=x_demo_phrase)
        stt_ms = int((time.perf_counter() - t_stt) * 1000)
    return await counter.run_utterance(
        db, session_id=session_id.strip() or "default", transcript=stt.data["transcript"],
        context=context, customer_id=customer_id, stt_source=stt.source, started=started, speak=speak,
        stt_ms=stt_ms)


@actions_router.get("")
def list_actions(status: Optional[str] = None, session_id: Optional[str] = None,
                 kind: Optional[str] = None, include_cart_edits: bool = False,
                 limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    q = db.query(PendingAction)
    if status:
        q = q.filter(PendingAction.status == status)
    if session_id:
        q = q.filter(PendingAction.session_id == session_id)
    if kind:
        q = q.filter(PendingAction.kind == kind)
    elif not include_cart_edits:
        q = q.filter(PendingAction.kind != "cart_edit")
    return [counter.action_json(a) for a in q.order_by(PendingAction.id.desc()).limit(limit).all()]


@actions_router.get("/{action_id}")
def get_action(action_id: int, db: Session = Depends(get_db)):
    action = db.get(PendingAction, action_id)
    if action is None:
        raise HTTPException(404, f"Action {action_id} nahi mila")
    return counter.action_json(action)


@actions_router.post("/{action_id}/confirm")
async def confirm_action(action_id: int, body: Optional[dict] = Body(None),
                         db: Session = Depends(get_db)):
    """Commit a proposed action. Optional JSON body overrides, e.g. {"customer_id": 2} for a split
    payment whose khata part had no customer. Idempotent: confirming twice returns the first result
    with already_resolved=true."""
    return await counter.resolve_action(db, action_id, "confirm", body or {})


@actions_router.post("/{action_id}/cancel")
async def cancel_action(action_id: int, body: Optional[dict] = Body(None),
                        db: Session = Depends(get_db)):
    return await counter.resolve_action(db, action_id, "cancel", body or {}, speak=False)
