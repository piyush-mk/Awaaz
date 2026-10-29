"""Seed "Ramesh General Store, Laxmi Nagar" (the demo scenario of the Awaaz deck).

    python seed.py            # seed only if the database is empty
    python seed.py --reset    # drop everything and rebuild

Numbers that line up with the deck (asserted in tests/test_seed.py):
  * 2 Maggi + 1 Surf + 4 Colgate = Rs 249 (MRP-inclusive)
  * cheeni Rs 44/kg, so Rs 20 buys 450 g
  * Colgate stock 12; ghee ~2 days of cover; Kurkure is NOT in the catalog
  * yesterday's sales Rs 8,420 (12% above the same weekday last week)
  * Verma ji owes Rs 850 and paid late 3 times; Rajesh Distributors last charged Surf Rs 42
  * galla expected today = Rs 6,850 (opening float Rs 2,000 + Rs 4,850 cash sales)
  * 45 days of history with a weekday pattern, plus last year's Dhanteras week spike

GST rates come from `pricing.GST_RATES_BY_CATEGORY` (GST 2.0). They are DATA:
verify against the CBIC notification before using them for real filing.
Everything is deterministic (fixed random seed); dates are relative to `today`.
"""
from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta
from typing import Any, Optional

from database import SessionLocal, Base, engine, init_db
from models import (
    CashClosing, Customer, Invoice, InvoiceItem, KhataEntry, MissedSale, Payment, Product,
    PurchaseBill, PurchaseItem, StockBatch, StockMove, StoreProfile, Supplier,
)
from services import pricing
from services.clock import today_local

RNG_SEED = 20261031
OPENING_FLOAT = 2000.0
TODAY_CASH_TARGET = 4850.0  # galla expected = OPENING_FLOAT + this = 6850
YESTERDAY_TOTAL = 8420
YESTERDAY_WEEK_AGO_TOTAL = 7518  # 8420 / 7518 = +12.0%
HISTORY_DAYS = 45

G = pricing.GST_RATES_BY_CATEGORY

# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------
# keys: id name name_hi aliases category hsn gst(category key) mrp cost mode base unit
#       loose(price per base) threshold stock supplier tags pop(history weight)
#       pack_size parent expiry_days

SUPPLIERS = [
    {"id": 1, "name": "Rajesh Distributors", "contact_name": "Rajesh Kumar", "phone": "919810000101",
     "visit_day": "Saturday", "lead_days": 1, "notes": "FMCG: Surf, Maggi, Colgate, Parle-G, Dettol"},
    {"id": 2, "name": "Sharma Dairy and Fresh", "contact_name": "Mohan Sharma", "phone": "919810000102",
     "visit_day": "Daily", "lead_days": 0, "notes": "Doodh, ande, paneer, bread, dahi"},
    {"id": 3, "name": "Om Traders", "contact_name": "Om Prakash", "phone": "919810000103",
     "visit_day": "Wednesday", "lead_days": 2, "notes": "Loose staples: cheeni, chawal, dal, atta, tel"},
    {"id": 4, "name": "Laxmi Festival Mart", "contact_name": "Suresh Bansal", "phone": "919810000104",
     "visit_day": "Tuesday", "lead_days": 3, "notes": "Ghee, dry fruits, diya, mithai, agarbatti"},
]


def P(id, name, name_hi, aliases, category, hsn, gst, mrp, cost, unit="packet", threshold=5,
      stock=10, supplier=1, tags=None, pop=1.0, mode="unit", base="pc", loose=None,
      pack_size=None, parent=None, expiry_days=None, gst_override=None):
    return dict(id=id, name=name, name_hi=name_hi, aliases=aliases, category=category, hsn=hsn,
                gst=gst, mrp=mrp, cost=cost, unit=unit, threshold=threshold, stock=stock,
                supplier=supplier, tags=tags or [], pop=pop, mode=mode, base=base, loose=loose,
                pack_size=pack_size, parent=parent, expiry_days=expiry_days,
                gst_override=gst_override)


