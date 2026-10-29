"""Sanity of the Ramesh General Store scenario against the deck's numbers."""
from datetime import timedelta

import pytest
from sqlalchemy import func

from models import (Customer, Invoice, KhataEntry, MissedSale, Product, PurchaseItem,
                    StockBatch, StockMove, StoreProfile, Supplier)
from services import cash, festivals, quantity, stock_ops
from services.clock import day_bounds, today_local


def day_total(db, day):
    a, b = day_bounds(day)
    return db.query(func.sum(Invoice.total)).filter(Invoice.created_at >= a, Invoice.created_at < b).scalar()


def test_token_counts(db):
    assert db.query(Product).count() == 40
    assert db.query(Customer).count() >= 17
    assert db.query(Supplier).count() >= 3
    assert db.query(StoreProfile).one().name == "Ramesh General Store"
    assert db.query(Invoice).count() > 1500


def test_original_ten_keep_their_ids(db):
    names = {p.id: p.name for p in db.query(Product).filter(Product.id <= 10)}
    assert names[1] == "Maggi" and names[3] == "Surf Excel" and names[5] == "Colgate"
    assert names[10] == "Dettol Soap" and len(names) == 10


def test_demo_cart_is_249(db):
    lines = quantity.parse_order("do maggi ek surf excel chaar colgate", db)
    assert sum(ln.line_total for ln in lines) == 249.0


def test_cheeni_is_44_per_kg_and_kurkure_absent(db):
    cheeni = db.query(Product).filter(Product.name == "Cheeni").one()
    assert cheeni.loose_price_per_base == 44 and cheeni.sell_mode == "loose" and cheeni.base_unit == "kg"
    assert db.query(Product).filter(Product.name.ilike("%kurkure%")).count() == 0
    assert db.query(MissedSale).filter(MissedSale.product_name == "Kurkure").count() == 6


def test_gst2_rates_seeded(db):
    rate = {p.name: p.gst_rate for p in db.query(Product)}
    assert rate["Maggi"] == 5 and rate["Colgate"] == 5 and rate["Dettol Soap"] == 5
    assert rate["Surf Excel"] == 18 and rate["Tata Salt"] == 0 and rate["Patanjali Honey"] == 5
    assert 12 not in rate.values() and 28 not in rate.values()


def test_yesterday_sales_8420_and_up_12_percent(db):
    today = today_local()
    assert day_total(db, today - timedelta(days=1)) == 8420
    assert day_total(db, today - timedelta(days=8)) == 7518
    assert round(8420 / day_total(db, today - timedelta(days=8)), 2) == 1.12


def test_forty_five_days_of_history_with_weekday_pattern(db):
    today = today_local()
    totals = {d: day_total(db, today - timedelta(days=d)) for d in range(1, 46)}
    assert all(v and v > 3000 for v in totals.values())
    weekend = [v for d, v in totals.items() if (today - timedelta(days=d)).weekday() == 5 and d not in (1, 8)]
    monday = [v for d, v in totals.items() if (today - timedelta(days=d)).weekday() == 0]
    assert sum(weekend) / len(weekend) > sum(monday) / len(monday)


def test_last_year_dhanteras_spike(db):
    from datetime import date
    spike = db.query(func.sum(StockMove.qty_change)).filter(
        StockMove.product_id == 20, StockMove.kind == "sale",
        StockMove.at >= date(2025, 10, 16), StockMove.at < date(2025, 10, 20)).scalar()
    normal = db.query(func.sum(StockMove.qty_change)).filter(
        StockMove.product_id == 20, StockMove.kind == "sale",
        StockMove.at >= today_local() - timedelta(days=4)).scalar()
    assert -spike > 3 * -normal


def test_galla_expected_6850(db):
    assert db.query(StoreProfile).one().opening_float == 2000
    assert cash.expected_cash(db) == 6850.0


def test_stock_levels_and_alerts(db):
    assert stock_ops.current_stock(db, 5) == 12  # Colgate
    low = {p.name for p in db.query(Product) if stock_ops.current_stock(db, p.id) <= p.threshold}
    assert low == {"Tata Salt", "Aashirvaad Atta 5kg", "Vim Bar"}


def test_ghee_has_two_days_of_cover(db):
    assert stock_ops.days_of_cover(db, 20) == pytest.approx(2.0, abs=0.2)


def test_ledger_reconciles_with_batches(db):
    for p in db.query(Product):
        moves = db.query(func.coalesce(func.sum(StockMove.qty_change), 0.0)).filter(
            StockMove.product_id == p.id).scalar()
        assert moves == pytest.approx(stock_ops.current_stock(db, p.id), abs=1e-6)


def test_verma_ji_khata(db):
    verma = db.query(Customer).filter(Customer.name == "Verma ji").one()
    assert verma.balance == 850 and verma.late_payments == 3
    total = db.query(func.sum(KhataEntry.amount)).filter(KhataEntry.customer_id == verma.id).scalar()
    assert total == 850


def test_sharma_ji_usual_basket(db):
    sharma = db.query(Customer).filter(Customer.name == "Sharma ji").one()
    assert {b["product_id"] for b in sharma.usual_basket} == {16, 17, 19}


def test_surf_last_bought_at_42_from_rajesh(db):
    item = (db.query(PurchaseItem).filter(PurchaseItem.product_id == 3)
            .order_by(PurchaseItem.id.desc()).first())
    assert item.rate == 42.0 and item.bill.supplier.name == "Rajesh Distributors"


def test_invoice_integrity(db):
    for inv in db.query(Invoice).limit(300):
        assert round(inv.taxable_total + inv.cgst_total + inv.sgst_total, 2) == inv.total
        assert round(sum(i.total for i in inv.items), 2) == inv.total
        paid = sum(p.amount for p in inv.payments if p.status == "success")
        assert round(paid, 2) == inv.total
    numbers = [n for (n,) in db.query(Invoice.number).all()]
    assert len(numbers) == len(set(numbers))


def test_surf_has_two_fifo_batches(db):
    assert db.query(StockBatch).filter(StockBatch.product_id == 3).count() == 2


def test_festival_calendar():
    names = {f["name"]: f for f in festivals.load_festivals()}
    assert str(names["Dhanteras"]["date"]) == "2026-11-06" and str(names["Diwali"]["date"]) == "2026-11-08"
    assert names["Dhanteras"]["multipliers"]["ghee"] >= 3


def test_seed_is_idempotent():
    import seed
    assert seed.seed(verbose=False) == {"seeded": False}
