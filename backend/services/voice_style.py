"""The shopkeeper's voice: what Awaaz says, how it is paced and how it is written for Bulbul TTS.

Pure module (no network, no database). Three jobs:

  * `line(kind, **facts) -> Line(text, pace, kind)`: a short, warm, slightly witty Hinglish reply
    for one situation, picked from 3-5 variants. Deterministic with `seed=` (tests); otherwise a
    random variant that never repeats the previous line of the same kind in the same `session=`.
    Light humour (about one reply in five) only on kinds that carry no money amount and no error.
  * `prepare_for_tts(text)`: the text Bulbul actually reads. Rupee amounts become "249 rupaye"
    (numbers of five digits or more get Indian commas), symbols and emoji become words or vanish,
    "kg/g/L" become "kilo/gram/litre", brand names that Bulbul tends to mangle get a phonetic
    spelling (flag `settings.voice_pronunciation_fixes`).
  * `pace_for(kind, text)`: acknowledgements and confirmations brisk (1.05), normal 1.0, warnings
    and money totals a little slower (0.93-0.97).

Written text on screen stays identical to the spoken line, so a line keeps the "₹294" form; only
`prepare_for_tts` rewrites it, at the moment audio is requested.

Persona: a counter, not a classroom. Romanised Hindi with English item words; short lines, one idea
per sentence; fillers as glue (ji, haan, lo, achha, theek hai, dekhiye); no gendered first-person
verbs (the default voice is female, the merchant may configure a male one), so "dekhte hain", not
"dekhta hoon".
"""
from __future__ import annotations

import random
import re
import string
from dataclasses import dataclass
from typing import Any, Optional

from config import settings
from services import sarvam

MAX_CHARS = 140  # TTS latency scales with length; keep every single line under this
WITTY_RATE = 0.2  # about one reply in five, only on kinds that allow it
WITTY_COOLDOWN = 3  # at least this many plain lines (per session) between two witty ones


@dataclass(frozen=True)
class Line:
    text: str
    pace: float
    kind: str = ""


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------


def inr(x: float) -> str:
    """Indian grouping, no symbol: 1350 -> '1,350', 123456 -> '1,23,456', 249.5 -> '249.50'."""
    x = round(float(x), 2)
    whole = int(abs(x))
    frac = abs(x) - whole
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    if frac >= 0.005:
        s += f"{frac:.2f}"[1:]
    return ("-" if x < 0 else "") + s


def rs(x: float) -> str:
    """'₹294' (on-screen form; prepare_for_tts turns it into '294 rupaye')."""
    return f"₹{inr(x)}"


MONEY_KEYS = {"total", "due", "amount", "balance", "bal", "old_price", "new_price", "price", "limit",
              "paid", "rest"}


