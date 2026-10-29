"""Deterministic demo data for every AI call, so the demo never fails.

  * STT: transcripts for the demo phrases, picked by an `X-Demo-Phrase` header
    (phrase id or the phrase text) or by passing text through.
  * LLM: tool calls produced by the rules parser (same shape as a real model).
  * Vision: fixtures matching the Ramesh General Store story (see seed.py).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from services import catalog, quantity
from services.types import ChatOut, ToolCall

DEMO_PHRASES: dict[str, str] = {
    "1": "do maggi ek surf excel chaar colgate",
    "2": "das packet maggi paanch kilo chawal do litre tel",
    "3": "aashirvaad atta teen bag tata namak chaar packet",
    "4": "paanch dettol sabun teen vim bar do parle g",
    "5": "ek patanjali shahad do colgate",
    "6": "bhaiya do maggi ek surf aur bees rupaye ki cheeni",
    "7": "verma ji ke khate mein paanch sau",
    "8": "teen sau cash diya do sau paytm baaki khate mein",
    "9": "kurkure nahi hai",
    "10": "bas kitna hua",
}


def demo_phrase(key_or_text: Optional[str]) -> str:
    """Resolve an X-Demo-Phrase value: an id ('1'..'10'), literal text, or empty -> phrase 1."""
    if key_or_text:
        k = key_or_text.strip()
        return DEMO_PHRASES.get(k, k)
    return DEMO_PHRASES["1"]


def stt_fixture(demo_key: Optional[str] = None, text: Optional[str] = None) -> dict[str, str]:
    """STT stand-in. `text` (a passthrough transcript) wins over the demo key."""
    return {"transcript": (text or demo_phrase(demo_key)).strip(), "language_code": "hi-IN"}


# --- rules-based "LLM" ---

_AMOUNT_WORDS = re.compile(r"\b(rupaye|rupay|rupees|rs)\b")
_CASH = {"cash", "naqad", "nakad", "कैश"}
_UPI = {"paytm", "upi", "phonepe", "gpay", "googlepay", "paytem", "पेटीएम", "यूपीआई"}
_KHATA = {"khata", "khate", "udhaar", "udhar", "उधार", "खाते", "खाता"}


def _amounts_by_keyword(text: str, index: catalog.CatalogIndex) -> dict[str, Optional[float]]:
    """{'cash': 300, 'upi': 200, 'khata': None} where None means 'the remainder'."""
    toks = quantity._tokenize(catalog.normalize(text).split(), index)
    out: dict[str, Optional[float]] = {}
    pending: Optional[float] = None
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.kind in ("num", "mult", "frac", "pre", "numunit", "numrupee"):
            q, j = quantity._read_qty(toks, i)
            if q is not None:
                pending = q.value
            i = j
            continue
        word = t.raw
        key = "cash" if word in _CASH else "upi" if word in _UPI else "khata" if word in _KHATA else None
        if key:
            if pending is not None:
                out[key] = pending
                pending = None
            else:
                after = quantity._read_qty(toks, i + 1) if i + 1 < len(toks) else (None, i)
                out[key] = after[0].value if after[0] is not None else None
        i += 1
    return out


def rules_tool_calls(text: str, db: Session, context: str = "counter") -> list[ToolCall]:
    """Map an utterance to LLM-style tool calls using rules only."""
    norm = catalog.normalize(text)
    index = catalog.load_index(db)
    if not norm:
        return []
    if quantity.is_checkout_phrase(norm):
        return [ToolCall("checkout", {})]

    words = norm.split()
    if "nahi" in words or "nahin" in words or "khatam" in words:
        name = " ".join(w for w in words if w not in ("nahi", "nahin", "hai", "hain", "khatam", "ho", "gaya"))
        if name:
            product, _ = index.match(name)
            return [ToolCall("missed_sale", {"product": name,
                                             "product_id": int(product.id) if product else None})]

    if any(w in _KHATA for w in words):
        amounts = _amounts_by_keyword(norm, index)
        if ("cash" in amounts or "upi" in amounts) and len(amounts) >= 2:
            return [ToolCall("split_payment", {"cash": amounts.get("cash"), "upi": amounts.get("upi"),
                                               "khata": amounts.get("khata")})]
        m = re.match(r"^(.*?)\s+(?:ke|ka|ki|ko)\s+(?:khate|khata|udhaar|udhar)\b", norm)
        spoken = m.group(1) if m else ""
        if spoken:
            customer, _ = catalog.match_customer(db, spoken)
            qty_toks = quantity._tokenize(norm.split(), index)
            amt = None
            for i, t in enumerate(qty_toks):
                if t.kind in ("num", "mult", "frac", "pre", "numunit"):
                    q, _ = quantity._read_qty(qty_toks, i)
                    if q is not None:
                        amt = q.value
                        break
            return [ToolCall("add_udhaar", {"customer": spoken, "amount": amt,
                                            "customer_id": int(customer.id) if customer else None})]

    outcome = quantity.parse_order_full(norm, index=index)
    tool = "restock" if context == "stock" else "add_to_cart"
    calls: list[ToolCall] = []
    if outcome.lines:
        calls.append(ToolCall(tool, {"items": [
            {"product_id": ln.product_id, "name": ln.name, "qty": ln.qty, "unit": ln.unit,
             "amount_rupees": ln.amount_rupees} for ln in outcome.lines]}))
    for miss in outcome.unmatched:
        calls.append(ToolCall("missed_sale", {"product": miss["name"], "product_id": None}))
    return calls


def llm_fixture(messages: list[dict[str, Any]], db: Session, context: str = "counter") -> ChatOut:
    """Chat completion stand-in built from the last user message."""
    text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content")
            text = content if isinstance(content, str) else " ".join(
                p.get("text", "") for p in content or [] if isinstance(p, dict))
            break
    calls = rules_tool_calls(text, db, context)
    return ChatOut(content="" if calls else "Samajh nahi aaya, dobara bolein.", tool_calls=calls)


# --- vision fixtures (Ramesh General Store story) ---


def vision_fixture(task: str, today: Optional[date] = None) -> Any:
    """Deterministic extraction result per vision task."""
    today = today or date.today()
    if task == "shelf":
        return [{"name": "Maggi noodles", "quantity": 8}, {"name": "Parle-G biscuits", "quantity": 12},
                {"name": "Colgate toothpaste", "quantity": 6}, {"name": "Surf Excel", "quantity": 4}]
    if task == "purchase_bill":
        def line(name, qty, rate, mrp, batch, days, scheme="", free=0, unit="packet"):
            return {"name": name, "qty": qty, "unit": unit, "rate": rate, "mrp": mrp, "batch": batch,
                    "expiry": (today + timedelta(days=days)).isoformat(), "scheme_text": scheme,
                    "free_qty": free}
        return {
            "supplier": "Rajesh Distributors", "bill_no": "RD/2526/4471", "date": today.isoformat(),
            "lines": [
                # the story: Surf now Rs 45 (was Rs 42), "Buy 10 Get 1 Free" but the free packet is missing
                line("Surf Excel Easy Wash", 10, 45.0, 45.0, "SE2609B", 600, "Buy 10 Get 1 Free", 0),
                line("Maggi 2-Minute Noodles 70g", 48, 11.0, 12.0, "MG0926", 240),
                line("Colgate Strong Teeth 100g", 24, 41.0, 45.0, "CG1026", 700),
                line("Parle-G 56g", 60, 8.6, 10.0, "PG0926", 150),
                line("Dettol Original Soap 75g", 24, 31.0, 35.0, "DT0926", 700, unit="soap"),
                line("Vim Dishwash Bar 155g", 24, 12.5, 15.0, "VM0926", 500, unit="bar"),
                line("Tata Salt 1kg", 20, 25.0, 28.0, "TS0926", 540),
                line("Bournvita 500g Jar", 6, 175.0, 190.0, "BV0826", 45, unit="jar"),  # expires soon
                line("Britannia Good Day Cashew 75g", 36, 8.5, 10.0, "GD0926", 150),
                line("Haldi Powder 100g", 12, 34.0, 40.0, "HL0926", 360),
                line("Cadbury Dairy Milk 25g", 48, 17.5, 20.0, "DM0926", 200),
                line("Haldiram Bhujia 200g", 12, 48.0, 55.0, "HB0926", 120),
                # not in the catalog: a new-product candidate
                line("Lays Magic Masala 52g", 24, 17.0, 20.0, "LY0926", 100),
            ],
        }
    if task == "parchi":
        return [{"name": "maggi", "qty": 2, "unit": "packet"}, {"name": "cheeni", "qty": 1, "unit": "kg"},
                {"name": "surf excel", "qty": 1, "unit": "packet"}, {"name": "dal", "qty": 500, "unit": "g"},
                {"name": "doodh", "qty": 1, "unit": "packet"},
                {"name": "kurkure", "qty": 1, "unit": "packet"}]  # Kurkure is not in the catalog
    if task == "khata_page":
        return [
            {"customer": "Tiwari ji", "amount": 420.0, "date": "2026-09-30", "note": "ration"},
            {"customer": "Mishra ji", "amount": 1150.0, "date": "2026-10-05", "note": "mahina"},
            {"customer": "Pandey ji", "amount": 275.0, "date": "2026-10-12", "note": ""},
            {"customer": "Rina didi", "amount": 640.0, "date": "2026-10-14", "note": "dudh"},
            {"customer": "Saxena ji", "amount": 90.0, "date": "2026-10-20", "note": ""},
        ]
    if task == "cash":
        return {"denominations": {"2000": 0, "500": 8, "200": 5, "100": 11, "50": 6, "20": 10,
                                  "10": 10, "coins": 0}, "total": 6700, "confidence": 0.88,
                "denomination_confidence": {"2000": 0.95, "500": 0.96, "200": 0.93, "100": 0.92,
                                            "50": 0.82, "20": 0.74, "10": 0.68, "coins": 0.9}}
    raise ValueError(f"unknown vision task: {task}")