PRODUCTS: list[dict[str, Any]] = [
    # --- the original 10 (ids kept; GST corrected to GST 2.0) ---
    P(1, "Maggi", "मैगी", ["maggi", "maggie", "magi", "noodles", "maggi noodles", "मैगी", "मैग्गी", "नूडल्स"],
      "food", "1902", "packaged_food", 12, 11, threshold=5, stock=12, pop=8, expiry_days=240),
    P(2, "Rice 5kg", "चावल", ["rice", "chawal", "rice bag", "chawal bag", "rice 5kg", "chawal 5kg", "चावल", "चावल बैग", "राइस"],
      "staples", "1006", "staples", 350, 315, unit="bag", threshold=3, stock=8, supplier=3, pop=1),
    P(3, "Surf Excel", "सर्फ एक्सेल", ["surf", "surf excel", "serf", "sarf", "detergent", "सर्फ", "सर्फ एक्सेल", "सर्फ एक्सल"],
      "cleaning", "3402", "detergent", 45, 42, threshold=5, stock=15, pop=4, expiry_days=600),
    P(4, "Tata Salt", "टाटा नमक", ["tata namak", "tata salt", "namak", "salt", "tata", "नमक", "टाटा नमक", "टाटा"],
      "staples", "2501", "staples", 28, 25, threshold=5, stock=3, pop=4),
    P(5, "Colgate", "कोलगेट", ["colgate", "kolgate", "toothpaste", "tooth paste", "कोलगेट", "टूथपेस्ट"],
      "personal_care", "3306", "oral_care", 45, 41, threshold=4, stock=12, pop=4, expiry_days=700),
    P(6, "Aashirvaad Atta 5kg", "आशीर्वाद आटा",
      ["aashirvaad atta", "aashirvaad", "ashirvad", "ashirwad", "aashirwad atta", "atta", "atta bag", "आशीर्वाद आटा", "आशीर्वाद", "आटा"],
      "staples", "1101", "branded_staples", 320, 290, unit="bag", threshold=3, stock=2, supplier=3, pop=1),
    P(7, "Patanjali Honey", "पतंजलि शहद", ["patanjali shahad", "patanjali honey", "honey", "shahad", "shehad", "patanjali", "पतंजलि शहद", "शहद", "पतंजलि"],
      "food", "0409", "packaged_food", 180, 160, unit="bottle", threshold=3, stock=7, pop=0.5),
    P(8, "Vim Bar", "विम बार", ["vim bar", "vim", "vim soap", "विम बार", "विम"],
      "cleaning", "3401", "detergent", 15, 12.5, unit="bar", threshold=5, stock=4, pop=3),
    P(9, "Parle-G", "पारले-जी", ["parle g", "parle", "parleg", "parle gee", "पारले जी", "पारले"],
      "food", "1905", "packaged_food", 10, 8.6, threshold=8, stock=20, pop=8, expiry_days=150),
    P(10, "Dettol Soap", "डेटॉल साबुन", ["dettol sabun", "dettol soap", "dettol", "sabun", "soap", "डेटॉल साबुन", "डेटॉल", "साबुन"],
      "personal_care", "3401", "soap", 35, 31, unit="soap", threshold=4, stock=6, pop=2, expiry_days=700),
    # --- loose goods (sold by weight / volume) ---
    P(11, "Cheeni", "चीनी", ["cheeni", "chini", "sugar", "चीनी", "चिनी", "शक्कर"],
      "staples", "1701", "packaged_food", 44, 40, unit="kg", threshold=10, stock=35, supplier=3,
      pop=5, mode="loose", base="kg", loose=44),
    P(12, "Chawal", "चावल", ["chawal", "rice", "loose chawal", "loose rice", "चावल", "राइस"],
      "staples", "1006", "staples", 62, 55, unit="kg", threshold=10, stock=60, supplier=3, pop=3,
      mode="loose", base="kg", loose=62),
    P(13, "Dal", "दाल", ["dal", "daal", "toor dal", "arhar dal", "दाल", "अरहर दाल", "तुअर दाल"],
      "staples", "0713", "staples", 140, 128, unit="kg", threshold=5, stock=22, supplier=3, pop=3,
      mode="loose", base="kg", loose=140),
    P(14, "Atta", "आटा", ["atta", "loose atta", "chakki atta", "aata", "आटा", "चक्की आटा"],
      "staples", "1101", "staples", 40, 36, unit="kg", threshold=15, stock=80, supplier=3, pop=4,
      mode="loose", base="kg", loose=40),
    P(15, "Sarson Tel", "सरसों तेल", ["tel", "sarson tel", "sarson ka tel", "oil", "mustard oil", "तेल", "सरसों तेल"],
      "staples", "1514", "edible_oil", 160, 146, unit="litre", threshold=5, stock=18, supplier=3, pop=3,
      mode="loose", base="l", loose=160),
    # --- fresh ---
    P(16, "Ande", "अंडे", ["ande", "anda", "egg", "eggs", "अंडे", "अंडा"], "fresh", "0407", "fresh",
      7, 5.8, unit="pc", threshold=30, stock=90, supplier=2, pop=6, expiry_days=12),
    P(17, "Doodh", "दूध", ["doodh", "dudh", "milk", "amul doodh", "दूध"], "fresh", "0401", "fresh",
      30, 28, threshold=10, stock=40, supplier=2, pop=8, expiry_days=2),
    P(18, "Paneer", "पनीर", ["paneer", "पनीर"], "fresh", "0406", "fresh", 380, 340, unit="kg",
      threshold=2, stock=4.5, supplier=2, pop=1.5, mode="loose", base="kg", loose=380, expiry_days=4),
    P(19, "Bread", "ब्रेड", ["bread", "double roti", "ब्रेड", "डबल रोटी"], "fresh", "1905", "fresh",
      45, 40, unit="loaf", threshold=5, stock=12, supplier=2, pop=5, expiry_days=3),
    # --- festival ---
    P(20, "Amul Ghee 500ml", "अमूल घी", ["ghee", "amul ghee", "घी", "अमूल घी"], "festival", "0405",
      "packaged_food", 340, 305, unit="pouch", threshold=2, stock=3, supplier=4,
      tags=["ghee"], pop=0.1, expiry_days=300),
    P(21, "Dry Fruits Box 250g", "ड्राई फ्रूट", ["dry fruits", "dry fruit", "dryfruits", "meva", "mewa", "ड्राई फ्रूट", "मेवा"],
      "festival", "0802", "festival", 420, 370, unit="box", threshold=3, stock=9, supplier=4,
      tags=["dry_fruits"], pop=0.05),
    P(22, "Diya Pack (12)", "दीया", ["diya", "diye", "deepak", "diya pack", "दीया", "दिये", "दीपक"],
      "festival", "6912", "festival", 60, 45, unit="pack", threshold=5, stock=30, supplier=4,
      tags=["diya"], pop=0.03),
    P(23, "Mithai Box 500g", "मिठाई", ["mithai", "mithai box", "sweets", "मिठाई"], "festival", "2106",
      "festival", 350, 300, unit="box", threshold=3, stock=10, supplier=4, tags=["mithai"], pop=0.05),
    # --- everyday packaged ---
    P(24, "Tata Tea Gold 250g", "टाटा चाय", ["chai patti", "tata tea", "tea", "chai", "चाय", "चायपत्ती"],
      "food", "0902", "packaged_food", 140, 125, threshold=4, stock=14, pop=4, expiry_days=300),
    P(25, "Bournvita 500g", "बॉर्नविटा", ["bournvita", "bornvita", "बॉर्नविटा"], "food", "1901",
      "beverage_mix", 190, 175, unit="jar", threshold=3, stock=6, pop=0.4, expiry_days=6),
    P(26, "Haldi 100g", "हल्दी", ["haldi", "turmeric", "हल्दी"], "food", "0910", "packaged_food", 40, 34,
      threshold=4, stock=15, pop=2),
    P(27, "Toffee", "टॉफी", ["toffee", "candy", "pulse", "टॉफी"], "food", "1704", "confectionery", 1, 0.8,
      unit="pc", threshold=50, stock=300, pop=10),
    P(28, "Good Day Biscuit", "गुड डे", ["good day", "goodday", "britannia", "गुड डे"], "food", "1905",
      "packaged_food", 10, 8.5, threshold=8, stock=24, pop=5, expiry_days=150),
    P(29, "Lux Soap", "लक्स साबुन", ["lux", "lux sabun", "लक्स"], "personal_care", "3401", "soap", 38, 33,
      unit="soap", threshold=4, stock=10, pop=2),
    P(30, "Amul Butter 100g", "अमूल बटर", ["butter", "amul butter", "बटर", "मक्खन"], "fresh", "0405",
      "packaged_food", 62, 56, threshold=4, stock=8, supplier=2, pop=2, expiry_days=60),
    P(31, "Dahi 400g", "दही", ["dahi", "curd", "दही"], "fresh", "0403", "packaged_food", 40, 35, threshold=5,
      stock=10, supplier=2, pop=3, expiry_days=5),
    P(32, "Thums Up 750ml", "थम्स अप", ["thums up", "thumbs up", "cold drink", "थम्स अप", "कोल्ड ड्रिंक"],
      "drinks", "2202", "aerated_drink", 40, 35, unit="bottle", threshold=6, stock=18, pop=3),
    P(33, "Bisleri 1L", "बिसलेरी", ["bisleri", "pani", "water", "पानी", "बिसलेरी"], "drinks", "2201",
      "water", 20, 16, unit="bottle", threshold=8, stock=30, pop=4),
    P(34, "Besan", "बेसन", ["besan", "बेसन"], "staples", "1106", "staples", 80, 70, unit="kg", threshold=3,
      stock=9, supplier=3, pop=1, mode="loose", base="kg", loose=80),
    P(35, "Haldiram Bhujia 200g", "भुजिया", ["bhujia", "haldiram", "namkeen", "भुजिया", "नमकीन"], "food",
      "2106", "packaged_food", 55, 48, threshold=4, stock=12, pop=3, expiry_days=120),
    P(36, "Maggi Carton (12)", "मैगी कार्टन", ["maggi carton", "maggi box", "मैगी कार्टन"], "food", "1902",
      "packaged_food", 144, 126, unit="carton", threshold=1, stock=2, pop=0, pack_size=12, parent=1),
    P(37, "Agarbatti", "अगरबत्ती", ["agarbatti", "incense", "अगरबत्ती"], "festival", "3307", "festival", 20,
      16, threshold=5, stock=25, supplier=4, tags=["pooja"], pop=1),
    P(38, "Matchbox", "माचिस", ["matchbox", "maachis", "match", "माचिस"], "general", "3605", "festival", 2, 1.5,
      unit="pc", threshold=20, stock=60, supplier=4, pop=4),
    P(39, "Fortune Oil 1L", "फॉर्च्यून तेल", ["fortune oil", "fortune tel", "refined oil", "tel pouch", "फॉर्च्यून तेल"],
      "staples", "1512", "edible_oil", 140, 128, unit="pouch", threshold=4, stock=12, supplier=3, pop=2),
    P(40, "Dairy Milk 25g", "डेयरी मिल्क", ["dairy milk", "cadbury", "chocolate", "चॉकलेट", "डेयरी मिल्क"],
      "food", "1806", "packaged_food", 20, 17.5, threshold=8, stock=24, pop=3, expiry_days=200),
]

