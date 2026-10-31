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


@pytest.mark.parametrize("transcript,expected", [
    # spellings Sarvam really returned, one of which billed 15 Maggi and 1 Colgate
    ("Baarah Maggi, pandrah Colgate.", {"Maggi": 12, "Colgate": 15}),
    ("Tera Maggi, solah Colgate.", {"Maggi": 13, "Colgate": 16}),
    ("Das packet Maggi aur paanch Colgate.", {"Maggi": 10, "Colgate": 5}),
    ("Dus packet Maggi aur paanch Colgate.", {"Maggi": 10, "Colgate": 5}),
    ("Taas packet Maggi aur paanch Colgate.", {"Maggi": 10, "Colgate": 5}),
    ("दास पैकेट मैगी और पाँच कोलगेट।", {"Maggi": 10, "Colgate": 5}),
    ("टास पैकेट Maggi और पाँच Colgate।", {"Maggi": 10, "Colgate": 5}),
])
def test_spellings_sarvam_returns_for_numbers(db, transcript, expected):
    out = parse_order_full(transcript, db)
    assert {ln.name: ln.qty for ln in out.lines} == expected
    assert out.explained


@pytest.mark.parametrize("transcript,expected", [
    ("zzqx packet Maggi aur paanch Colgate", {"Maggi": 1, "Colgate": 5}),  # the misheard number is not Colgate's
    ("Do Maggi zzqx Surf Excel chaar Colgate", {"Maggi": 2, "Surf Excel": 1, "Colgate": 4}),
    ("do maggi surf excel teen colgate", {"Maggi": 2, "Surf Excel": 1, "Colgate": 3}),
    ("zzqx maggi paanch", {"Maggi": 5}),
    ("zzqx maggi paanch colgate teen", {"Maggi": 5, "Colgate": 3}),  # number-after sentence
    ("maggi paanch colgate teen", {"Maggi": 5, "Colgate": 3}),
    ("do maggi, colgate paanch, surf excel teen", {"Maggi": 2, "Colgate": 5, "Surf Excel": 3}),
])
def test_a_number_does_not_slide_onto_the_wrong_item(db, transcript, expected):
    assert {ln.name: ln.qty for ln in parse_order_full(transcript, db).lines} == expected


def test_one_item_heard_in_two_pieces_is_not_counted_twice(db):
    out = parse_order_full("Do Tata नामक एक Vim Bar.", db)
    assert {ln.name: ln.qty for ln in out.lines} == {"Tata Salt": 2, "Vim Bar": 1}


@pytest.mark.parametrize("transcript", ["Bhaiya ek Surf Excel aur do Colgate de do.", "भैया एक सर्फ एक्सेल और दो कोलगेट दे दो।"])
def test_de_do_means_give_and_needs_no_llm(db, transcript):
    out = parse_order_full(transcript, db)
    assert {ln.name: ln.qty for ln in out.lines} == {"Surf Excel": 1, "Colgate": 2}
    assert out.explained
