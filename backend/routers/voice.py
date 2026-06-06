import os
import re
import json
import base64
import httpx
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from fastapi import Depends
from database import get_db
from models import Product
from schemas import ParsedItem, VoiceParseResponse, TTSRequest, TTSResponse

load_dotenv()

router = APIRouter()

SARVAM_API_KEY  = os.getenv("SARVAM_API_KEY", "")
SARVAM_BASE_URL = os.getenv("SARVAM_API_BASE_URL", "https://api.sarvam.ai")
STT_MODEL       = os.getenv("SARVAM_STT_MODEL", "saaras:v2")
TTS_MODEL       = os.getenv("SARVAM_TTS_MODEL", "bulbul:v1")
PAYTM_BASE_URL  = os.getenv("PAYTM_API_BASE_URL", "https://api.inference.paytm.com")
PAYTM_LLM_MODEL = os.getenv("PAYTM_LLM_MODEL", "llama-3.3-70b-versatile")
PAYTM_AI_KEY    = os.getenv("PAYTM_AI_KEY", "")
DEMO_MODE = not bool(SARVAM_API_KEY) or os.getenv("DEMO_MODE", "false").lower() == "true"

# Product ID mapping for demo mode
DEMO_ITEMS = {
    "maggi": {"product_id": 1, "name": "Maggi", "name_hi": "मैगी", "unit": "packet", "price": 12.0, "gst_rate": 12.0},
    "chawal": {"product_id": 2, "name": "Rice 5kg", "name_hi": "चावल", "unit": "bag", "price": 350.0, "gst_rate": 0.0},
    "rice": {"product_id": 2, "name": "Rice 5kg", "name_hi": "चावल", "unit": "bag", "price": 350.0, "gst_rate": 0.0},
    "surf": {"product_id": 3, "name": "Surf Excel", "name_hi": "सर्फ एक्सेल", "unit": "packet", "price": 45.0, "gst_rate": 18.0},
    "surf excel": {"product_id": 3, "name": "Surf Excel", "name_hi": "सर्फ एक्सेल", "unit": "packet", "price": 45.0, "gst_rate": 18.0},
    "namak": {"product_id": 4, "name": "Tata Salt", "name_hi": "टाटा नमक", "unit": "packet", "price": 28.0, "gst_rate": 0.0},
    "tata": {"product_id": 4, "name": "Tata Salt", "name_hi": "टाटा नमक", "unit": "packet", "price": 28.0, "gst_rate": 0.0},
    "colgate": {"product_id": 5, "name": "Colgate", "name_hi": "कोलगेट", "unit": "packet", "price": 45.0, "gst_rate": 12.0},
    "atta": {"product_id": 6, "name": "Aashirvaad Atta 5kg", "name_hi": "आशीर्वाद आटा", "unit": "bag", "price": 320.0, "gst_rate": 0.0},
    "aashirvaad": {"product_id": 6, "name": "Aashirvaad Atta 5kg", "name_hi": "आशीर्वाद आटा", "unit": "bag", "price": 320.0, "gst_rate": 0.0},
    "shahad": {"product_id": 7, "name": "Patanjali Honey", "name_hi": "पतंजलि शहद", "unit": "bottle", "price": 180.0, "gst_rate": 12.0},
    "honey": {"product_id": 7, "name": "Patanjali Honey", "name_hi": "पतंजलि शहद", "unit": "bottle", "price": 180.0, "gst_rate": 12.0},
    "patanjali": {"product_id": 7, "name": "Patanjali Honey", "name_hi": "पतंजलि शहद", "unit": "bottle", "price": 180.0, "gst_rate": 12.0},
    "vim": {"product_id": 8, "name": "Vim Bar", "name_hi": "विम बार", "unit": "bar", "price": 15.0, "gst_rate": 18.0},
    "parle": {"product_id": 9, "name": "Parle-G", "name_hi": "पारले-जी", "unit": "packet", "price": 10.0, "gst_rate": 12.0},
    "parle g": {"product_id": 9, "name": "Parle-G", "name_hi": "पारले-जी", "unit": "packet", "price": 10.0, "gst_rate": 12.0},
    "parle-g": {"product_id": 9, "name": "Parle-G", "name_hi": "पारले-जी", "unit": "packet", "price": 10.0, "gst_rate": 12.0},
    "dettol": {"product_id": 10, "name": "Dettol Soap", "name_hi": "डेटॉल साबुन", "unit": "soap", "price": 35.0, "gst_rate": 18.0},
    "sabun": {"product_id": 10, "name": "Dettol Soap", "name_hi": "डेटॉल साबुन", "unit": "soap", "price": 35.0, "gst_rate": 18.0},
    "tel": {"product_id": 2, "name": "Rice 5kg", "name_hi": "चावल", "unit": "bag", "price": 350.0, "gst_rate": 0.0},  # fallback for "tel" (oil - not in catalog, map to rice for demo)
}

# Hinglish number words → digits
HINGLISH_NUMBERS = {
    "ek": 1, "do": 2, "teen": 3, "chaar": 4, "paanch": 5,
    "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

SKIP_WORDS = {"packet", "kilo", "litre", "liter", "bag", "bottle", "bar", "soap", "ka", "ke", "ki", "aur", "or"}


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text.lower().strip())