# (name, balance, late_payments, credit_limit, name_hi)
CUSTOMERS: list[dict[str, Any]] = [
    {"id": 1, "name": "Walk-in Customer", "balance": 0},
    {"id": 2, "name": "Verma ji", "name_hi": "वर्मा जी", "balance": 850, "late": 3, "limit": 1000,
     "phone": "919810000002", "upi": "verma.ji@paytm"},
    {"id": 3, "name": "Sharma ji", "name_hi": "शर्मा जी", "balance": 0, "late": 0, "limit": 1500,
     "phone": "919810000003", "upi": "sharma.ji@paytm",
     "usual": [{"product_id": 17, "qty": 1}, {"product_id": 19, "qty": 1}, {"product_id": 16, "qty": 6}]},
    {"id": 4, "name": "Mrs. Kapoor", "name_hi": "कपूर मैडम", "balance": 0, "late": 0, "limit": 3000,
     "phone": "919810000004", "upi": "kapoor.family@paytm",
     "usual": [{"product_id": 14, "qty": 10}, {"product_id": 11, "qty": 2}, {"product_id": 13, "qty": 2},
               {"product_id": 15, "qty": 1}]},
    {"id": 5, "name": "Singh sahab", "balance": 350, "late": 0},
    {"id": 6, "name": "Joshi ji", "balance": 1200, "late": 1},
    {"id": 7, "name": "Agarwal ji", "balance": 0, "late": 0},
    {"id": 8, "name": "Khan sahab", "balance": 2200, "late": 2, "limit": 2500},
    {"id": 9, "name": "Yadav ji", "balance": 140, "late": 0},
    {"id": 10, "name": "Mehta ji", "balance": 0, "late": 0},
    {"id": 11, "name": "Chauhan ji", "balance": 560, "late": 1},
    {"id": 12, "name": "Bansal ji", "balance": 780, "late": 0},
    {"id": 13, "name": "Malhotra ji", "balance": 95, "late": 0},
    {"id": 14, "name": "Rawat ji", "balance": 1650, "late": 2, "limit": 2000},
    {"id": 15, "name": "Pooja didi", "balance": 0, "late": 0},
    {"id": 16, "name": "Sunita bhabhi", "balance": 310, "late": 0},
    {"id": 17, "name": "Anil bhaiya", "balance": 450, "late": 1},
    {"id": 18, "name": "Iyer uncle", "balance": 0, "late": 0},
]

