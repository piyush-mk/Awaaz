import os
import re
import json
from pathlib import Path
from collections import defaultdict
import httpx
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional, cast
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from fastapi import Depends
from database import get_db
from models import Product
from schemas import ParsedItem, VoiceParseResponse, TTSRequest, TTSResponse

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)

router = APIRouter()

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
SARVAM_API_BASE_URL = os.getenv("SARVAM_API_BASE_URL", "https://api.sarvam.ai").rstrip("/")
SARVAM_API_REGION = os.getenv("SARVAM_API_REGION", "in")
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
SARVAM_PARSE_USE_TRANSLATED_TEXT = os.getenv("SARVAM_PARSE_USE_TRANSLATED_TEXT", "true").lower() == "true"
PAYTM_API_KEY = os.getenv("PAYTM_API_KEY", "") or os.getenv("PAYTM_AI_KEY", "")
PAYTM_API_BASE_URL = os.getenv("PAYTM_API_BASE_URL", "https://api.inference.paytm.com").rstrip("/")
PAYTM_LLM_MODEL = os.getenv("PAYTM_LLM_MODEL", "llama-3.3-70b-versatile")

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

HINDI_NUMBERS = {
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
}

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

SKIP_WORDS = {"packet", "kilo", "litre", "liter", "bag", "bottle", "bar", "soap", "ka", "ke", "ki", "aur", "or"}
HINDI_SKIP_WORDS = {"पैकेट", "किलो", "लीटर", "बैग", "बोतल", "बार", "का", "के", "की", "और"}


def normalize(text: str) -> str:
    normalized = text.translate(DEVANAGARI_DIGITS).lower().strip()
    normalized = re.sub(r"[^\w\s\u0900-\u097F-]", " ", normalized)
    return re.sub(r'\s+', ' ', normalized)


def _extract_qty(tokens: list[str], start_idx: int, end_idx: int) -> int:
    # Check nearby tokens around a matched product phrase.
    nearby_indices = [start_idx - 2, start_idx - 1, end_idx, end_idx + 1]
    for idx in nearby_indices:
        if idx < 0 or idx >= len(tokens):
            continue
        token = tokens[idx]
        if token.isdigit():
            return max(1, int(token))
        if token in HINGLISH_NUMBERS:
            return HINGLISH_NUMBERS[token]
        if token in HINDI_NUMBERS:
            return HINDI_NUMBERS[token]
    return 1


def _canonical_aliases_for_product(product: Product) -> set[str]:
    name = normalize(str(cast(str, product.name)))
    name_hi = normalize(str(cast(str, product.name_hi)))
    aliases = {name, name_hi}

    # Add useful sub-phrases for better matching from STT output.
    name_parts = name.split()
    if len(name_parts) > 1:
        aliases.add(" ".join(name_parts[:2]))
        aliases.add(name_parts[0])

    name_hi_parts = name_hi.split()
    if len(name_hi_parts) > 1:
        aliases.add(" ".join(name_hi_parts[:2]))
        aliases.add(name_hi_parts[0])

    # Preserve existing known demo aliases too.
    for alias, info in DEMO_ITEMS.items():
        if int(info["product_id"]) == int(cast(int, product.id)):
            aliases.add(normalize(alias))

    return {a for a in aliases if a}


def parse_transcript_with_db_products(transcript: str, products: list[Product]) -> list[ParsedItem]:
    text = normalize(transcript)
    if not text:
        return []

    tokens = text.split()
    alias_to_product: dict[str, Product] = {}
    max_alias_len = 1
    for product in products:
        for alias in _canonical_aliases_for_product(product):
            alias_to_product[alias] = product
            max_alias_len = max(max_alias_len, len(alias.split()))

    quantities_by_product: dict[int, int] = defaultdict(int)
    matched_products: dict[int, Product] = {}

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in SKIP_WORDS or token in HINDI_SKIP_WORDS:
            i += 1
            continue

        matched_alias = None
        matched_product = None

        for n in range(max_alias_len, 0, -1):
            if i + n > len(tokens):
                continue
            phrase = " ".join(tokens[i:i + n])
            product = alias_to_product.get(phrase)
            if product:
                matched_alias = phrase
                matched_product = product
                break

        if not matched_product or not matched_alias:
            i += 1
            continue

        qty = _extract_qty(tokens, i, i + len(matched_alias.split()))
        product_id = int(cast(int, matched_product.id))
        quantities_by_product[product_id] += qty
        matched_products[product_id] = matched_product
        i += len(matched_alias.split())

    items: list[ParsedItem] = []
    for product_id, qty in quantities_by_product.items():
        product = matched_products[product_id]
        items.append(ParsedItem(
            product_id=product_id,
            name=str(cast(str, product.name)),
            name_hi=str(cast(str, product.name_hi)),
            quantity=qty,
            unit=str(cast(str, product.unit)),
            price=float(cast(float, product.price)),
            gst_rate=float(cast(float, product.gst_rate)),
        ))

    return items