def parse_transcript_demo(transcript: str) -> list[ParsedItem]:
    """Parse Hinglish transcript into items using keyword matching."""
    text = normalize(transcript)
    tokens = text.split()
    items = []
    seen_products = set()

    i = 0
    while i < len(tokens):
        token = tokens[i]

        # Try to find a quantity (number or Hinglish word)
        qty = None
        if token.isdigit():
            qty = int(token)
            i += 1
        elif token in HINGLISH_NUMBERS:
            qty = HINGLISH_NUMBERS[token]
            i += 1

        # Try to match product (single or two-word)
        if i < len(tokens):
            two_word = f"{tokens[i]} {tokens[i+1]}" if i + 1 < len(tokens) else None
            product = None

            if two_word and two_word in DEMO_ITEMS:
                product = DEMO_ITEMS[two_word]
                i += 2
            elif tokens[i] in DEMO_ITEMS:
                product = DEMO_ITEMS[tokens[i]]
                i += 1
            elif tokens[i] in SKIP_WORDS:
                i += 1
                continue
            else:
                i += 1
                continue

            if product and product["product_id"] not in seen_products:
                seen_products.add(product["product_id"])
                items.append(ParsedItem(
                    product_id=product["product_id"],
                    name=product["name"],
                    name_hi=product["name_hi"],
                    quantity=qty if qty else 1,
                    unit=product["unit"],
                    price=product["price"],
                    gst_rate=product["gst_rate"],
                ))
        else:
            i += 1

    return items


async def sarvam_stt(audio_bytes: bytes, filename: str) -> str:
    """Call Sarvam Saaras STT API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{SARVAM_BASE_URL}/speech-to-text",
            headers={"api-subscription-key": SARVAM_API_KEY},
            files={"file": (filename, audio_bytes, "audio/webm")},
            data={"language_code": "hi-IN", "model": STT_MODEL},
        )
        response.raise_for_status()
        data = response.json()
        # saaras:v3 may return translated_text alongside transcript
        use_translated = os.getenv("SARVAM_PARSE_USE_TRANSLATED_TEXT", "false").lower() == "true"
        if use_translated and data.get("translated_text"):
            return data["translated_text"]
        return data.get("transcript", "")


async def paytm_llm_parse(transcript: str, db: Session) -> list[ParsedItem]:
    """Use Paytm AI gateway (Llama 3.3 70B) to parse transcript into structured items."""
    products = db.query(Product).all()
    product_list = "\n".join([f"- {p.name} ({p.name_hi}): ₹{p.price}/{p.unit}" for p in products])

    prompt = f"""You are an inventory assistant for an Indian kirana store.
Extract items and quantities from this Hindi/Hinglish text.

Available products:
{product_list}

Text: "{transcript}"

Return ONLY a valid JSON array. Map items to the closest available product.
Format: [{{"product_name": "Maggi", "quantity": 2}}]
If no items found, return []"""

    auth_key = PAYTM_AI_KEY or SARVAM_API_KEY
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{PAYTM_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {auth_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": PAYTM_LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

    # Parse JSON from LLM response
    json_match = re.search(r'\[.*\]', content, re.DOTALL)
    if not json_match:
        return parse_transcript_demo(transcript)

    parsed = json.loads(json_match.group())
    items = []
    for entry in parsed:
        product = db.query(Product).filter(
            Product.name.ilike(f"%{entry['product_name']}%")
        ).first()
        if product:
            items.append(ParsedItem(
                product_id=product.id,
                name=product.name,
                name_hi=product.name_hi,
                quantity=entry.get("quantity", 1),
                unit=product.unit,
                price=product.price,
                gst_rate=product.gst_rate,
            ))
    return items


# Keep old name as alias so nothing breaks if referenced elsewhere
sarvam_llm_parse = paytm_llm_parse


@router.post("/parse", response_model=VoiceParseResponse)
async def parse_voice(
    audio: Optional[UploadFile] = File(None),
    transcript: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Parse voice audio OR text transcript into structured inventory items.
    Tries Sarvam APIs if key is set, falls back to demo mode.
    """
    final_transcript = ""
    used_demo = True

    try:
        if transcript:
            final_transcript = transcript
        elif audio and SARVAM_API_KEY:
            audio_bytes = await audio.read()
            final_transcript = await sarvam_stt(audio_bytes, audio.filename or "audio.webm")
            used_demo = False
        elif audio:
            final_transcript = "do maggi ek surf excel chaar colgate"  # demo fallback
    except Exception:
        final_transcript = final_transcript or "do maggi ek surf excel chaar colgate"
        used_demo = True

    if not final_transcript:
        final_transcript = "do maggi ek surf excel chaar colgate"

    # Parse transcript
    try:
        if not used_demo and (PAYTM_AI_KEY or SARVAM_API_KEY):
            items = await paytm_llm_parse(final_transcript, db)
        else:
            items = parse_transcript_demo(final_transcript)
    except Exception:
        items = parse_transcript_demo(final_transcript)
        used_demo = True

    return VoiceParseResponse(
        transcript=final_transcript,
        items=items,
        demo_mode=used_demo,
    )


@router.post("/tts", response_model=TTSResponse)
async def text_to_speech(req: TTSRequest):
    """Convert Hindi text to speech using Bulbul V3 TTS."""
    if not SARVAM_API_KEY:
        return TTSResponse(audio_base64="", text=req.text)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{SARVAM_BASE_URL}/text-to-speech",
                headers={
                    "api-subscription-key": SARVAM_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "inputs": [req.text],
                    "target_language_code": "hi-IN",
                    "speaker": "meera",
                    "model": TTS_MODEL,
                },
            )
            response.raise_for_status()
            audios = response.json().get("audios", [])
            audio_b64 = audios[0] if audios else ""
            return TTSResponse(audio_base64=audio_b64, text=req.text)
    except Exception:
        return TTSResponse(audio_base64="", text=req.text)