WEEKDAY_FACTOR = [0.86, 0.88, 0.92, 0.95, 1.05, 1.22, 1.12]  # Mon..Sun
BASE_DAILY = 6900


def _p(pid: int) -> dict[str, Any]:
    return next(x for x in PRODUCTS if x["id"] == pid)


def _price(prod: dict[str, Any]) -> float:
    return float(prod["loose"] if prod["mode"] == "loose" else prod["mrp"])


# ---------------------------------------------------------------------------
# history generation
# ---------------------------------------------------------------------------

_QTY_CHOICES = {
    "unit": [1, 1, 1, 2, 2, 3, 4],
    "loose": [0.5, 1, 1, 2, 2, 5],
    "pc_many": [6, 6, 12, 4, 2],
    "candy": [2, 5, 5, 10],
}


def _qty_options(prod: dict[str, Any]) -> list[float]:
    if prod["id"] == 27:
        return _QTY_CHOICES["candy"]
    if prod["id"] in (16,):
        return _QTY_CHOICES["pc_many"]
    if prod["id"] == 18:
        return [0.25, 0.5, 0.5, 1]
    if prod["mode"] == "loose":
        return _QTY_CHOICES["loose"]
    return _QTY_CHOICES["unit"]


def _history_products() -> tuple[list[dict[str, Any]], list[float]]:
    items = [p for p in PRODUCTS if p["pop"] > 0]
    return items, [p["pop"] for p in items]