def _find_product_by_text(db: Session, product_name: str) -> Optional[Product]:
    cleaned = normalize(product_name)
    if not cleaned:
        return None

    product = db.query(Product).filter(Product.name.ilike(f"%{cleaned}%")).first()
    if product:
        return product

    product = db.query(Product).filter(Product.name_hi.ilike(f"%{cleaned}%")).first()
    if product:
        return product

    products = db.query(Product).all()
    for candidate in products:
        aliases = _canonical_aliases_for_product(candidate)
        if cleaned in aliases:
            return candidate
    return None


def _sarvam_headers() -> dict[str, str]:
    headers = {"api-subscription-key": SARVAM_API_KEY}
    if SARVAM_API_REGION:
        headers["x-sarvam-region"] = SARVAM_API_REGION
    return headers


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


async def sarvam_stt(audio_bytes: bytes, filename: str, mode: str = "transcribe") -> str:
    """Call Sarvam Saaras STT API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{SARVAM_API_BASE_URL}/speech-to-text",
            headers=_sarvam_headers(),
            files={"file": (filename, audio_bytes, "audio/webm")},
            data={"language_code": "hi-IN", "model": SARVAM_STT_MODEL, "mode": mode},
        )
        response.raise_for_status()
        return response.json().get("transcript", "")


async def paytm_llm_parse(transcript: str, db: Session, translated_transcript: Optional[str] = None) -> list[ParsedItem]:
    """Parse transcript into strict inventory JSON using Paytm Inference."""
    if not PAYTM_API_KEY:
        raise HTTPException(status_code=503, detail="PAYTM_API_KEY is not configured")

    products = db.query(Product).all()
    if not products:
        raise HTTPException(status_code=500, detail="No products found in database. Run seed.py first.")

    product_catalog = [
        {
            "product_id": int(cast(int, p.id)),
            "name": str(cast(str, p.name)),
            "name_hi": str(cast(str, p.name_hi)),
            "unit": str(cast(str, p.unit)),
            "price": float(cast(float, p.price)),
            "gst_rate": float(cast(float, p.gst_rate)),
        }
        for p in products
    ]
    product_by_id = {item["product_id"]: item for item in product_catalog}

    transcript_block = f"Original transcript:\n{transcript}"
    if translated_transcript:
        transcript_block += f"\n\nEnglish translation:\n{translated_transcript}"

    system_prompt = (
        "You are a strict inventory parser. "
        "Convert transcript text into structured inventory items. "
        "Use product IDs from the provided catalog when the product exists there. "
        "If the transcript mentions a real product that is not in the catalog, still return it as a custom item with product_id as null. "
        "Do NOT invent products or quantities not explicitly mentioned in the transcript. "
        "If a product's price is mentioned in the transcript, return that price (number). "
        "If price is not mentioned, the model may provide an estimated price. "
        "If nothing matches, return an empty items array. "
        "Never add fields outside the tool schema."
    )

    user_prompt = (
        f"Catalog JSON:\n{json.dumps(product_catalog, ensure_ascii=False)}\n\n"
        f"{transcript_block}\n\n"
        "Extract the ordered products and quantities from the transcript. For each item, return the catalog product_id and quantity. "
        "If the item is not in the catalog, return product_id as null and still include name, name_hi, unit, price and gst_rate. "
        "If available, also return a numeric price for the item (customer-stated price or reasonable estimate). "
        "Only return items that are explicitly present in the transcript."
    )

    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            f"{PAYTM_API_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {PAYTM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": PAYTM_LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "fill_inventory_items",
                            "description": "Return parsed product IDs, quantities and optional prices",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "items": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "product_id": {"type": ["integer", "null"]},
                                                "name": {"type": "string"},
                                                "name_hi": {"type": "string"},
                                                "quantity": {"type": "integer", "minimum": 1},
                                                "unit": {"type": "string"},
                                                "price": {"type": "number"}
                                                ,"gst_rate": {"type": "number"}
                                            },
                                            "required": ["quantity", "name", "unit"],
                                            "additionalProperties": False
                                        }
                                    }
                                },
                                "required": ["items"],
                                "additionalProperties": False
                            }
                        }
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": "fill_inventory_items"}},
                "temperature": 0,
                "max_completion_tokens": 220,
            },
        )
        response.raise_for_status()
        response_json = response.json()

    message = response_json["choices"][0].get("message", {})
    tool_calls = message.get("tool_calls", [])
    if not tool_calls:
        raise HTTPException(status_code=502, detail="Paytm LLM did not return tool output")

    arguments_text = tool_calls[0].get("function", {}).get("arguments", "")
    try:
        parsed_payload = json.loads(arguments_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Paytm LLM returned invalid tool JSON") from exc

    parsed = parsed_payload.get("items", [])
    if not isinstance(parsed, list):
        raise HTTPException(status_code=502, detail="Paytm LLM tool output has invalid shape")

    items: list[ParsedItem] = []
    for entry in parsed:
        try:
            quantity = max(1, int(entry.get("quantity", 1)))
        except (TypeError, ValueError):
            continue

        raw_product_id = entry.get("product_id")
        product_info = None
        product_id: Optional[int] = None
        if raw_product_id is not None:
            try:
                product_id = int(raw_product_id)
                product_info = product_by_id.get(product_id)
            except (TypeError, ValueError):
                product_id = None

        if not product_info and entry.get("name"):
            product_info = None
            for candidate in products:
                aliases = _canonical_aliases_for_product(candidate)
                if normalize(str(entry.get("name"))) in aliases:
                    product_info = {
                        "product_id": int(cast(int, candidate.id)),
                        "name": str(cast(str, candidate.name)),
                        "name_hi": str(cast(str, candidate.name_hi)),
                        "unit": str(cast(str, candidate.unit)),
                        "price": float(cast(float, candidate.price)),
                        "gst_rate": float(cast(float, candidate.gst_rate)),
                    }
                    product_id = int(cast(int, candidate.id))
                    break

        if product_info:
            price_from_llm = entry.get("price")
            try:
                price_val = float(price_from_llm) if price_from_llm is not None else float(product_info["price"])
            except Exception:
                price_val = float(product_info["price"])

            items.append(ParsedItem(
                product_id=product_id,
                name=str(product_info["name"]),
                name_hi=str(product_info["name_hi"]),
                quantity=quantity,
                unit=str(product_info["unit"]),
                price=price_val,
                gst_rate=float(product_info["gst_rate"]),
            ))
            continue

        # Custom/non-catalog product: keep it visible in the UI with LLM-provided values.
        items.append(ParsedItem(
            product_id=None,
            name=str(entry.get("name") or "Unknown item"),
            name_hi=str(entry.get("name_hi") or entry.get("name") or ""),
            quantity=quantity,
            unit=str(entry.get("unit") or "piece"),
            price=float(entry.get("price") or 0.0),
            gst_rate=float(entry.get("gst_rate") or 0.0),
        ))

    return items


def _demo_items_from_transcript(transcript: str) -> list[ParsedItem]:
    return parse_transcript_demo(transcript)


def _auto_parse_without_llm(transcript: str, db: Session) -> list[ParsedItem]:
    products = db.query(Product).all()
    return parse_transcript_with_db_products(transcript, products)


@router.post("/parse", response_model=VoiceParseResponse)
async def parse_voice(
    audio: Optional[UploadFile] = File(None),
    transcript: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Parse voice audio OR text transcript into structured inventory items.
    Uses Sarvam APIs when configured; demo mode is opt-in only.
    """
    final_transcript = ""
    translated_transcript = ""

    if transcript:
        final_transcript = transcript.strip()
    elif audio:
        if not SARVAM_API_KEY:
            raise HTTPException(status_code=503, detail="SARVAM_API_KEY is not configured")
        audio_bytes = await audio.read()
        filename = audio.filename or "audio.webm"
        final_transcript = await sarvam_stt(audio_bytes, filename, mode="transcribe")

        if SARVAM_PARSE_USE_TRANSLATED_TEXT:
            translated_transcript = await sarvam_stt(audio_bytes, filename, mode="translate")

    if not final_transcript:
        raise HTTPException(status_code=422, detail="Provide transcript text or audio to parse")

    try:
        items = await paytm_llm_parse(final_transcript, db, translated_transcript or None)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Paytm parse failed: {str(exc)}") from exc

    return VoiceParseResponse(
        transcript=final_transcript,
        items=items,
        demo_mode=False,
    )


@router.post("/tts", response_model=TTSResponse)
async def text_to_speech(req: TTSRequest):
    """Convert Hindi text to speech using Bulbul V3 TTS."""
    if not SARVAM_API_KEY:
        raise HTTPException(status_code=503, detail="SARVAM_API_KEY is not configured")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{SARVAM_API_BASE_URL}/text-to-speech",
                headers={
                    **_sarvam_headers(),
                    "Content-Type": "application/json",
                },
                json={
                    "inputs": [req.text],
                    "target_language_code": "hi-IN" if (getattr(req, 'language', 'hi') or '').startswith('hi') else 'en-US',
                    "speaker": "meera" if (getattr(req, 'language', 'hi') or '').startswith('hi') else 'sam',
                    "model": SARVAM_TTS_MODEL,
                },
            )
            response.raise_for_status()
            audios = response.json().get("audios", [])
            audio_b64 = audios[0] if audios else ""
            return TTSResponse(audio_base64=audio_b64, text=req.text)
    except Exception:
        return TTSResponse(audio_base64="", text=req.text)
