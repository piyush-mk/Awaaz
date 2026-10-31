"""Hindi / Hinglish / Devanagari quantity and order parsing.

`parse_order(text, db)` turns a spoken utterance such as
"do maggi ek surf excel bees rupaye ki cheeni" into cart lines. It is pure rules
(no network, a few ms) so it can answer instantly while the LLM runs.

Handled: digits and number words 1-100 (Roman and Devanagari), hundreds/thousands
("dhai sau gram"), fractions (aadha, paav, sava, dedh, dhai, paune, saadhe),
units (gram, kilo, litre, ml, dozen, packet, bag...), amount-based requests
("bees rupaye ki cheeni" -> 450 g at Rs 44/kg, rounded DOWN to 10 g), quantity
before or after the product, several items per utterance, fuzzy product names.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from models import Product
from schemas import CartLine
from services.catalog import CatalogIndex, load_index, normalize

# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

_NUM_ROMAN = """
ek 1|do 2|teen 3|tin 3|chaar 4|char 4|paanch 5|panch 5|paach 5|chhe 6|chhah 6|chah 6|chhey 6|
saat 7|sat 7|aath 8|aat 8|nau 9|das 10|gyarah 11|barah 12|terah 13|chaudah 14|pandrah 15|
solah 16|satrah 17|atharah 18|unnis 19|bees 20|ikkis 21|baais 22|baees 22|teis 23|chaubis 24|
pachchis 25|pachis 25|pacchis 25|chhabbis 26|sattais 27|atthais 28|unatis 29|tees 30|ikatis 31|
battis 32|taintis 33|chautis 34|paintis 35|chhattis 36|saintis 37|adtis 38|untalis 39|chalis 40|
iktalis 41|bayalis 42|taintalis 43|chavalis 44|paintalis 45|chhiyalis 46|saintalis 47|
adtalis 48|unchas 49|pachas 50|pachaas 50|ikyavan 51|bavan 52|tirpan 53|chauvan 54|
pachpan 55|chhappan 56|sattavan 57|atthavan 58|unsath 59|iksath 61|baasath 62|tirsath 63|
chaunsath 64|painsath 65|chhiyasath 66|sadsath 67|adsath 68|unhattar 69|sattar 70|
ikhattar 71|bahattar 72|tihattar 73|chauhattar 74|pachhattar 75|chhihattar 76|satattar 77|
athattar 78|unasi 79|assi 80|ikyasi 81|bayasi 82|tirasi 83|chaurasi 84|pachasi 85|
chhiyasi 86|sattasi 87|atthasi 88|navasi 89|nabbe 90|ikyanve 91|banve 92|tiranve 93|
chauranve 94|pachanve 95|chhiyanve 96|sattanve 97|atthanve 98|ninyanve 99|
one 1|two 2|three 3|four 4|five 5|six 6|seven 7|eight 8|nine 9|ten 10|eleven 11|twelve 12|
fifteen 15|twenty 20|thirty 30|forty 40|fifty 50|sixty 60|seventy 70|eighty 80|ninety 90
"""
_NUM_DEVA = """
एक 1|दो 2|डू 2|दू 2|तीन 3|चार 4|पांच 5|पाँच 5|छह 6|छः 6|छे 6|सात 7|आठ 8|नौ 9|दस 10|ग्यारह 11|बारह 12|
तेरह 13|चौदह 14|पंद्रह 15|पन्द्रह 15|सोलह 16|सत्रह 17|अठारह 18|उन्नीस 19|बीस 20|इक्कीस 21|
बाईस 22|तेईस 23|चौबीस 24|पच्चीस 25|छब्बीस 26|सत्ताईस 27|अट्ठाईस 28|उनतीस 29|तीस 30|
इकतीस 31|बत्तीस 32|तैंतीस 33|चौंतीस 34|पैंतीस 35|छत्तीस 36|सैंतीस 37|अड़तीस 38|उनतालीस 39|
चालीस 40|इकतालीस 41|बयालीस 42|तैंतालीस 43|चौवालीस 44|पैंतालीस 45|छियालीस 46|सैंतालीस 47|
अड़तालीस 48|उनचास 49|पचास 50|इक्यावन 51|बावन 52|तिरपन 53|चौवन 54|पचपन 55|छप्पन 56|
सत्तावन 57|अट्ठावन 58|उनसठ 59|साठ 60|इकसठ 61|बासठ 62|तिरसठ 63|चौंसठ 64|पैंसठ 65|
छियासठ 66|सड़सठ 67|अड़सठ 68|उनहत्तर 69|सत्तर 70|इकहत्तर 71|बहत्तर 72|तिहत्तर 73|चौहत्तर 74|
पचहत्तर 75|छिहत्तर 76|सतहत्तर 77|अठहत्तर 78|उनासी 79|अस्सी 80|इक्यासी 81|बयासी 82|तिरासी 83|
चौरासी 84|पचासी 85|छियासी 86|सत्तासी 87|अट्ठासी 88|नवासी 89|नब्बे 90|इक्यानवे 91|बानवे 92|
तिरानवे 93|चौरानवे 94|पंचानवे 95|छियानवे 96|सत्तानवे 97|अट्ठानवे 98|निन्यानवे 99
"""


def _table(raw: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in raw.replace("\n", "").split("|"):
        part = part.strip()
        if part:
            word, val = part.rsplit(" ", 1)
            out[word] = float(val)
    return out


NUMBER_WORDS: dict[str, float] = {**_table(_NUM_ROMAN), **_table(_NUM_DEVA)}
MULTIPLIERS = {"sau": 100.0, "सौ": 100.0, "सो": 100.0, "hazaar": 1000.0, "hazar": 1000.0,
               "हज़ार": 1000.0, "हजार": 1000.0, "hundred": 100.0, "thousand": 1000.0}
FRACTIONS = {"aadha": 0.5, "adha": 0.5, "aadhi": 0.5, "aadhaa": 0.5, "half": 0.5,
             "आधा": 0.5, "आधी": 0.5, "paav": 0.25, "pav": 0.25, "पाव": 0.25, "quarter": 0.25,
             "dedh": 1.5, "डेढ़": 1.5, "डेढ": 1.5, "dhai": 2.5, "dhaai": 2.5, "ढाई": 2.5,
             "paun": 0.75, "pauna": 0.75, "पौन": 0.75, "पौना": 0.75}
PREFIXES = {"sava": 0.25, "savaa": 0.25, "सवा": 0.25, "paune": -0.25, "पौने": -0.25,
            "saadhe": 0.5, "sadhe": 0.5, "साढ़े": 0.5, "साढे": 0.5}

# canonical unit -> (kind, factor to base). weight base kg, volume base l, count base pieces
UNITS: dict[str, tuple[str, float]] = {}


def _units(kind: str, factor: float, words: str) -> None:
    for w in words.split():
        UNITS[w] = (kind, factor)


_units("weight", 0.001, "gram grams gm gms g gramm ग्राम")
_units("weight", 1.0, "kilo kilos kg kgs kilogram kilograms किलो किलोग्राम")
_units("volume", 1.0, "litre liter litres liters ltr lt l लीटर")
_units("volume", 0.001, "ml millilitre milliliter मिली")
_units("count", 12.0, "dozen darjan dozan दर्जन")
_units("count", 1.0, "packet packets pack packs pkt pkts pc pcs piece pieces nag bag bags bottle "
       "bottles botal dabba dabbe box tin jar sachet carton cartons पैकेट बैग बोतल डब्बा नग पीस")

RUPEE_WORDS = {"rupaye", "rupay", "rupee", "rupees", "rupiya", "rupiye", "rupya", "rs",
               "रुपये", "रुपए", "रुपया", "रूपये", "रुपय"}
CONNECTORS = {"ka", "ki", "ke", "ko", "का", "की", "के", "को"}
STOP_WORDS = {
    "aur", "and", "or", "bhi", "bhaiya", "bhai", "bhaiyya", "uncle", "aunty", "sir", "didi",
    "mujhe", "humko", "hume", "hamko", "chahiye", "chahie", "chahiyen", "dena", "dijiye",
    "dijie", "diji", "karo", "kijiye", "please", "plz", "wala", "wali", "wale", "sirf", "bas",
    "total", "kitna", "hua", "hai", "of", "the", "a", "an", "also", "mein", "me", "se", "wo",
    "woh", "ye", "yeh", "jara", "zara", "thoda", "aap", "dukan", "ji", "jee", "lena", "lo",
    "dedo", "denge", "hoga", "chaiye", "भैया", "भाई", "और", "भी", "चाहिए", "दीजिए", "दे", "देना",
    "मुझे", "में", "से", "जी", "बस", "है",
}
VERB_DE = {"de", "dena", "dijiye"}

CHECKOUT_PHRASES = ("kitna hua", "kitne hue", "total batao", "bill banao", "bill bana do",
                    "bas itna", "bas itna hi", "bas ho gaya", "hisaab", "total kitna",
                    "बस कितना हुआ", "कितना हुआ", "बिल बनाओ", "बस इतना")


def is_checkout_phrase(text: str) -> bool:
    """True for 'bas, kitna hua' / 'total' style closers."""
    t = normalize(text)
    return any(normalize(p) in t for p in CHECKOUT_PHRASES) or t in ("total", "bas", "bill")


# ---------------------------------------------------------------------------
# tokens and quantity expressions
# ---------------------------------------------------------------------------


@dataclass
class Tok:
    kind: str  # num | mult | frac | pre | unit | rupee | stop | prod | unk
    val: object = None
    raw: str = ""
    score: float = 100.0


@dataclass
class Qty:
    """A spoken quantity. `kind`: weight (kg) | volume (l) | count (pieces) | bare | amount (Rs)."""

    value: float
    kind: str
    unit: Optional[str] = None
    raw: str = ""
    consumed: bool = False


@dataclass
class Elem:
    kind: str  # Q | P | U
    qty: Optional[Qty] = None
    products: list[Product] = field(default_factory=list)
    score: float = 100.0
    raw: str = ""
    pos: int = 0


@dataclass
class ParseOutcome:
    lines: list[CartLine]
    unmatched: list[dict]
    normalized: str


_DIGIT = re.compile(r"^(\d+(?:\.\d+)?)([a-z]+)?$")


def _classify(word: str) -> Tok:
    """Classify one normalised word (not part of a product alias)."""
    if word in NUMBER_WORDS:
        return Tok("num", NUMBER_WORDS[word], word)
    if word in MULTIPLIERS:
        return Tok("mult", MULTIPLIERS[word], word)
    if word in FRACTIONS:
        return Tok("frac", FRACTIONS[word], word)
    if word in PREFIXES:
        return Tok("pre", PREFIXES[word], word)
    if word in UNITS:
        return Tok("unit", UNITS[word], word)
    if word in RUPEE_WORDS:
        return Tok("rupee", None, word)
    if word in STOP_WORDS or word in CONNECTORS:
        return Tok("stop", None, word)
    m = _DIGIT.match(word)
    if m:
        unit = m.group(2)
        if unit is None:
            return Tok("num", float(m.group(1)), word)
        if unit in UNITS:  # "250g", "2kg"
            return Tok("numunit", (float(m.group(1)), UNITS[unit]), word)
        if unit in RUPEE_WORDS:
            return Tok("numrupee", float(m.group(1)), word)
    return Tok("unk", None, word)


def _tokenize(words: list[str], index: CatalogIndex) -> list[Tok]:
    """Product phrases first (longest alias wins), then everything else."""
    toks: list[Tok] = []
    i = 0
    n = len(words)
    while i < n:
        matched = False
        for span in range(min(index.max_alias_words, n - i), 0, -1):
            phrase = " ".join(words[i:i + span])
            prods = index.alias_map.get(phrase)
            if not prods:
                continue
            # a lone word that is also a number/unit/stop word is not a product mention
            if span == 1 and _classify(phrase).kind not in ("unk",):
                continue
            toks.append(Tok("prod", prods, phrase))
            i += span
            matched = True
            break
        if matched:
            continue
        w = words[i]
        t = _classify(w)
        if t.kind == "num" and w == "do" and i > 0 and words[i - 1] in VERB_DE:
            t = Tok("stop", None, w)  # "de do" = give, not two
        toks.append(t)
        i += 1
    return _fuzzy_unknowns(toks, index)


def _fuzzy_unknowns(toks: list[Tok], index: CatalogIndex) -> list[Tok]:
    """Try to rescue unknown words (STT misspellings) as products; bigrams first."""
    out: list[Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.kind == "unk":
            if i + 1 < len(toks) and toks[i + 1].kind == "unk":
                hit = index.match_all(f"{t.raw} {toks[i + 1].raw}")
                if hit:
                    out.append(Tok("prod", [p for p, _ in hit], f"{t.raw} {toks[i + 1].raw}", hit[0][1]))
                    i += 2
                    continue
            hit = index.match_all(t.raw)
            if hit:
                out.append(Tok("prod", [p for p, _ in hit], t.raw, hit[0][1]))
                i += 1
                continue
        out.append(t)
        i += 1
    return out


def _read_qty(toks: list[Tok], i: int) -> tuple[Optional[Qty], int]:
    """Read one quantity expression starting at toks[i]; returns (Qty, next index)."""
    n = len(toks)
    t = toks[i]
    j = i
    value: Optional[float] = None
    unit_from_token: Optional[tuple[str, float]] = None

    if t.kind == "numunit":
        value, unit_from_token = t.val[0], t.val[1]  # type: ignore[index]
        j += 1
    elif t.kind == "numrupee":
        return Qty(float(t.val), "amount", raw=t.raw), i + 1  # type: ignore[arg-type]
    elif t.kind == "pre":
        add = float(t.val)  # type: ignore[arg-type]
        j += 1
        if j < n and toks[j].kind == "num":
            value = float(toks[j].val) + add  # type: ignore[arg-type]
            j += 1
        else:
            value = 1.0 + add
    elif t.kind in ("num", "frac"):
        value = float(t.val)  # type: ignore[arg-type]
        j += 1
    elif t.kind == "mult":
        value = float(t.val)  # type: ignore[arg-type]
        j += 1
    else:
        return None, i

    if t.kind != "mult" and unit_from_token is None:
        multiplied = False
        while j < n and toks[j].kind == "mult":
            value *= float(toks[j].val)  # type: ignore[arg-type]
            j += 1
            multiplied = True
        # "do sau pachaas gram": hundreds followed by a tens number and a unit
        if (multiplied and j + 1 < n and toks[j].kind == "num" and float(toks[j].val) < 100  # type: ignore[arg-type]
                and toks[j + 1].kind in ("unit", "rupee")):
            value += float(toks[j].val)  # type: ignore[arg-type]
            j += 1

    raw = " ".join(x.raw for x in toks[i:j])
    if unit_from_token is not None:
        kind, factor = unit_from_token
        return Qty(value * factor, kind, raw=raw), j
    if j < n and toks[j].kind == "unit":
        kind, factor = toks[j].val  # type: ignore[misc]
        raw += " " + toks[j].raw
        return Qty(value * factor, kind, unit=toks[j].raw, raw=raw), j + 1
    if j < n and toks[j].kind == "rupee":
        return Qty(value, "amount", raw=raw + " " + toks[j].raw), j + 1
    return Qty(value, "bare", raw=raw), j


def _elements(toks: list[Tok]) -> list[Elem]:
    elems: list[Elem] = []
    i = 0
    unk_run: list[str] = []

    def flush_unknown() -> None:
        if unk_run:
            elems.append(Elem("U", raw=" ".join(unk_run), pos=len(elems)))
            unk_run.clear()

    while i < len(toks):
        t = toks[i]
        if t.kind == "prod":
            flush_unknown()
            elems.append(Elem("P", products=list(t.val), score=t.score, raw=t.raw, pos=len(elems)))  # type: ignore[arg-type]
            i += 1
        elif t.kind in ("num", "mult", "frac", "pre", "numunit", "numrupee"):
            flush_unknown()
            q, j = _read_qty(toks, i)
            if q is None:
                i += 1
                continue
            elems.append(Elem("Q", qty=q, raw=q.raw, pos=len(elems)))
            i = j
        elif t.kind == "unk":
            unk_run.append(t.raw)
            i += 1
        else:  # stop / orphan unit / rupee
            if t.kind == "unit":
                # an orphan unit ("kilo") after a bare number is handled in _read_qty
                pass
            i += 1
    flush_unknown()
    return elems


# ---------------------------------------------------------------------------
# binding quantities to products
# ---------------------------------------------------------------------------


def _neighbour_qty(elems: list[Elem], pos: int, step: int) -> Optional[Qty]:
    """Nearest unconsumed Q in direction `step`, skipping unknown-word elements."""
    k = pos + step
    while 0 <= k < len(elems):
        e = elems[k]
        if e.kind == "U":
            k += step
            continue
        if e.kind == "Q" and e.qty is not None and not e.qty.consumed:
            return e.qty
        return None
    return None


def _spoken_kind(q: Optional[Qty]) -> str:
    return q.kind if q is not None else "none"


def choose_product(cands: list[Product], q: Optional[Qty]) -> Product:
    """Pick among products sharing an alias using the spoken unit.
    Weight/volume -> loose product; pieces/bag/packet or nothing -> packed product."""
    if len(cands) == 1:
        return cands[0]
    kind = _spoken_kind(q)
    loose = [p for p in cands if p.sell_mode == "loose"]
    packed = [p for p in cands if p.sell_mode != "loose"]
    if kind in ("weight", "volume", "amount") and loose:
        return loose[0]
    if kind in ("count", "bare", "none") and packed:
        return packed[0]
    return cands[0]


def weigh_instruction(qty: float, base_unit: str) -> str:
    """'450 gram tolo' / '1 kilo 250 gram tolo' / '300 ml naap lo'."""
    if base_unit == "kg":
        grams = int(round(qty * 1000))
        if grams < 1000:
            return f"{grams} gram tolo"
        kilos, rem = divmod(grams, 1000)
        return f"{kilos} kilo tolo" if rem == 0 else f"{kilos} kilo {rem} gram tolo"
    if base_unit == "l":
        ml = int(round(qty * 1000))
        if ml < 1000:
            return f"{ml} ml naap lo"
        litres, rem = divmod(ml, 1000)
        return f"{litres} litre naap lo" if rem == 0 else f"{litres} litre {rem} ml naap lo"
    return ""


def amount_to_quantity(amount_rupees: float, price_per_base: float) -> float:
    """Base units (kg or litre) that Rs `amount_rupees` buys, rounded DOWN to 10 g/10 ml."""
    if price_per_base <= 0:
        return 0.0
    return math.floor(amount_rupees * 100 / price_per_base + 1e-6) / 100


def build_line(product: Product, q: Optional[Qty], raw: str, score: float) -> CartLine:
    """Turn a product plus an optional spoken quantity into a priced CartLine."""
    flags: list[str] = []
    loose = product.sell_mode == "loose"
    price = product.price
    amount_rupees: Optional[float] = None
    weigh: Optional[str] = None
    line_total: Optional[float] = None
    kind = _spoken_kind(q)
    base = product.base_unit or "pc"

    if q is None:
        qty = 1.0
        flags.append("default_qty")
    elif kind == "amount":
        if loose:
            qty = amount_to_quantity(q.value, price)
            amount_rupees = q.value
            line_total = round(q.value, 2)
            weigh = weigh_instruction(qty, base)
        else:
            qty = float(max(1, math.floor(q.value / price + 1e-6))) if price > 0 else 1.0
            flags.append("amount_rounded_to_whole_units")
    elif loose:
        if kind == "weight":
            qty = q.value
            if base != "kg":
                flags.append("unit_mismatch")
        elif kind == "volume":
            qty = q.value
            if base != "l":
                flags.append("unit_mismatch")
        else:
            qty = q.value
            flags.append("assumed_base_unit")
        if base in ("kg", "l"):
            weigh = weigh_instruction(qty, base)
    else:
        qty = q.value
        if kind in ("weight", "volume"):
            flags.append("unit_mismatch")
            qty = max(1.0, float(round(qty)))

    qty = round(qty, 3)
    if line_total is None:
        line_total = round(qty * price, 2)
    unit = ("kg" if base == "kg" else "litre") if loose and base in ("kg", "l") else (product.unit or "pc")
    return CartLine(
        product_id=int(product.id), name=str(product.name), name_hi=str(product.name_hi or ""),
        qty=qty, unit=unit, sell_mode="loose" if loose else "unit", base_unit=base,
        unit_price=price, line_total=line_total, gst_rate=float(product.gst_rate or 0.0),
        amount_rupees=amount_rupees, weigh_instruction=weigh, flags=flags, raw=raw,
        confidence=round(score / 100.0, 2),
    )


def _merge(lines: list[CartLine]) -> list[CartLine]:
    merged: dict[int, CartLine] = {}
    order: list[CartLine] = []
    for ln in lines:
        prev = merged.get(ln.product_id or -1)
        if prev is not None and ln.amount_rupees is None and prev.amount_rupees is None:
            prev.qty = round(prev.qty + ln.qty, 3)
            prev.line_total = round(prev.qty * prev.unit_price, 2)
            continue
        if ln.product_id is not None:
            merged.setdefault(ln.product_id, ln)
        order.append(ln)
    return order


def parse_order_full(text: str, db: Optional[Session] = None, index: Optional[CatalogIndex] = None
                     ) -> ParseOutcome:
    """Parse one utterance into cart lines plus unmatched (not in catalog) mentions."""
    if index is None:
        if db is None:
            raise ValueError("parse_order needs a db session or a CatalogIndex")
        index = load_index(db)
    norm = normalize(text)
    if not norm:
        return ParseOutcome([], [], norm)
    toks = _tokenize(norm.split(), index)
    elems = _elements(toks)

    first = next((e for e in elems if e.kind in ("Q", "P")), None)
    qty_after_style = first is not None and first.kind == "P"

    lines: list[CartLine] = []
    for e in elems:
        if e.kind != "P":
            continue
        left = _neighbour_qty(elems, e.pos, -1)
        right = _neighbour_qty(elems, e.pos, +1)
        chosen = (right or left) if qty_after_style else (left or right)
        product = choose_product(e.products, chosen)
        if chosen is not None:
            chosen.consumed = True
        lines.append(build_line(product, chosen, e.raw, e.score))

    unmatched: list[dict] = []
    for e in elems:
        if e.kind != "Q" or e.qty is None or e.qty.consumed:
            continue
        name = ""
        for step in (+1, -1):
            k = e.pos + step
            if 0 <= k < len(elems) and elems[k].kind == "U":
                name = elems[k].raw
                break
        if name and e.qty.kind != "amount":
            unmatched.append({"name": name, "qty": e.qty.value, "raw": f"{e.qty.raw} {name}".strip()})
    return ParseOutcome(_merge(lines), unmatched, norm)


def parse_order(text: str, db: Session) -> list[CartLine]:
    """Parse a spoken order into cart lines (catalog matches only)."""
    return parse_order_full(text, db).lines
