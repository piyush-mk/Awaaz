"""
Photo Inventory — shelf photo → Grok-4.3 vision → product detection → inventory update.
Falls back to demo mode if API unavailable.
"""
import os
import base64
import json
import re
import httpx
from fastapi import APIRouter, UploadFile, File
from schemas import ParsedItem, VoiceParseResponse
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

XAI_KEY      = os.getenv("XAI_KEY", "")
XAI_URL      = "https://api.x.ai/v1/chat/completions"
VISION_MODEL = "grok-4.3"

PRODUCT_MAP = {
    1:  {"name": "Maggi",               "name_hi": "मैगी",           "unit": "packet", "price": 12.0,  "gst_rate": 12.0},
    2:  {"name": "Rice 5kg",            "name_hi": "चावल",           "unit": "bag",    "price": 350.0, "gst_rate": 0.0},
    3:  {"name": "Surf Excel",          "name_hi": "सर्फ एक्सेल",   "unit": "packet", "price": 45.0,  "gst_rate": 18.0},
    4:  {"name": "Tata Salt",           "name_hi": "टाटा नमक",       "unit": "packet", "price": 28.0,  "gst_rate": 0.0},
    5:  {"name": "Colgate",             "name_hi": "कोलगेट",         "unit": "packet", "price": 45.0,  "gst_rate": 12.0},
    6:  {"name": "Aashirvaad Atta 5kg", "name_hi": "आशीर्वाद आटा",  "unit": "bag",    "price": 320.0, "gst_rate": 0.0},
    7:  {"name": "Patanjali Honey",     "name_hi": "पतंजलि शहद",     "unit": "bottle", "price": 180.0, "gst_rate": 12.0},
    8:  {"name": "Vim Bar",             "name_hi": "विम बार",         "unit": "bar",    "price": 15.0,  "gst_rate": 18.0},
    9:  {"name": "Parle-G",             "name_hi": "पारले-जी",        "unit": "packet", "price": 10.0,  "gst_rate": 12.0},
    10: {"name": "Dettol Soap",         "name_hi": "डेटॉल साबुन",    "unit": "soap",   "price": 35.0,  "gst_rate": 18.0},
}

VISION_PROMPT = """You are analyzing a photo of a kirana (Indian grocery) store shelf.
Identify ALL visible products from this list and estimate how many units are visible:

1=Maggi noodles, 2=Rice 5kg bag, 3=Surf Excel detergent, 4=Tata Salt,
5=Colgate toothpaste, 6=Aashirvaad Atta flour bag, 7=Patanjali Honey,
8=Vim Bar dishwash, 9=Parle-G biscuits, 10=Dettol Soap

Return ONLY a JSON array, nothing else. Example:
[{"product_id": 1, "quantity": 12}, {"product_id": 9, "quantity": 8}]

Only include products clearly visible. Estimate conservatively."""

DEMO_ITEMS = [
    {"product_id": 1, "quantity": 8},
    {"product_id": 9, "quantity": 12},
    {"product_id": 5, "quantity": 6},
    {"product_id": 3, "quantity": 4},
]


def build_items(raw: list[dict]) -> list[ParsedItem]:
    return [
        ParsedItem(product_id=pid, quantity=max(1, int(e.get("quantity", 1))), **PRODUCT_MAP[pid])
        for e in raw
        if (pid := int(e.get("product_id", 0))) in PRODUCT_MAP
    ]


def extract_json(text: str) -> list[dict] | None:
    try:
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        return json.loads(match.group()) if match else None
    except Exception:
        return None


async def vision_parse(image_b64: str, mime_type: str) -> list[ParsedItem] | None:
    if not XAI_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                XAI_URL,
                headers={
                    "Authorization": f"Bearer {XAI_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": VISION_MODEL,
                    "max_tokens": 512,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_b64}"
                                },
                            },
                        ],
                    }],
                },
            )
            if r.status_code != 200:
                return None
            content = r.json()["choices"][0]["message"]["content"]
            raw = extract_json(content)
            return build_items(raw) if raw else None
    except Exception:
        return None


@router.post("/parse", response_model=VoiceParseResponse)
async def parse_photo(image: UploadFile = File(...)):
    """
    POST a shelf photo → Grok-4.3 vision detects products + quantities →
    same ParsedItem[] as voice parse. Feed into POST /api/inventory/restock.
    """
    image_bytes = await image.read()
    mime_type   = image.content_type or "image/jpeg"
    image_b64   = base64.b64encode(image_bytes).decode()

    items = await vision_parse(image_b64, mime_type)
    if items:
        return VoiceParseResponse(
            transcript=f"[Photo — {VISION_MODEL}]",
            items=items,
            demo_mode=False,
        )

    return VoiceParseResponse(
        transcript="[Photo — Demo mode]",
        items=build_items(DEMO_ITEMS),
        demo_mode=True,
    )