def _facts(facts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in facts.items():
        if v is None:
            continue
        if k in MONEY_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = rs(v)
        elif isinstance(v, float) and v == int(v):
            out[k] = int(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# the phrase bank
#
# kind -> (plain variants, witty variants). A variant is only used when every {field} in it was
# given as a fact, so one kind can offer richer variants when more facts are known.
# ---------------------------------------------------------------------------

_BANK: dict[str, tuple[list[str], list[str]]] = {
    # --- cart edits ---------------------------------------------------------------------------
    "items_added": ([
        "{items}, likh liya. Total {total}.",
        "Achha, {items}. Total {total} hua.",
        "Ji, {items} jod diya. Abhi tak {total}.",
        "{items}. Ho gaya, total {total}.",
        "Ho gaya ji. Total {total}.",
        "Lijiye, likh liya. Total {total}.",
        "Theek hai, jod diya. Abhi tak {total}.",
    ], []),
    "total_now": ([
        "Total {total} hua.",
        "Abhi tak {total}.",
        "Kul {total} ho gaya.",
        "Total {total}, ji.",
    ], []),
    "loose_item": ([
        "{label}, {qty_text}. {verb} dijiye.",
        "{label}: {qty_text}. {verb} lijiye.",
        "Achha, {qty_text} {name}. {verb} dijiye.",
        "{name}, {qty_text}. {verb} dijiye.",
    ], []),
    "item_removed": ([
        "{name} hata diya.",
        "Theek hai, {name} hata diya.",
        "Ji, {name} cart se hata diya.",
        "{name} hata di, ji.",
    ], [
        "{name} ko chhutti de di.",
    ]),
    "qty_changed": ([
        "{name} ab {qty_text}.",
        "Theek hai, {qty_text} {name} kar diya.",
        "Achha, {name} {qty_text} kar di.",
        "Ho gaya, ab {qty_text} {name}.",
    ], []),
    "undo_done": ([
        "Theek hai, wapas kar diya.",
        "Achha, pichla badlaav hata diya.",
        "Ho gaya, jaisa pehle tha.",
    ], [
        "Koi baat nahi, sab pehle jaisa.",
    ]),
    "cart_empty": ([
        "Cart khali hai ji, pehle saaman bolo.",
        "Abhi kuch nahi likha. Saaman bolo ji.",
        "Cart khali hai. Boliye, kya dena hai?",
    ], []),
    # --- not understood / not in the catalogue ------------------------------------------------
    "nothing_understood": ([
        "Samajh nahi aaya, dobara bolna?",
        "Ek baar phir bolna ji, saaf sunai nahi diya.",
        "Maaf kijiye, dobara bataiye?",
        "Thoda saaf bolna ji, dobara?",
    ], []),
    "nothing_heard": ([
        "Kuch sunai nahi diya, dobara bolna ji.",
        "Awaaz nahi aayi, ek baar phir bolna?",
        "Sunai nahi diya ji, dobara boliye.",
    ], []),
    "missed_sale": ([
        "{name} abhi nahi hai, note kar liya.",
        "Ji, {name} nahi hai. Likh liya, mangwa lenge.",
        "{name} khatam hai ji, note kar liya.",
        "Achha, {name} chahiye tha? Note kar liya.",
    ], []),
    # --- checkout and payment -----------------------------------------------------------------
    "confirm_needed": ([
        "Kul {total}. Bill bana doon? Haan bolo.",
        "{total} hua. Bill bana doon? Haan bolo.",
        "Total {total}. Bill banau? Haan bolo.",
        "Bill bana doon? Haan bolo.",
    ], []),
    "confirm_what": ([
        "{what}? Haan bolo.",
        "{what}. Theek hai? Haan bolo.",
        "Dekhiye, {what}. Haan bolo.",
    ], []),
    "checkout_ready": ([
        "Total {total}. QR scan kijiye.",
        "Ye lijiye, {total} ka QR. Scan kar dijiye.",
        "Bill {total} ka hai. QR se pay kar dijiye.",
        "Kul {total}. QR scan karke pay kijiye.",
    ], []),
    "checkout_partial": ([
        "Kul {total}. {due} ka QR scan kijiye.",
        "Bill {total} ka hai, ye lijiye {due} ka QR.",
        "Total {total}. Baaki {due} QR se pay kijiye.",
    ], []),
    "bill_done": ([
        "Bill ban gaya, kul {total}.",
        "Ho gaya ji, kul {total}.",
        "Lijiye, bill ban gaya. Kul {total}.",
        "Theek hai, {total} ka bill ban gaya.",
    ], []),
    "payment_received": ([
        "{amount} mil gaye. Dhanyavaad ji.",
        "Payment aa gaya, {amount}. Shukriya!",
        "Haan ji, {amount} aa gaye.",
        "{amount} mil gaye. Bahut shukriya.",
    ], []),
    "payment_partial": ([
        "{amount} aa gaye. Baaki {rest} abhi baaki hai.",
        "Haan ji, {amount} mile. {rest} aur chahiye.",
    ], []),
    "payment_failed": ([
        "Payment nahi hua. Dobara try kijiye.",
        "Ji, payment fail ho gaya. Ek baar phir scan kijiye.",
    ], []),
    "low_stock": ([
        "{name} sirf {qty} bacha hai.",
        "Dhyan dijiye, {name} kam hai, {qty} bacha.",
        "{name} khatam hone wala hai, {qty} bacha hai.",
    ], [
        "{name} jaldi ud raha hai, {qty} hi bacha.",
    ]),
    "out_of_stock": ([
        "{name} khatam ho gaya.",
        "Dhyan dijiye, {name} khatam ho gaya.",
        "{name} ab stock mein nahi hai.",
    ], [
        "{name} ki chhutti ho gayi, khatam hai.",
    ]),
    "low_stock_more": ([
        "Aur {more} cheezein bhi kam hain.",
        "{more} aur cheezein bhi kam hain.",
    ], []),
    "low_stock_one_more": ([
        "Ek aur cheez bhi kam hai.",
        "Aur ek cheez bhi kam hai.",
    ], []),
    # --- khata ---------------------------------------------------------------------------------
    "udhaar_proposed": ([
        "{customer} ke khate mein {amount} likhun? Haan bolo.",
        "{customer} ko {amount} udhaar? Haan bolo.",
        "Ji, {customer} ke khate mein {amount} likh doon? Haan bolo.",
    ], []),
    "udhaar_over_limit": ([
        "{customer} ki limit paar ho jayegi. Phir bhi {amount} likhun? Haan bolo.",
        "Dhyan dijiye, {customer} limit se upar jayenge. {amount} likhun? Haan bolo.",
    ], []),
    "udhaar_confirmed": ([
        "{customer} ke khate mein {amount} likh diya. Kul baaki {balance}.",
        "Ho gaya ji. {customer} ka baaki ab {balance}.",
        "Likh liya, {customer} ke khate mein {amount}. Kul baaki {balance}.",
    ], []),
    "khata_payment": ([
        "{customer} se {amount} jama karun? Haan bolo.",
        "{customer} ne {amount} diye? Jama kar doon, haan bolo.",
        "Ji, {customer} ke {amount} jama kar doon? Haan bolo.",
    ], []),
    "khata_payment_done": ([
        "{customer} se {amount} jama ho gaye. Baaki {balance}.",
        "Ho gaya ji. {customer} ka baaki ab {balance}.",
        "Jama kar liya, {amount}. {customer} ka baaki {balance}.",
    ], []),
    "ask_customer": ([
        "Kaun se customer? Naam samajh nahi aaya.",
        "Kiska khata? Naam dobara bolna ji.",
    ], []),
    "ask_amount": ([
        "{customer} ke khate mein kitna likhun?",
        "Ji, {customer} ke liye kitna?",
    ], []),
    "ask_khata_customer": ([
        "Kiske khate mein likhun?",
        "Khata kiska hai ji? Naam bolo.",
    ], []),
    "split_mismatch": ([
        "Hisaab nahi baith raha. Bill {total} ka hai, dobara bolna.",
        "Parts ka jod bill se nahi mil raha. Dobara bolna ji.",
    ], []),
    "split_parts": ([
        "Kul {total}: {parts}.",
        "Total {total}. {parts}.",
    ], []),
    "items_noted": ([
        "{items}, likh liya.",
        "Achha, {items} jod diya.",
        "Ji, {items}, likh liya.",
    ], []),
    "split_summary": ([
        "Kul {total}: {parts}. Theek hai? Haan bolo.",
        "Total {total}. {parts}. Haan bolo.",
    ], []),
    # --- stock and prices ---------------------------------------------------------------------
    "restock_ask": ([
        "Kaun sa maal aaya? Dobara bolna ji.",
        "Maal ka naam samajh nahi aaya. Dobara boliye.",
    ], []),
    "restock_proposed": ([
        "{items} stock mein jodun? Haan bolo.",
        "Ji, {items} stock mein jod doon? Haan bolo.",
        "{items} aaya? Stock mein chadha doon, haan bolo.",
    ], []),
    "restock_done": ([
        "Stock update ho gaya: {items}.",
        "Ho gaya ji, stock mein chadha diya. {items}.",
        "Lijiye, stock theek kar diya. {items}.",
    ], []),
    "price_ask": ([
        "Kaun sa item aur kitna rate? Dobara bolna.",
        "Item ka naam aur rate, dono bolna ji.",
    ], []),
    "price_proposed": ([
        "{name} ka rate {old_price} se {new_price} per {unit}? Haan bolo.",
        "{name} ab {new_price} per {unit}, pehle {old_price}. Haan bolo.",
    ], []),
    "price_done": ([
        "{name} ka rate ab {price} hai.",
        "Ho gaya ji, {name} ab {price}.",
    ], []),
    # --- control phrases ----------------------------------------------------------------------
    "action_cancelled": ([
        "Theek hai, cancel kar diya.",
        "Chhodiye, cancel kar diya.",
        "Achha, rehne dete hain.",
        "Ho gaya, cancel.",
    ], [
        "Koi baat nahi, ise rehne dete hain.",
    ]),
    "nothing_to_confirm": ([
        "Confirm karne ke liye kuch nahi hai.",
        "Abhi haan karne layak kuch nahi hai ji.",
    ], []),
    "nothing_to_undo": ([
        "Undo karne ke liye kuch nahi hai.",
        "Wapas karne ke liye kuch nahi hai ji.",
    ], []),
    "undo_after_bill": ([
        "Bill ban chuka hai, ab wapas nahi ho sakta.",
        "Ji, bill ban gaya hai. Ab wapas nahi hoga.",
    ], []),
    "generic_ok": ([
        "Ho gaya.",
        "Theek hai ji.",
        "Lijiye.",
        "Ji, kar diya.",
    ], [
        "Ho gaya, ek second bhi nahi laga.",
    ]),
    "ask_unavailable": ([
        "Abhi is sawaal ka jawab nahi de sakte. AI judte hi bata denge.",
        "Ye sawaal abhi nahi ho paayega ji. AI judte hi jawab milega.",
    ], []),
    # --- receipts -----------------------------------------------------------------------------
    "voice_receipt": ([
        "Aapne {items} liya, kul {total}.{khata} Dhanyavaad, {store} mein phir aaiyega.",
        "Namaste! {items}, kul {total}.{khata} Shukriya, {store} mein phir aaiyega.",
        "Dhanyavaad ji! Aapne {items} liya. Kul {total}.{khata} {store} mein phir aaiyega.",
    ], []),
    "voice_receipt_short": ([
        "Aapne {count} cheezein liya, kul {total}.{khata} Dhanyavaad, {store} mein phir aaiyega.",
        "Namaste! {count} cheezein, kul {total}.{khata} Shukriya, {store} mein phir aaiyega.",
    ], []),
}

# Aliases: same bank, another name.
_ALIASES = {"not_in_catalog": "missed_sale", "udhaar": "udhaar_proposed", "ok": "generic_ok"}

# Pace per kind. Acks and confirmations brisk, money and warnings a touch slower.
_PACE: dict[str, float] = {
    "items_added": 1.0, "total_now": 0.97, "loose_item": 1.0, "item_removed": 1.05, "qty_changed": 1.05,
    "undo_done": 1.05, "cart_empty": 1.0, "nothing_understood": 1.0, "nothing_heard": 1.0,
    "missed_sale": 1.0, "confirm_needed": 0.97, "confirm_what": 0.97, "checkout_ready": 0.95,
    "checkout_partial": 0.95, "bill_done": 0.95, "payment_received": 0.95, "payment_partial": 0.95,
    "payment_failed": 0.93, "low_stock": 0.95, "out_of_stock": 0.95, "low_stock_more": 0.97, "low_stock_one_more": 0.97,
    "udhaar_proposed": 0.95, "udhaar_over_limit": 0.93, "udhaar_confirmed": 0.95, "khata_payment": 0.95,
    "khata_payment_done": 0.95, "ask_customer": 1.0, "ask_amount": 1.0, "ask_khata_customer": 1.0,
    "split_mismatch": 0.95, "split_summary": 0.95, "split_parts": 0.95, "items_noted": 1.0, "restock_ask": 1.0, "restock_proposed": 1.0,
    "restock_done": 1.0, "price_ask": 1.0, "price_proposed": 0.95, "price_done": 0.97,
    "action_cancelled": 1.05, "nothing_to_confirm": 1.0, "nothing_to_undo": 1.0, "undo_after_bill": 0.97,
    "generic_ok": 1.05, "ask_unavailable": 1.0, "voice_receipt": 0.97, "voice_receipt_short": 0.97,
}

KINDS = tuple(sorted(set(_BANK) | set(_ALIASES)))


def _canon(kind: str) -> str:
    kind = _ALIASES.get(kind, kind)
    if kind not in _BANK:
        raise ValueError(f"unknown voice line kind: {kind}")
    return kind


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def _render(templates: list[str], facts: dict[str, Any]) -> list[str]:
    """Variants whose fields are all known, rendered, tidy, and under the length cap."""
    out = []
    for t in templates:
        if _fields(t) <= set(facts):
            out.append(_tidy(t.format(**facts)))
    return out


def _tidy(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"([.!?])\1+", r"\1", text)
    return text


def variants(kind: str, **facts: Any) -> list[str]:
    """Every rendered variant (plain then witty) for `kind` given `facts`. Used by tests."""
    plain, witty = _BANK[_canon(kind)]
    f = _facts(facts)
    return _render(plain, f) + _render(witty, f)


def clip(text: str, limit: int = MAX_CHARS) -> str:
    """Cut at the last sentence end within `limit` (or the last word), never mid-word."""
    text = _tidy(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    ends = [m.end() for m in re.finditer(r"[.!?]", cut)]
    if ends and ends[-1] > limit * 0.4:
        return cut[:ends[-1]].strip()
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "."


# ---------------------------------------------------------------------------
# picking a variant
# ---------------------------------------------------------------------------

_rng = random.Random()
_last_text: dict[tuple[str, str], str] = {}  # (session, kind) -> last spoken text
_since_witty: dict[str, int] = {}  # session -> plain lines since the last witty one
_MAX_TRACKED = 4000


def reset_memory() -> None:
    """Forget the anti-repeat state (tests)."""
    _last_text.clear()
    _since_witty.clear()


def pick(options: list[str], *, key: str, seed: Any = None, session: Optional[str] = None) -> str:
    """One of `options`: deterministic with a seed, else random but never the previous pick for
    (session, key). Shared by the phrase-bank ack chooser."""
    if not options:
        raise ValueError("no options")
    if seed is not None:
        return random.Random(f"{seed}|{key}").choice(options)
    memo = (session or "", key)
    last = _last_text.get(memo)
    pool = [o for o in options if o != last] or options
    choice = _rng.choice(pool)
    if len(_last_text) > _MAX_TRACKED:
        _last_text.clear()
    _last_text[memo] = choice
    return choice


def line(kind: str, *, seed: Any = None, session: Optional[str] = None, max_chars: int = MAX_CHARS,
         **facts: Any) -> Line:
    """The spoken line for a situation. `seed` makes the choice deterministic (tests); otherwise
    the variant is random, never equal to the previous line of this kind in this `session`."""
    canon = _canon(kind)
    plain, witty = _BANK[canon]
    f = _facts(facts)
    plain_r = [t for t in _render(plain, f) if len(t) <= max_chars]
    witty_r = [t for t in _render(witty, f) if len(t) <= max_chars]
    if not plain_r:  # nothing fits: fall back to the shortest render, clipped
        every = _render(plain, f) + _render(witty, f)
        if not every:
            raise ValueError(f"line '{kind}' needs facts: {sorted(_fields(plain[0]))}")
        text = clip(min(every, key=len), max_chars)
        return Line(text, pace_for(canon, text), canon)

    sess = session or ""
    if seed is not None:
        rng = random.Random(f"{seed}|{canon}")
        use_witty = bool(witty_r) and rng.random() < WITTY_RATE
        text = rng.choice(witty_r if use_witty else plain_r)
        return Line(text, pace_for(canon, text), canon)

    since = _since_witty.get(sess, WITTY_COOLDOWN)
    use_witty = bool(witty_r) and since >= WITTY_COOLDOWN and _rng.random() < WITTY_RATE
    if len(_since_witty) > _MAX_TRACKED:
        _since_witty.clear()
    _since_witty[sess] = 0 if use_witty else since + 1
    text = pick(witty_r if use_witty else plain_r, key=canon, session=sess)
    return Line(text, pace_for(canon, text), canon)


def combine(lines: list[Line], kind: str = "combo") -> Line:
    """Several lines said in one breath. Pace follows the slowest, but never below 0.93."""
    parts = [ln.text for ln in lines if ln.text]
    paces = [ln.pace for ln in lines if ln.text]
    return Line(clip(" ".join(parts), 220), max(0.93, min(paces)) if paces else 1.0, kind)


# ---------------------------------------------------------------------------
# pace
# ---------------------------------------------------------------------------


def pace_for(kind: Optional[str], text: str = "") -> float:
    """Speaking pace for a line. Known kinds use the table; free text falls back to a heuristic:
    money or long text slower, short acknowledgements brisk."""
    if kind:
        try:
            return _PACE.get(_canon(kind), 1.0)
        except ValueError:
            pass
    t = text or ""
    if re.search(r"₹|\brupaye\b|\bRs\b", t):
        return 0.96
    if len(t) <= 25:
        return 1.05
    if len(t) > 110:
        return 0.97
    return 1.0


# ---------------------------------------------------------------------------
# text for the TTS engine
# ---------------------------------------------------------------------------

# Brand names Bulbul tends to mangle when read as English letters: Devanagari spelling. Applied to the
# TTS text only, never to what is shown on screen. Turn off with VOICE_PRONUNCIATION_FIXES=off.
# UNVERIFIED against live Bulbul: listen to each before relying on it.
PRONUNCIATION_FIXES: dict[str, str] = {
    "surf excel": "सर्फ एक्सेल",
    "colgate": "कोलगेट",
    "parle-g": "पारले जी",
    "parle g": "पारले जी",
    "dettol": "डेटॉल",
    "aashirvaad": "आशीर्वाद",
    "ashirvaad": "आशीर्वाद",
    "patanjali": "पतंजलि",
    "bournvita": "बॉर्नविटा",
}
_BRAND_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(
    re.escape(k) for k in sorted(PRONUNCIATION_FIXES, key=len, reverse=True)) + r")(?![A-Za-z])", re.I)

_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]")
_MONEY_RE = re.compile(r"(?:₹|\bRs\.?|\bINR)\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", re.I)
_UNIT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?(kgs?|kilograms?|gms?|grams?|g|ml|ltr|litres?|liters?|lt|l)\b(?![\w-])",
                      re.I)