def basket_to_target(rng: random.Random, target: int, fixed: Optional[dict[int, float]] = None
                     ) -> dict[int, float]:
    """Random basket whose total is exactly `target` rupees (integer prices only)."""
    items, weights = _history_products()
    basket: dict[int, float] = dict(fixed or {})
    remaining = target - int(round(sum(_price(_p(pid)) * q for pid, q in basket.items())))
    tries = 0
    while remaining >= 25 and tries < 80:
        prod = rng.choices(items, weights)[0]
        qty = rng.choice(_qty_options(prod))
        cost = int(round(_price(prod) * qty))
        if cost > remaining or cost <= 0:
            tries += 1
            continue
        basket[prod["id"]] = basket.get(prod["id"], 0) + qty
        remaining -= cost
    tens, rest = divmod(max(remaining, 0), 10)
    if tens:
        basket[9] = basket.get(9, 0) + tens  # Parle-G
    if rest:
        basket[27] = basket.get(27, 0) + rest  # toffee at Rs 1
    return basket


def _split_day_total(rng: random.Random, total: int) -> list[int]:
    sizes: list[int] = []
    left = total
    while left > 0:
        size = rng.randint(80, 280)
        if left - size < 80:
            size = left
        sizes.append(size)
        left -= size
    return sizes


def _ghee_units(days_ago: int) -> int:
    """Ghee units sold per day: exactly alternating 2,1 in the last 14 days (velocity 1.5/day)."""
    if 1 <= days_ago <= 14:
        return 2 if days_ago % 2 == 1 else 1
    return 1 if days_ago % 3 else 0


def _target_for(day: date, today: date, rng: random.Random, last_year: bool) -> int:
    if day == today - timedelta(days=1):
        return YESTERDAY_TOTAL
    if day == today - timedelta(days=8):
        return YESTERDAY_WEEK_AGO_TOTAL
    base = BASE_DAILY * WEEKDAY_FACTOR[day.weekday()] * rng.uniform(0.93, 1.07)
    if last_year:
        dist = abs((day - date(2025, 10, 18)).days)
        base *= 1.0 + max(0.0, 1.0 - dist / 6.0) * 0.9
    return int(round(base / 10.0) * 10)


