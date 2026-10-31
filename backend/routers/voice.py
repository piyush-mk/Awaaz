"""Legacy voice API: /api/voice/parse and /api/voice/tts (shapes unchanged).

Parsing now uses the shared rules parser (`services/quantity.py`) after one STT
call (`services/sarvam.py`); with no key or DEMO_MODE=on the transcript comes from
fixtures (header `X-Demo-Phrase` picks one). The agent endpoint with LLM tool
calling is a separate Phase 1 router (`routers/agent.py`).
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from schemas import ParsedItem, TTSRequest, TTSResponse, VoiceParseResponse
from services import catalog, phrases, quantity, sarvam, tts_cache

router = APIRouter()


@router.post("/parse", response_model=VoiceParseResponse)
async def parse_voice(
    audio: Optional[UploadFile] = File(None),
    transcript: Optional[str] = Form(None),
    x_demo_phrase: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Parse spoken audio OR a text transcript into catalog items."""
    if not transcript and audio is None:
        raise HTTPException(status_code=422, detail="Provide transcript text or audio to parse")
    if transcript:
        stt = await sarvam.stt(b"", text=transcript.strip())
    else:
        data = await audio.read()  # type: ignore[union-attr]
        stt = await sarvam.stt(data, audio.filename or "audio.webm",  # type: ignore[union-attr]
                               keyterms=catalog.keyterms(db), demo_phrase=x_demo_phrase)
    text = stt.data["transcript"]
    outcome = quantity.parse_order_full(text, db)
    items = [ParsedItem(product_id=ln.product_id, name=ln.name, name_hi=ln.name_hi, quantity=ln.qty,
                        unit=ln.unit, price=ln.unit_price, gst_rate=ln.gst_rate) for ln in outcome.lines]
    items += [ParsedItem(product_id=None, name=m["name"], name_hi="", quantity=m["qty"], unit="piece",
                         price=0.0, gst_rate=0.0) for m in outcome.unmatched]
    return VoiceParseResponse(transcript=text, items=items, demo_mode=stt.source == "fixture",
                              source=stt.source, latency_ms=stt.latency_ms)


@router.post("/tts", response_model=TTSResponse)
async def text_to_speech(req: TTSRequest):
    """Text to speech via the disk cache. Empty `audio_base64` means: use browser TTS."""
    speech = await tts_cache.get_speech(req.text, req.language, req.speaker)
    return TTSResponse(audio_base64=speech.audio_base64, text=req.text, url=speech.url,
                       source=speech.source)


@router.get("/tts/{key}.mp3")
def cached_tts(key: str):
    """Serve a cached TTS clip by the key returned in `url`."""
    if not re.fullmatch(r"[0-9a-f]{32}", key):
        raise HTTPException(status_code=404, detail="not found")
    audio = tts_cache.read_cached(key)
    if audio is None:
        raise HTTPException(status_code=404, detail="not found")
    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/phrases")
def phrase_bank():
    """The instant-acknowledgement phrase bank: {ready, phrases: {id: {text, audio_url|null, kind}}}.
    `audio_url` is null until the clip is cached (and always null without TTS: speak `text` with
    browser speech). `ready` is true when every clip is available. Asking while some are missing
    nudges the background warm-up (a no-op under DEMO_MODE=on or without a key)."""
    out = phrases.view()
    if not out["ready"]:
        phrases.start_warmup()
    return out
