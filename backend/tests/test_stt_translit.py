"""Speech-recognition output the parser must fully understand, so plain orders take the fast path.

Sarvam returns Hindi in Devanagari by default ("टू मैगी, एक सर्फ एक्सेल और चार कोलगेट।"), where English
number words are spelled phonetically (टू = two). With mode=translit it returns Roman-letter Hinglish.
Both must give the same cart and be "explained" (no LLM needed).
"""
import pytest

from config import settings
from services.quantity import parse_order_full

EXPECTED = {"Maggi": 2, "Surf Excel": 1, "Colgate": 4}


@pytest.mark.parametrize("transcript", [
    "Do Maggi, ek Surf Excel aur chaar Colgate.",     # saaras:v4 mode=translit
    "Two Maggi, ek Surf Excel aur chaar Colgate.",    # saaras:v3 mode=translit
    "2 Maggi, 1 Surf Excel और 4 Colgate",             # mode=codemix
    "टू मैगी, एक सर्फ एक्सेल और चार कोलगेट।",           # default Devanagari output
    "दो मैगी, एक सर्फ एक्सेल और चार कोलगेट।",
])
def test_recognition_outputs_give_the_same_explained_cart(db, transcript):
    out = parse_order_full(transcript, db)
    assert {ln.name: ln.qty for ln in out.lines} == EXPECTED
    assert out.explained, f"would fall back to the slow LLM path: {out}"


@pytest.mark.parametrize("word,qty", [("वन", 1), ("टू", 2), ("थ्री", 3), ("फोर", 4), ("फाइव", 5),
                                      ("सिक्स", 6), ("सेवन", 7), ("एट", 8), ("नाइन", 9), ("टेन", 10)])
def test_devanagari_english_numbers(db, word, qty):
    (line,) = parse_order_full(f"{word} मैगी", db).lines
    assert line.name == "Maggi" and line.qty == qty


def test_stt_defaults_to_translit():
    assert settings.sarvam_stt_mode == "translit"
