"""Catalog lookup: alias index, fuzzy product match, customer match, STT keyterms.

The alias index maps every normalised spoken name (English, Hinglish, Devanagari)
to one or more products. Several products may share an alias (bare "atta" is both
the loose atta and the packed bag); callers disambiguate by spoken unit, see
`services/quantity.py`.

Moved and extended from the old routers/voice.py (`normalize`, alias building).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from models import Customer, Product

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_SIZE_TOKEN = re.compile(r"^\d+(?:\.\d+)?(?:g|gm|kg|ml|l|ltr)$")
HONORIFICS = {"ji", "jee", "bhaiya", "bhai", "uncle", "aunty", "auntie", "sahab", "sahib",
              "madam", "sir", "mr", "mrs", "ms", "didi", "भैया", "जी", "अंकल", "आंटी", "साहब"}

FUZZY_PRODUCT_THRESHOLD = 84
FUZZY_CUSTOMER_THRESHOLD = 72


def normalize(text: str) -> str:
    """Lowercase, Devanagari digits to ASCII, punctuation and hyphens to spaces.
    The rupee sign and 'Rs' prefixes become the word 'rupaye' so amounts survive."""
    t = (text or "").translate(DEVANAGARI_DIGITS).lower().strip()
    t = re.sub(r"₹\s*(\d+(?:\.\d+)?)", r" \1 rupaye ", t)
    t = re.sub(r"\brs\.?\s*(\d+(?:\.\d+)?)", r" \1 rupaye ", t)
    t = t.replace("₹", " rupaye ")
    t = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", t)  # 1,200 -> 1200
    t = re.sub(r"[^\w\sऀ-ॿ.]", " ", t)
    t = t.replace("_", " ")
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# --- rough Devanagari -> Latin transliteration (for cross-script fuzzy match) ---

_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j",
    "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t",
    "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "f", "ब": "b", "भ": "bh",
    "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s",
    "ह": "h", "ड़": "d", "ढ़": "dh", "ज़": "j", "फ़": "f", "क़": "k",
}
_VOWELS = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai",
           "ओ": "o", "औ": "au", "ऑ": "o", "ऋ": "ri"}
_MATRAS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o",
           "ौ": "au", "ॉ": "o", "ृ": "ri"}
_VIRAMA = "्"
_NASAL = {"ं": "n", "ँ": "n", "ः": "h"}
_NUKTA = "़"


def has_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)


def transliterate_devanagari(text: str) -> str:
    """Best-effort romanisation with simple schwa deletion. Latin text is returned as is."""
    text = text.replace("ड" + _NUKTA, "ड़").replace("ढ" + _NUKTA, "ढ़")
    out: list[str] = []
    for word in text.split():
        if not has_devanagari(word):
            out.append(word)
            continue
        syll: list[tuple[str, bool]] = []  # (romanised syllable, bare consonant with inherent a)
        i = 0
        while i < len(word):
            ch = word[i]
            if ch in _CONS:
                base = _CONS[ch]
                nxt = word[i + 1] if i + 1 < len(word) else ""
                if nxt == _NUKTA:
                    i += 1
                    nxt = word[i + 1] if i + 1 < len(word) else ""
                if nxt == _VIRAMA:
                    syll.append((base, False))
                    i += 2
                    continue
                if nxt in _MATRAS:
                    syll.append((base + _MATRAS[nxt], False))
                    i += 2
                    continue
                syll.append((base + "a", True))
            elif ch in _VOWELS:
                syll.append((_VOWELS[ch], False))
            elif ch in _NASAL and syll:
                syll[-1] = (syll[-1][0] + _NASAL[ch], syll[-1][1])
            elif ch.isalnum() and ord(ch) < 0x0900:
                syll.append((ch, False))
            i += 1
        last = len(syll) - 1
        pieces = []
        for idx, (s, bare) in enumerate(syll):
            if bare and (idx == last or (0 < idx < last and not syll[idx - 1][1])):
                s = s[:-1]
            pieces.append(s)
        out.append("".join(pieces))
    return " ".join(out)


def phonetic_key(text: str) -> str:
    """Collapse spelling variants so Latin and transliterated Devanagari compare close."""
    t = transliterate_devanagari(normalize(text))
    for src, dst in (("ph", "f"), ("w", "v"), ("z", "j"), ("q", "k"), ("c", "k"), ("x", "ks"),
                     ("ee", "i"), ("oo", "u"), ("aa", "a"), ("ai", "a"), ("kh", "k"), ("gh", "g"),
                     ("chh", "ch"), ("sh", "s")):
        t = t.replace(src, dst)
    t = re.sub(r"(.)\1+", r"\1", t)
    return t.replace(" ", "")


# --- alias index ---


def _strip_sizes(name: str) -> str:
    return " ".join(w for w in name.split() if not _SIZE_TOKEN.match(w))


def product_aliases(product: Product) -> set[str]:
    """All normalised spoken names for a product (name, name_hi, aliases, size-stripped)."""
    raw: list[str] = [str(product.name or ""), str(product.name_hi or "")]
    raw.extend(str(a) for a in (product.aliases or []))
    out: set[str] = set()
    for item in raw:
        n = normalize(item)
        if not n:
            continue
        out.add(n)
        stripped = _strip_sizes(n)
        if stripped:
            out.add(stripped)
    return out


@dataclass
class CatalogIndex:
    """In-memory alias index over the active catalog."""

    products: list[Product]
    alias_map: dict[str, list[Product]] = field(default_factory=dict)
    max_alias_words: int = 1
    _fuzzy_keys: dict[str, str] = field(default_factory=dict)  # key -> alias (latin side)
    _phonetic_keys: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, products: Iterable[Product]) -> "CatalogIndex":
        plist = list(products)
        idx = cls(products=plist)
        for p in sorted(plist, key=lambda x: int(x.id or 0)):
            for alias in product_aliases(p):
                bucket = idx.alias_map.setdefault(alias, [])
                if p not in bucket:
                    bucket.append(p)
                idx.max_alias_words = max(idx.max_alias_words, len(alias.split()))
        for alias in idx.alias_map:
            if len(alias) >= 4 and not has_devanagari(alias):
                idx._fuzzy_keys[alias] = alias
            pk = phonetic_key(alias)
            if len(pk) >= 4:
                idx._phonetic_keys.setdefault(pk, alias)
        return idx

    def exact(self, phrase: str) -> list[Product]:
        """Products whose alias equals the (normalised) phrase."""
        return list(self.alias_map.get(normalize(phrase), []))

    def match(self, phrase: str, threshold: int = FUZZY_PRODUCT_THRESHOLD
              ) -> tuple[Optional[Product], float]:
        """Best product for a spoken phrase: exact alias, then fuzzy, then phonetic.
        Returns (product, score 0-100); (None, best_score) when below threshold."""
        candidates = self.match_all(phrase, threshold)
        if not candidates:
            return None, 0.0
        return candidates[0]

    def find_in_phrase(self, phrase: str, threshold: int = FUZZY_PRODUCT_THRESHOLD
                       ) -> tuple[Optional[Product], float]:
        """Match a longer product description ("Parle-G biscuits 56g", "Surf Excel Easy
        Wash") by its longest known alias inside it; falls back to fuzzy `match`."""
        words = normalize(phrase).split()
        for span in range(min(self.max_alias_words, len(words)), 0, -1):
            for i in range(len(words) - span + 1):
                prods = self.alias_map.get(" ".join(words[i:i + span]))
                if prods:
                    return prods[0], 100.0 if span > 1 else 95.0
        return self.match(phrase, threshold)

    def match_all(self, phrase: str, threshold: int = FUZZY_PRODUCT_THRESHOLD
                  ) -> list[tuple[Product, float]]:
        """All products sharing the best-matching alias, with the score."""
        q = normalize(phrase)
        if not q:
            return []
        exact = self.alias_map.get(q)
        if exact:
            return [(p, 100.0) for p in exact]
        if len(q) >= 4 and self._fuzzy_keys and not has_devanagari(q):
            hit = process.extractOne(q, list(self._fuzzy_keys), scorer=fuzz.ratio,
                                     score_cutoff=threshold)
            if hit:
                return [(p, float(hit[1])) for p in self.alias_map[hit[0]]]
        pk = phonetic_key(q)
        if len(pk) >= 4 and self._phonetic_keys:
            hit = process.extractOne(pk, list(self._phonetic_keys), scorer=fuzz.ratio,
                                     score_cutoff=max(threshold, 85) if not has_devanagari(q) else 78)
            if hit:
                alias = self._phonetic_keys[hit[0]]
                return [(p, float(hit[1])) for p in self.alias_map[alias]]
        return []


def load_index(db: Session) -> CatalogIndex:
    """Build the alias index from active products."""
    products = db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all()
    return CatalogIndex.build(products)


def match_product(db: Session, phrase: str, threshold: int = FUZZY_PRODUCT_THRESHOLD
                  ) -> tuple[Optional[Product], float]:
    """Convenience: fuzzy-match one spoken phrase against the DB catalog."""
    return load_index(db).match(phrase, threshold)


# --- customers ---


def _customer_core(name: str) -> str:
    words = [w for w in normalize(name).split() if w not in HONORIFICS]
    return " ".join(words)


def match_customer(db: Session, spoken: str, threshold: int = FUZZY_CUSTOMER_THRESHOLD
                   ) -> tuple[Optional[Customer], float]:
    """Match a spoken customer name ("Verma ji", "Sharma ji ke") to a Customer.
    Honorifics are ignored on both sides; ties go to the lower id."""
    core = _customer_core(spoken)
    if not core:
        return None, 0.0
    best: Optional[Customer] = None
    best_score = 0.0
    for c in db.query(Customer).order_by(Customer.id).all():
        if (c.name or "").lower().startswith("walk-in"):
            continue
        names = [_customer_core(str(c.name or ""))]
        if c.name_hi:
            names.append(_customer_core(str(c.name_hi)))
        for cand in names:
            if not cand:
                continue
            score = max(fuzz.ratio(core, cand), phonetic_ratio(core, cand))
            first = cand.split()[0]
            if core == first:
                score = max(score, 95.0)
            if score > best_score:
                best, best_score = c, float(score)
    if best is not None and best_score >= threshold:
        return best, best_score
    return None, best_score


def phonetic_ratio(a: str, b: str) -> float:
    return float(fuzz.ratio(phonetic_key(a), phonetic_key(b)))


# --- STT biasing ---


def keyterms(db: Session, limit: int = 50, max_len: int = 64) -> list[str]:
    """Strings to bias speech recognition: product names first (short form), then
    the best-known spoken aliases, then customer names. At most `limit` strings,
    each at most `max_len` characters, de-duplicated case-insensitively."""
    seen: set[str] = set()
    out: list[str] = []

    def add(term: str) -> None:
        term = (term or "").strip()
        key = term.lower()
        if not term or len(term) > max_len or key in seen or len(out) >= limit:
            return
        seen.add(key)
        out.append(term)

    products = db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all()
    for p in products:
        add(_strip_sizes(str(p.name)))
    for p in products:
        for alias in (p.aliases or [])[:2]:
            if not has_devanagari(str(alias)):
                add(str(alias))
    top_customers = db.query(Customer).order_by(Customer.id).limit(10).all()
    for c in top_customers:
        if not (c.name or "").lower().startswith("walk-in"):
            add(str(c.name))
    return out[:limit]
