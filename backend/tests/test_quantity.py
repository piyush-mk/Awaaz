"""Table-driven tests for the Hindi/Hinglish order parser."""
import pytest

from services import quantity
from services.quantity import is_checkout_phrase, parse_order, parse_order_full

# (utterance, {product name: qty})
CASES = [
    # --- the five legacy demo phrases from CLAUDE.md ---
    ("do maggi ek surf excel chaar colgate", {"Maggi": 2, "Surf Excel": 1, "Colgate": 4}),
    ("das packet maggi paanch kilo chawal do litre tel", {"Maggi": 10, "Chawal": 5, "Sarson Tel": 2}),
    ("aashirvaad atta teen bag tata namak chaar packet", {"Aashirvaad Atta 5kg": 3, "Tata Salt": 4}),
    ("paanch dettol sabun teen vim bar do parle g", {"Dettol Soap": 5, "Vim Bar": 3, "Parle-G": 2}),
    ("ek patanjali shahad do colgate", {"Patanjali Honey": 1, "Colgate": 2}),
    # --- new: loose, amount, fractions ---
    ("bhaiya do maggi ek surf aur bees rupaye ki cheeni", {"Maggi": 2, "Surf Excel": 1, "Cheeni": 0.45}),
    ("bees rupaye ki cheeni", {"Cheeni": 0.45}),
    ("aadha kilo cheeni", {"Cheeni": 0.5}),
    ("dhai sau gram dal", {"Dal": 0.25}),
    ("paav kilo chawal", {"Chawal": 0.25}),
    ("dedh kilo atta", {"Atta": 1.5}),
    ("sava kilo cheeni", {"Cheeni": 1.25}),
    ("paune do kilo dal", {"Dal": 1.75}),
    ("saadhe teen kilo chawal", {"Chawal": 3.5}),
    ("ek dozen ande", {"Ande": 12}),
    ("aadha dozen ande", {"Ande": 6}),
    ("do darjan ande", {"Ande": 24}),
    ("500 gram paneer", {"Paneer": 0.5}),
    ("paanch sau gram besan", {"Besan": 0.5}),
    ("ek litre tel", {"Sarson Tel": 1}),
    ("500 ml tel", {"Sarson Tel": 0.5}),
    ("do kilo cheeni teen kilo atta", {"Cheeni": 2, "Atta": 3}),
    ("atta teen bag", {"Aashirvaad Atta 5kg": 3}),
    ("5 maggi", {"Maggi": 5}),
    ("2 kilo cheeni", {"Cheeni": 2}),
    ("do sau gram cheeni", {"Cheeni": 0.2}),
    ("sau gram dal", {"Dal": 0.1}),
    ("ek sau pachaas gram dal", {"Dal": 0.15}),
    ("teen kilo chawal do kilo dal ek kilo cheeni", {"Chawal": 3, "Dal": 2, "Cheeni": 1}),
    ("pachas rupaye ka paneer", {"Paneer": 0.13}),
    ("sau rupaye ki dal", {"Dal": 0.71}),
    ("bees rupaye ka maggi", {"Maggi": 1}),
    # --- scripts and spelling ---
    ("२ मैगी", {"Maggi": 2}),
    ("दो मैगी एक सर्फ एक्सेल चार कोलगेट", {"Maggi": 2, "Surf Excel": 1, "Colgate": 4}),
    ("तीन पारले जी", {"Parle-G": 3}),
    ("maggie teen", {"Maggi": 3}),
    ("kolgate do", {"Colgate": 2}),
    # --- order styles ---
    ("maggi do surf ek", {"Maggi": 2, "Surf Excel": 1}),
    ("ek doodh ek bread chhe ande", {"Doodh": 1, "Bread": 1, "Ande": 6}),
    ("mujhe do maggi de do", {"Maggi": 2}),
    ("teen maggi aur teen maggi", {"Maggi": 6}),
    ("ek ghee", {"Amul Ghee 500ml": 1}),
    ("do diya ek mithai box", {"Diya Pack (12)": 2, "Mithai Box 500g": 1}),
    ("ek kilo paneer", {"Paneer": 1}),
    ("ek thums up do bisleri", {"Thums Up 750ml": 1, "Bisleri 1L": 2}),
    ("pachchis toffee", {"Toffee": 25}),
    ("chaar maggi", {"Maggi": 4}),
    ("do maggi aur teen kurkure", {"Maggi": 2}),
]


def as_dict(lines):
    return {ln.name: pytest.approx(ln.qty, abs=1e-6) for ln in lines}


@pytest.mark.parametrize("text,expected", CASES, ids=[c[0][:40] for c in CASES])
def test_parse_order_table(db, text, expected):
    got = {ln.name: ln.qty for ln in parse_order(text, db)}
    assert got == {k: pytest.approx(v, abs=1e-6) for k, v in expected.items()}


def test_table_size():
    assert len(CASES) >= 40


def test_amount_based_cheeni_is_450_grams(db):
    (line,) = parse_order("bees rupaye ki cheeni", db)
    assert line.qty == pytest.approx(0.45)
    assert line.weigh_instruction == "450 gram tolo"
    assert line.amount_rupees == 20
    assert line.line_total == 20.0  # billed the asked amount
    assert line.unit == "kg" and line.sell_mode == "loose"


def test_amount_rounds_down_to_10_grams():
    assert quantity.amount_to_quantity(20, 44) == pytest.approx(0.45)
    assert quantity.amount_to_quantity(22, 44) == pytest.approx(0.50)
    assert quantity.amount_to_quantity(10, 44) == pytest.approx(0.22)
    assert quantity.amount_to_quantity(1, 0) == 0.0


def test_weigh_instruction_formats():
    assert quantity.weigh_instruction(0.45, "kg") == "450 gram tolo"
    assert quantity.weigh_instruction(1.0, "kg") == "1 kilo tolo"
    assert quantity.weigh_instruction(1.25, "kg") == "1 kilo 250 gram tolo"
    assert quantity.weigh_instruction(0.3, "l") == "300 ml naap lo"


def test_unit_disambiguation_between_loose_and_packed(db):
    assert parse_order("paanch kilo chawal", db)[0].name == "Chawal"
    assert parse_order("do chawal", db)[0].name == "Rice 5kg"
    assert parse_order("teen kilo atta", db)[0].name == "Atta"
    assert parse_order("teen atta", db)[0].name == "Aashirvaad Atta 5kg"


def test_unmatched_item_reported(db):
    out = parse_order_full("do maggi aur teen kurkure", db)
    assert [ln.name for ln in out.lines] == ["Maggi"]
    assert out.unmatched == [{"name": "kurkure", "qty": 3.0, "raw": "teen kurkure"}]


def test_line_totals_use_mrp(db):
    lines = parse_order("do maggi ek surf excel chaar colgate", db)
    assert sum(ln.line_total for ln in lines) == 249.0


def test_empty_and_noise(db):
    assert parse_order("", db) == []
    assert parse_order("bhaiya namaste kaise ho", db) == []


@pytest.mark.parametrize("text", ["bas kitna hua", "total", "bill banao", "kitna hua bhaiya"])
def test_checkout_phrases(text):
    assert is_checkout_phrase(text)


def test_not_checkout():
    assert not is_checkout_phrase("do maggi")
