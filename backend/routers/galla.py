"""Galla closing (F7).

GET  /api/galla/expected   opening float + cash payments - refunds for a day
POST /api/galla/scan       photo -> vision 'cash' -> denominations, counted vs expected, difference
POST /api/galla/close      confirmed (possibly corrected) denominations -> CashClosing
GET  /api/galla/history    past closings

`close` publishes `galla_closed` on channel `store` and returns the spoken text via tts_cache.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import CashClosing
from services import events, galla as svc, tts_cache, vision
from services.clock import now_local, today_local
from services.types import ProviderError

router = APIRouter()


class CloseBody(BaseModel):
    denominations: Dict[str, float] = Field(
        ..., description="note counts keyed '2000','500','200','100','50','20','10' and 'coins' (rupee value)")
    day: Optional[date] = None
    photo_ref: Optional[str] = None
    speak: bool = True


def _closing_out(c: CashClosing) -> dict:
    return {"id": c.id, "day": c.day, "expected": c.expected, "counted": c.counted, "diff": c.diff,
            "difference": c.diff, "message_hi": svc.difference_message(c.expected, c.counted),
            "denominations": c.denominations or {}, "photo_ref": c.photo_ref, "created_at": c.created_at}


@router.get("/expected")
def expected(day: Optional[date] = None, db: Session = Depends(get_db)):
    bd = svc.breakdown(db, day)
    closing = (db.query(CashClosing).filter(CashClosing.day == (day or today_local()))
               .order_by(CashClosing.id.desc()).first())
    return {**bd, "already_closed": _closing_out(closing) if closing else None,
            "message_hi": f"Aaj galle mein {svc.inr(bd['expected'])} hone chahiye.",
            "source": "rules", "latency_ms": 0, "demo_mode": False}


@router.post("/scan")
async def scan_cash(image: UploadFile = File(...), db: Session = Depends(get_db)):
    """Photo of the cash -> per-denomination counts (editable) and the difference to expected."""
    data = await image.read()
    if not data:
        raise HTTPException(400, "Empty image upload")
    try:
        result = await vision.extract_json_from_image(data, image.content_type or "image/jpeg", "cash")
    except ProviderError as exc:
        raise HTTPException(502, f"Cash scan failed: {exc}") from exc
    denoms = svc.clean_denominations({k: v for k, v in result.data["denominations"].items()})
    out = svc.evaluate(db, denoms, result.data.get("denomination_confidence") or {},
                       float(result.data.get("confidence", 0.5)))
    return {**out, "source": result.source, "latency_ms": result.latency_ms,
            "demo_mode": result.source == "fixture"}


@router.post("/close")
async def close_day(body: CloseBody, db: Session = Depends(get_db)):
    """Persist the closing (one per day: closing again the same day replaces the count)."""
    t0 = time.perf_counter()
    try:
        denoms = svc.clean_denominations(body.denominations)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    day = body.day or today_local()
    ev = svc.evaluate(db, denoms, day=day)
    closing = db.query(CashClosing).filter(CashClosing.day == day).order_by(CashClosing.id.desc()).first()
    updated = closing is not None
    if closing is None:
        closing = CashClosing(day=day)
        db.add(closing)
    closing.expected, closing.counted, closing.diff = ev["expected"], ev["counted"], ev["difference"]
    closing.denominations = denoms
    closing.photo_ref = body.photo_ref or closing.photo_ref
    closing.created_at = now_local()
    db.commit()
    db.refresh(closing)

    events.publish("store", "galla_closed", {
        "id": closing.id, "day": day.isoformat(), "expected": closing.expected, "counted": closing.counted,
        "diff": closing.diff, "message_hi": ev["message_hi"]})
    speech = None
    if body.speak:
        sp = await tts_cache.get_speech(ev["message_hi"])
        speech = {"audio_base64": sp.audio_base64, "url": sp.url, "source": sp.source, "cached": sp.cached}
    return {"id": closing.id, "day": day.isoformat(), "expected": closing.expected, "counted": closing.counted,
            "difference": closing.diff, "message_hi": ev["message_hi"], "denominations": denoms,
            "table": ev["table"], "updated": updated, "speech": speech, "source": "rules",
            "latency_ms": int((time.perf_counter() - t0) * 1000), "demo_mode": False}


@router.get("/history")
def history(limit: int = 30, db: Session = Depends(get_db)):
    rows = (db.query(CashClosing).order_by(CashClosing.day.desc(), CashClosing.id.desc())
            .limit(max(1, min(limit, 365))).all())
    items = [_closing_out(c) for c in rows]
    return {"items": items, "summary": {
        "count": len(items), "total_diff": round(sum(c.diff for c in rows), 2),
        "short_days": sum(1 for c in rows if c.diff < -0.005), "excess_days": sum(1 for c in rows if c.diff > 0.005)},
        "source": "rules", "latency_ms": 0, "demo_mode": False}