_UNIT_WORDS = {"kg": "kilo", "kgs": "kilo", "kilogram": "kilo", "kilograms": "kilo", "g": "gram",
               "gm": "gram", "gms": "gram", "gram": "gram", "grams": "gram", "ml": "millilitre",
               "l": "litre", "lt": "litre", "ltr": "litre", "litre": "litre", "litres": "litre",
               "liter": "litre", "liters": "litre"}
_FRACTION_WORDS = {0.5: "aadha", 1.5: "dedh", 2.5: "dhai"}


def _unit_sub(m: re.Match) -> str:
    num = float(m.group(1))
    word = _UNIT_WORDS[m.group(2).lower()]
    if word in ("kilo", "litre") and num in _FRACTION_WORDS:
        return f"{_FRACTION_WORDS[num]} {word}"
    shown = m.group(1)
    return f"{shown} {word}"


def prepare_for_tts(text: str, *, pronunciation: Optional[bool] = None) -> str:
    """Rewrite a display line into what Bulbul should read.

    Amounts: '₹1350' -> '1350 rupaye', '₹12345.50' -> '12,345 rupaye 50 paise' (commas from five
    digits). Units: '2 kg' -> '2 kilo', '450 g' -> '450 gram', '1.5 L' -> 'dedh litre'. Symbols
    become words ('%' -> 'percent', '&' -> 'aur') or disappear; emoji and em-dashes are removed."""
    out = text or ""
    out = _EMOJI_RE.sub("", out)
    use_fixes = settings.voice_pronunciation_fixes if pronunciation is None else pronunciation
    if use_fixes:
        out = _BRAND_RE.sub(lambda m: PRONUNCIATION_FIXES[m.group(1).lower()], out)
    out = _MONEY_RE.sub(lambda m: sarvam.speak_rupees(float(m.group(1).replace(",", ""))), out)
    out = _UNIT_RE.sub(_unit_sub, out)
    out = re.sub(r"(\d+(?:\.\d+)?)\s?%", r"\1 percent", out)
    out = out.replace("₹", " rupaye ")
    out = re.sub(r"[—–]", ", ", out)
    out = out.replace("…", ".")
    out = out.replace("&", " aur ").replace("+", " plus ").replace("@", " at ")
    out = out.replace("×", " ").replace("=", " ")
    out = re.sub(r"\s*[()\[\]{}]\s*", ", ", out)
    out = re.sub(r"[#*_~^|<>\"`]", " ", out)
    out = re.sub(r"(?<=\D)/(?=\D)|(?<=\s)/|/(?=\s)", " ", out)
    out = re.sub(r"[:;](?!\d)", ",", out)
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"\s+([,.!?])", r"\1", out)
    out = re.sub(r",\s*,+", ",", out)
    out = re.sub(r",\s*([.!?])", r"\1", out)
    out = re.sub(r"([.!?])\s*,\s*", r"\1 ", out)
    out = re.sub(r"^[,\s]+|[,\s]+$", "", out)
    return sarvam.prepare_tts_text(out.strip())
