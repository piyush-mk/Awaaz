"""Voice persona: variants, anti-repeat, length caps, TTS text normalisation and pace. Pure, no network."""
import re
from collections import Counter

import pytest

from services import phrases, voice_style as vs

# facts rich enough to render every variant of every kind
FACTS = dict(
    items="2 Maggi, 1 Surf Excel", total=294, due=100, amount=249, balance=1350, bal=1350, rest=45,
    name="Maggi", qty_text="450 gram", label="₹20 ki Cheeni", verb="Tol", customer="Verma ji", qty="8",
    more=3, what="Bill ₹249, 3 items", parts="₹300 cash, ₹200 Paytm", unit="kg", old_price=44, new_price=48,
    price=48, khata="", store="Ramesh General Store", count=7)
MONEY_KINDS = {"items_added", "total_now", "confirm_needed", "checkout_ready", "checkout_partial",
               "bill_done", "payment_received", "payment_partial", "udhaar_proposed", "udhaar_over_limit",
               "udhaar_confirmed", "khata_payment", "khata_payment_done", "price_proposed", "price_done",
               "split_summary", "split_parts", "split_mismatch", "voice_receipt", "voice_receipt_short"}
ERROR_KINDS = {"nothing_understood", "nothing_heard", "missed_sale", "payment_failed", "split_mismatch",
               "undo_after_bill", "ask_customer", "ask_amount", "price_ask", "restock_ask"}


@pytest.fixture(autouse=True)
def fresh_memory():
    vs.reset_memory()
    yield
    vs.reset_memory()


@pytest.mark.parametrize("kind", [k for k in vs.KINDS])
def test_every_kind_has_distinct_variants(kind):
    got = vs.variants(kind, **FACTS)
    assert len(got) >= 2, kind
    assert len(set(got)) == len(got)  # variants really differ


def test_core_situations_have_three_to_five_plain_variants():
    for kind in ("items_added", "loose_item", "item_removed", "qty_changed", "undo_done", "nothing_understood",
                 "missed_sale", "checkout_ready", "payment_received", "low_stock", "udhaar_proposed",
                 "udhaar_confirmed", "khata_payment", "confirm_needed", "action_cancelled", "generic_ok"):
        n = len(vs._BANK[vs._canon(kind)][0])
        assert 3 <= n <= 8, (kind, n)


def test_all_kinds_the_brief_asks_for_exist():
    for kind in ("items_added", "loose_item", "item_removed", "qty_changed", "undo_done", "nothing_understood",
                 "not_in_catalog", "missed_sale", "checkout_ready", "payment_received", "low_stock",
                 "udhaar_proposed", "udhaar_confirmed", "khata_payment", "confirm_needed", "action_cancelled",
                 "generic_ok"):
        assert vs.line(kind, seed=1, **FACTS).text


def test_lines_are_short():
    for kind in vs.KINDS:
        if kind.startswith("voice_receipt"):
            continue
        for text in vs.variants(kind, **FACTS):
            assert len(text) <= vs.MAX_CHARS, (kind, text)
        assert len(vs.line(kind, seed=3, **FACTS).text) <= vs.MAX_CHARS


def test_seed_is_deterministic_and_varies():
    a = [vs.line("items_added", seed=s, **FACTS).text for s in range(40)]
    b = [vs.line("items_added", seed=s, **FACTS).text for s in range(40)]
    assert a == b
    assert len(set(a)) >= 3


def test_no_repeat_in_a_row_per_session():
    for kind in ("items_added", "payment_received", "nothing_understood", "generic_ok", "item_removed",
                 "checkout_ready", "missed_sale"):
        seen = [vs.line(kind, session="s1", **FACTS).text for _ in range(60)]
        assert all(x != y for x, y in zip(seen, seen[1:])), kind


def test_sessions_do_not_share_memory():
    vs.line("generic_ok", session="a")
    firsts = {vs.line("generic_ok", session=f"fresh-{i}").text for i in range(30)}
    assert len(firsts) > 1


def test_humour_is_rare_and_never_on_money_or_errors():
    for kind in MONEY_KINDS | ERROR_KINDS:
        assert vs._BANK[vs._canon(kind)][1] == [], f"{kind} must not be witty"
    witty = set(vs.variants("item_removed", name="Maggi")[-1:])
    hits = sum(vs.line("item_removed", session=f"w{i}", name="Maggi").text in witty for i in range(600))
    assert 0 < hits < 600 * 0.3  # about one in five at most
    # never two witty lines back to back in one session
    seq = [vs.line("item_removed", session="one", name="Maggi").text in witty for _ in range(300)]
    assert not any(x and y for x, y in zip(seq, seq[1:]))


def test_loose_line_matches_the_counter_style():
    got = vs.line("loose_item", seed=0, label="₹20 ki Cheeni", name="Cheeni", qty_text="450 gram", verb="Tol")
    assert "450 gram" in got.text and "tol" in got.text.lower()
    assert any(t == "₹20 ki Cheeni, 450 gram. Tol dijiye." for t in vs.variants(
        "loose_item", label="₹20 ki Cheeni", name="Cheeni", qty_text="450 gram", verb="Tol"))


def test_missing_facts_skip_variants_instead_of_crashing():
    assert vs.line("items_added", seed=1, total=50).text  # no `items`: the item-less variants
    with pytest.raises(ValueError):
        vs.line("missed_sale", seed=1)  # needs a name
    with pytest.raises(ValueError):
        vs.line("no_such_kind")