class HistoryBuilder:
    """Accumulates invoices, items, payments and stock moves in memory."""

    def __init__(self, rng: random.Random, customer_ids: list[int]):
        self.rng = rng
        self.customer_ids = customer_ids
        self.invoices: list[Invoice] = []
        self.payments: list[Payment] = []
        self.moves: list[StockMove] = []
        self.sold: dict[int, float] = {}
        self.seq: dict[str, int] = {}
        self.next_id = 1

    def _number(self, at: datetime) -> str:
        fy = pricing.financial_year(at.date())
        self.seq[fy] = self.seq.get(fy, 0) + 1
        return pricing.invoice_number("RGS", at.date(), self.seq[fy])

    def add_invoice(self, at: datetime, basket: dict[int, float], mode: str,
                    customer_id: Optional[int] = None, split: Optional[tuple[float, float]] = None,
                    status: str = "paid") -> Invoice:
        inv_id = self.next_id
        self.next_id += 1
        lines, items = [], []
        for pid, qty in basket.items():
            prod = _p(pid)
            lt = pricing.price_line(qty, _price(prod), float(prod["_gst"]))
            lines.append(lt)
            items.append(InvoiceItem(
                product_id=pid, name=prod["name"], name_hi=prod["name_hi"], qty=qty, unit=prod["unit"],
                mrp=_price(prod), gst_rate=lt.gst_rate, hsn=prod["hsn"], taxable=lt.taxable,
                cgst=lt.cgst, sgst=lt.sgst, total=lt.total))
            self.moves.append(StockMove(product_id=pid, qty_change=-qty, kind="sale",
                                        ref=f"invoice:{inv_id}", amount=lt.total, at=at))
            self.sold[pid] = self.sold.get(pid, 0.0) + qty
        totals = pricing.totals_for_lines(lines)
        inv = Invoice(id=inv_id, number=self._number(at), doc_type="tax_invoice",
                      customer_id=customer_id, status=status, taxable_total=totals.taxable,
                      cgst_total=totals.cgst, sgst_total=totals.sgst, total=totals.total,
                      public_token=f"seed{inv_id:05d}", created_at=at, paid_at=at, items=items)
        self.invoices.append(inv)
        parts = [(mode, totals.total)] if split is None else [
            ("cash", split[0]), ("upi", round(totals.total - split[0], 2))]
        for k, (m, amt) in enumerate(parts):
            self.payments.append(Payment(
                invoice_id=inv_id, customer_id=customer_id, mode=m, amount=amt, status="success",
                order_id=f"ORD-{inv_id:05d}-{k}", rail="upi_intent" if m == "upi" else "simulated",
                created_at=at, paid_at=at))
        return inv

    def _time(self, day: date, k: int, n: int) -> datetime:
        minutes = int(8 * 60 + (k + self.rng.random()) / max(n, 1) * 13 * 60)
        return datetime(day.year, day.month, day.day) + timedelta(minutes=minutes)

    def build_day(self, day: date, today: date, total: int, last_year: bool = False) -> None:
        """All invoices of one day summing to exactly `total` rupees."""
        rng = self.rng
        days_ago = (today - day).days
        dedicated: list[tuple[dict[int, float], Optional[int]]] = []
        if not last_year:
            for _ in range(_ghee_units(days_ago)):
                dedicated.append(({20: 1}, None))
            if days_ago % 2 == 0:  # Sharma ji's usual basket every other day
                dedicated.append(({17: 1, 19: 1, 16: 6}, 3))
            if days_ago in (3, 6, 9, 13, 17):
                dedicated.append(({21: 1}, None))
        else:
            spike = max(0.0, 1.0 - abs((day - date(2025, 10, 18)).days) / 6.0)
            for pid, base in ((20, 5), (21, 4), (22, 12), (23, 5)):
                for _ in range(int(round(base * (0.4 + 3.0 * spike)))):
                    dedicated.append(({pid: 1}, None))
        plans: list[tuple[int, dict[int, float], Optional[int]]] = []
        used = 0
        for fixed, cust in dedicated:
            fixed_total = int(round(sum(_price(_p(pid)) * q for pid, q in fixed.items())))
            extra = rng.randint(0, 120) if cust is None else 0
            plans.append((fixed_total + extra, fixed, cust))
            used += fixed_total + extra
        while used > total - 80 and plans:  # dedicated baskets must leave room for the rest
            used -= plans.pop()[0]
        sizes = _split_day_total(rng, total - used) if total - used > 0 else []
        plans += [(s, {}, None) for s in sizes]
        rng.shuffle(plans)
        n = len(plans)
        times = sorted(self._time(day, k, n) for k in range(n))
        for at, (size, fixed, cust) in zip(times, plans):
            basket = basket_to_target(rng, size, fixed)
            if cust is None and rng.random() < 0.18:
                cust = rng.choice(self.customer_ids)
            r = rng.random()
            if r < 0.04:
                total_inv = int(round(sum(_price(_p(pid)) * q for pid, q in basket.items())))
                cash_part = float(max(10, (total_inv // 20) * 10))
                self.add_invoice(at, basket, "cash", cust, split=(min(cash_part, total_inv - 1), 0))
            else:
                self.add_invoice(at, basket, "cash" if r < 0.42 else "upi", cust)

    def build_today(self, today: date) -> None:
        """Today's partial day: cash payments sum to exactly TODAY_CASH_TARGET."""
        rng = self.rng
        cash_left = int(TODAY_CASH_TARGET)
        times = sorted(self._time(today, k, 34) for k in range(34))
        k = 0
        while cash_left > 0:
            size = rng.randint(90, 260) if cash_left - 260 > 60 else cash_left
            size = min(size, cash_left)
            self.add_invoice(times[k % len(times)], basket_to_target(rng, size), "cash")
            cash_left -= size
            k += 1
        upi_left = 2420
        while upi_left > 0:
            size = rng.randint(90, 260) if upi_left - 260 > 60 else upi_left
            size = min(size, upi_left)
            cust = 3 if k == 5 else None
            self.add_invoice(times[k % len(times)], basket_to_target(rng, size), "upi", cust)
            upi_left -= size
            k += 1


def _khata_entries(rng: random.Random, customer: Customer, balance: int, late: int,
                   today: date) -> list[KhataEntry]:
    """Ledger lines that add up to `balance`; `late` earlier credits were repaid late."""
    entries: list[KhataEntry] = []

    def at(days_ago: int) -> datetime:
        return datetime(today.year, today.month, today.day, 11, 0) - timedelta(days=days_ago)

    cid = customer.id
    ago = HISTORY_DAYS - 3
    for i in range(late):
        amt = rng.choice([300, 400, 500, 600, 700])
        entries.append(KhataEntry(customer_id=cid, amount=amt, note="udhaar", at=at(ago),
                                  confirmed_by_customer=True))
        entries.append(KhataEntry(customer_id=cid, amount=-amt, note="der se chukaya (late)",
                                  at=at(ago - rng.randint(10, 18)), confirmed_by_customer=True))
        ago -= 9
    if balance:
        parts = [balance] if balance < 400 else [balance // 2 // 10 * 10, balance - balance // 2 // 10 * 10]
        for j, amt in enumerate(parts):
            entries.append(KhataEntry(customer_id=cid, amount=amt, note="udhaar",
                                      at=at(rng.randint(2, 12) + j * 3), confirmed_by_customer=True))
    return entries


# ---------------------------------------------------------------------------
# main seed
# ---------------------------------------------------------------------------


def seed(reset: bool = False, today: Optional[date] = None, verbose: bool = True) -> dict[str, Any]:
    """Populate the demo store. Idempotent: does nothing if products exist, unless reset=True."""
    if reset:
        import models  # noqa: F401
        Base.metadata.drop_all(bind=engine)
    init_db()
    db = SessionLocal()
    try:
        if db.query(Product).count() > 0:
            if verbose:
                print("Database already seeded. Use --reset to rebuild.")
            return {"seeded": False}
        return _seed(db, today or today_local(), verbose)
    finally:
        db.close()


def _seed(db, today: date, verbose: bool) -> dict[str, Any]:
    rng = random.Random(RNG_SEED)
    now_dt = datetime(today.year, today.month, today.day, 9, 0)

    db.add(StoreProfile(
        id=1, name="Ramesh General Store", owner_name="Ramesh Gupta", address="Laxmi Nagar, Delhi 110092",
        phone="919810000001", upi_vpa="paytm.merchant@paytm", gstin="07ABCDE1234F1Z5",
        composition_scheme=False, language="hi-IN", opening_float=OPENING_FLOAT, invoice_prefix="RGS"))
    for s in SUPPLIERS:
        db.add(Supplier(**s))

    for prod in PRODUCTS:
        prod["_gst"] = prod["gst_override"] if prod["gst_override"] is not None else G[prod["gst"]]
        db.add(Product(
            id=prod["id"], name=prod["name"], name_hi=prod["name_hi"], aliases=prod["aliases"],
            category=prod["category"], hsn=prod["hsn"], gst_rate=prod["_gst"], mrp=float(prod["mrp"]),
            cost_price=float(prod["cost"]), sell_mode=prod["mode"], base_unit=prod["base"],
            unit=prod["unit"], loose_price_per_base=prod["loose"], pack_size=prod["pack_size"],
            parent_id=prod["parent"], threshold=float(prod["threshold"]), festival_tags=prod["tags"],
            supplier_id=prod["supplier"], barcode=f"890{prod['id']:010d}"))
    db.flush()

    customers: dict[int, Customer] = {}
    for c in CUSTOMERS:
        cust = Customer(
            id=c["id"], name=c["name"], name_hi=c.get("name_hi"), phone=c.get("phone"),
            upi_id=c.get("upi"), language="hi-IN", credit_limit=float(c.get("limit", 1000)),
            late_payments=c.get("late", 0), usual_basket=c.get("usual", []),
            created_at=now_dt - timedelta(days=200))
        db.add(cust)
        customers[c["id"]] = cust
    db.flush()

    # --- history: last year's Dhanteras week + 45 days ---
    hb = HistoryBuilder(rng, [c["id"] for c in CUSTOMERS if c["id"] != 1])
    for offset in range(-3, 4):
        day = date(2025, 10, 18) + timedelta(days=offset)
        hb.build_day(day, today, _target_for(day, today, rng, True), last_year=True)
    for days_ago in range(HISTORY_DAYS, 0, -1):
        day = today - timedelta(days=days_ago)
        hb.build_day(day, today, _target_for(day, today, rng, False))
    hb.build_today(today)
    db.add_all(hb.invoices)
    db.add_all(hb.payments)

    # --- stock: batches at final levels; ledger reconciles via an opening restock ---
    open_at = datetime(today.year, today.month, today.day) - timedelta(days=HISTORY_DAYS + 1)
    batches = 0
    for prod in PRODUCTS:
        pid, final = prod["id"], float(prod["stock"])
        sold = hb.sold.get(pid, 0.0)
        db.add(StockMove(product_id=pid, qty_change=round(final + sold, 3), kind="restock",
                         ref="seed:opening", at=open_at, note="opening stock"))
        exp = today + timedelta(days=prod["expiry_days"]) if prod["expiry_days"] else None
        if pid == 3:  # Surf: two batches (FIFO demo)
            specs = [(5, today + timedelta(days=150), "SE2608A"), (10, exp, "SE2609B")]
        else:
            specs = [(final, exp, f"B{pid:03d}")]
        for qty, expiry, batch_no in specs:
            db.add(StockBatch(product_id=pid, qty=qty, batch_no=batch_no, expiry=expiry,
                              cost_price=float(prod["cost"]), supplier_id=prod["supplier"],
                              received_at=open_at + timedelta(days=30)))
            batches += 1
    db.add_all(hb.moves)

    # --- khata ledgers ---
    for c in CUSTOMERS:
        if c["id"] == 1:
            continue
        db.add_all(_khata_entries(rng, customers[c["id"]], c["balance"], c.get("late", 0), today))

    # --- a confirmed distributor bill so the price guard has history (Surf last at Rs 42) ---
    bill_day = today - timedelta(days=14)
    bill = PurchaseBill(supplier_id=1, bill_no="RD/2526/4102", bill_date=bill_day, status="confirmed",
                        total=0.0, flags=[], created_at=datetime(bill_day.year, bill_day.month, bill_day.day, 10))
    rows = [(3, 20, 42.0, 45.0, "Buy 10 Get 1 Free", 2), (1, 48, 11.0, 12.0, "", 0),
            (5, 24, 41.0, 45.0, "", 0), (9, 60, 8.6, 10.0, "", 0), (10, 24, 31.0, 35.0, "", 0)]
    for pid, qty, rate, mrp, scheme, free in rows:
        bill.items.append(PurchaseItem(
            product_id=pid, name_raw=_p(pid)["name"], qty=qty, unit="packet", rate=rate, mrp=mrp,
            batch_no=f"OLD{pid:02d}", scheme_text=scheme, free_qty_expected=free,
            free_qty_received=free))
        bill.total += qty * rate
    db.add(bill)

    # --- missed sales: Kurkure asked six times this week ---
    for k in range(6):
        db.add(MissedSale(product_name="Kurkure", product_id=None,
                          at=now_dt - timedelta(days=k % 6, hours=2 + k)))
    db.add(MissedSale(product_name="Lays", product_id=None, at=now_dt - timedelta(days=2)))

    # --- recent cash closings (small diffs) ---
    cash_by_day: dict[date, float] = {}
    for p in hb.payments:
        if p.mode == "cash":
            cash_by_day[p.created_at.date()] = cash_by_day.get(p.created_at.date(), 0.0) + p.amount
    for days_ago, diff in ((7, 0), (6, -20), (5, 0), (4, 50), (3, 0), (2, -100), (1, 0)):
        day = today - timedelta(days=days_ago)
        expected = OPENING_FLOAT + cash_by_day.get(day, 0.0)
        db.add(CashClosing(day=day, expected=round(expected, 2), counted=round(expected + diff, 2),
                           denominations={}, diff=float(diff),
                           created_at=datetime(day.year, day.month, day.day, 21, 30)))

    db.commit()
    summary = {
        "seeded": True, "products": len(PRODUCTS), "customers": len(CUSTOMERS),
        "invoices": len(hb.invoices), "payments": len(hb.payments), "stock_batches": batches,
        "stock_moves": len(hb.moves) + len(PRODUCTS),
    }
    if verbose:
        print("Seeded Ramesh General Store, Laxmi Nagar:", summary)
    return summary


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
