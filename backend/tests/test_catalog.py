import pytest

from services import catalog
from services.catalog import keyterms, load_index, match_customer, match_product, normalize


def test_normalize():
    assert normalize("  Parle-G!  ") == "parle g"
    assert normalize("₹20 ki cheeni") == "20 rupaye ki cheeni"
    assert normalize("Rs.45 ka surf") == "45 rupaye ka surf"
    assert normalize("१० पैकेट") == "10 पैकेट"
    assert normalize("1,200 rupaye") == "1200 rupaye"


@pytest.mark.parametrize("spoken,name", [
    ("maggi", "Maggi"), ("maggie", "Maggi"), ("Surf Excel", "Surf Excel"), ("serf excel", "Surf Excel"),
    ("kolgate", "Colgate"), ("shahad", "Patanjali Honey"), ("doodh", "Doodh"), ("dudh", "Doodh"),
    ("पारले जी", "Parle-G"), ("मैगी", "Maggi"), ("कोलगेट", "Colgate"), ("दूध", "Doodh"),
    ("cheeni", "Cheeni"), ("chini", "Cheeni"), ("tata namak", "Tata Salt"),
])
def test_product_match(db, spoken, name):
    product, score = match_product(db, spoken)
    assert product is not None and product.name == name
    assert score >= 75


def test_no_match_for_unknown_or_short(db):
    assert match_product(db, "kurkure")[0] is None
    assert match_product(db, "xyz")[0] is None
    assert match_product(db, "")[0] is None


def test_shared_aliases_return_all_candidates(db):
    index = load_index(db)
    names = {p.name for p, _ in index.match_all("atta")}
    assert names == {"Aashirvaad Atta 5kg", "Atta"}
    assert {p.name for p, _ in index.match_all("chawal")} == {"Rice 5kg", "Chawal"}


def test_find_in_phrase_for_vision_names(db):
    index = load_index(db)
    assert index.find_in_phrase("Parle-G biscuits 56g")[0].name == "Parle-G"
    assert index.find_in_phrase("Colgate Strong Teeth 100g")[0].name == "Colgate"
    assert index.find_in_phrase("Surf Excel Easy Wash")[0].name == "Surf Excel"
    assert index.find_in_phrase("Lays Magic Masala 52g")[0] is None


@pytest.mark.parametrize("spoken,name", [
    ("Verma ji", "Verma ji"), ("verma", "Verma ji"), ("Sharma ji ke", "Sharma ji"),
    ("sharma", "Sharma ji"), ("vermaa ji", "Verma ji"), ("वर्मा जी", "Verma ji"),
    ("Kapoor", "Mrs. Kapoor"),
])
def test_customer_match(db, spoken, name):
    customer, score = match_customer(db, spoken)
    assert customer is not None and customer.name == name


def test_customer_no_match(db):
    assert match_customer(db, "Zebra")[0] is None
    assert match_customer(db, "")[0] is None


def test_keyterms_limits(db):
    terms = keyterms(db)
    assert 0 < len(terms) <= 50
    assert all(0 < len(t) <= 64 for t in terms)
    assert len({t.lower() for t in terms}) == len(terms)
    assert "Maggi" in terms and "Surf Excel" in terms and "Colgate" in terms
    assert len(keyterms(db, limit=5)) == 5


def test_kurkure_not_in_catalog(db):
    index = load_index(db)
    assert "kurkure" not in index.alias_map


def test_transliteration_is_roughly_right():
    assert catalog.transliterate_devanagari("मैगी") == "maigi"
    assert catalog.has_devanagari("मैगी") and not catalog.has_devanagari("maggi")
