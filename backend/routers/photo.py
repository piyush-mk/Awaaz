"""Legacy photo inventory API: shelf photo -> vision -> ParsedItem[] (shape unchanged).
Chain is Sarvam gemma4 -> xAI grok-4.3 -> fixture (see services/vision.py)."""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from schemas import ParsedItem, VoiceParseResponse
from services import catalog, vision

router = APIRouter()


@router.post("/parse", response_model=VoiceParseResponse)
async def parse_photo(image: UploadFile = File(...), db: Session = Depends(get_db)):
    """POST a shelf photo; feed the result into POST /api/inventory/restock."""
    data = await image.read()
    result = await vision.extract_json_from_image(data, image.content_type or "image/jpeg", "shelf")
    index = catalog.load_index(db)
    merged: dict[int, ParsedItem] = {}
    extras: list[ParsedItem] = []
    for row in result.data:
        product, _ = index.find_in_phrase(row["name"])
        qty = float(row["quantity"])
        if product is None:
            extras.append(ParsedItem(product_id=0, name=row["name"], name_hi="", quantity=qty,
                                     unit="unit", price=0.0, gst_rate=0.0))
        elif product.id in merged:
            merged[product.id].quantity += qty
        else:
            merged[product.id] = ParsedItem(
                product_id=product.id, name=product.name, name_hi=product.name_hi or "", quantity=qty,
                unit=product.unit or "", price=product.price, gst_rate=product.gst_rate or 0.0)
    names = ", ".join(r["name"] for r in result.data) or "none"
    return VoiceParseResponse(
        transcript=f"Detected: {names}" if result.source != "fixture" else "[Photo - Demo mode]",
        items=list(merged.values()) + extras, demo_mode=result.source == "fixture",
        source=result.source, latency_ms=result.latency_ms)