def test_alias_kinds():
    assert vs.line("not_in_catalog", seed=1, name="Kurkure").kind == "missed_sale"


def test_combine_keeps_slowest_pace_with_floor():
    a, b = vs.line("generic_ok", seed=1), vs.line("udhaar_over_limit", seed=1, customer="X", amount=5)
    c = vs.combine([a, b])
    assert c.pace == 0.93 and a.text in c.text and b.text in c.text


# --- TTS text ---------------------------------------------------------------------------------------


def test_amounts_become_rupaye_with_no_symbol():
    assert vs.prepare_for_tts("Total ₹249.") == "Total 249 rupaye."
    assert vs.prepare_for_tts("Rs. 50 diye") == "50 rupaye diye"
    assert vs.prepare_for_tts("₹249.50 hua") == "249 rupaye 50 paise hua"
    assert "₹" not in vs.prepare_for_tts("₹5, ₹10 aur ₹15")


def test_five_digit_numbers_get_indian_commas():
    assert vs.prepare_for_tts("₹12,345") == "12,345 rupaye"
    assert vs.prepare_for_tts("₹1234567") == "12,34,567 rupaye"
    assert vs.prepare_for_tts("₹9999") == "9999 rupaye"  # four digits are read fine
    assert vs.prepare_for_tts("bill 123456 ka") == "bill 1,23,456 ka"


def test_units_and_symbols_become_words():
    out = vs.prepare_for_tts("2 kg chawal, 450 g cheeni, 1 L tel, 300 ml doodh, 12% GST", pronunciation=False)
    assert "2 kilo chawal" in out and "450 gram cheeni" in out and "1 litre tel" in out
    assert "300 millilitre doodh" in out and "12 percent GST" in out
    assert vs.prepare_for_tts("0.5 kg", pronunciation=False) == "aadha kilo"
    assert vs.prepare_for_tts("1.5 L", pronunciation=False) == "dedh litre"


def test_emoji_dashes_and_odd_symbols_are_removed():
    out = vs.prepare_for_tts("Done ✅ — ho gaya \U0001F600 (ji) #1 A&B * x=y")
    assert not re.search("[✅\U0001F600—#*=&()]", out)
    assert "aur" in out and "ji" in out
    assert "  " not in out and not out.startswith(",")


def test_brand_pronunciation_table_and_flag():
    on = vs.prepare_for_tts("2 Surf Excel aur Parle-G, Colgate", pronunciation=True)
    assert "सर्फ एक्सेल" in on and "पारले जी" in on and "कोलगेट" in on
    off = vs.prepare_for_tts("2 Surf Excel aur Parle-G, Colgate", pronunciation=False)
    assert off == "2 Surf Excel aur Parle-G, Colgate"
    for brand in ("Dettol", "Aashirvaad", "Patanjali", "Bournvita"):
        assert vs.prepare_for_tts(brand, pronunciation=True) != brand
    assert vs.prepare_for_tts("Maggilicious", pronunciation=True) == "Maggilicious"


def test_prepare_is_idempotent_for_every_variant():
    for kind in vs.KINDS:
        for text in vs.variants(kind, **FACTS):
            once = vs.prepare_for_tts(text)
            assert vs.prepare_for_tts(once) == once, (kind, text)
            assert "₹" not in once and "—" not in once


# --- pace ---------------------------------------------------------------------------------------------


def test_pace_by_register():
    assert vs.pace_for("generic_ok") >= 1.05 - 1e-9
    assert vs.pace_for("item_removed") == 1.05
    assert vs.pace_for("nothing_understood") == 1.0
    for kind in ("checkout_ready", "payment_received", "udhaar_proposed", "low_stock"):
        assert 0.93 <= vs.pace_for(kind) <= 0.97
    for kind in vs.KINDS:
        assert 0.9 <= vs.pace_for(kind) <= 1.1
    assert vs.pace_for(None, "Ji.") == 1.05
    assert vs.pace_for(None, "Total ₹294 hua, QR scan kijiye ji.") == 0.96
    assert vs.line("checkout_ready", seed=1, total=294).pace == vs.pace_for("checkout_ready")


# --- phrase bank ------------------------------------------------------------------------------------------


def test_phrase_bank_shape():
    assert len(phrases.PHRASES) >= 24
    for pid in ("ack_ji", "ack_haan_ji", "ack_ek_second", "done_ho_gaya", "unclear_dobara"):
        assert pid in phrases.PHRASES
    assert {p.kind for p in phrases.PHRASES.values()} >= {"ack", "done", "unclear", "light"}
    for p in phrases.PHRASES.values():
        assert len(p.text) <= 40 and "—" not in p.text and 0.95 <= p.pace <= 1.1
    assert len({p.text for p in phrases.PHRASES.values()}) == len(phrases.PHRASES)


def test_acks_point_at_real_phrases_and_vary():
    for situation in phrases._SITUATIONS:
        assert phrases.ack_for(situation, seed=1) in phrases.PHRASES
    assert phrases.ack_for("nope") is None
    picks = [phrases.ack_for("added", session="s") for _ in range(40)]
    assert all(a != b for a, b in zip(picks, picks[1:]))
    assert len(Counter(picks)) >= 3
