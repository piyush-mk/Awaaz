"""F6 distributor bill scan: proposal flags, confirm, duplicate detection (fixture mode, no keys)."""
import pytest
from fastapi.testclient import TestClient

import main
import seed as seed_module
from database import SessionLocal
from models import Product, PurchaseBill, PurchaseItem, StockBatch, StockMove
from services import events, stock_ops

IMG = {"image": ("bill.jpg", b"fake-image-bytes", "image/jpeg")}


@pytest.fixture(scope="module")
def client():
    seed_module.seed(reset=True, verbose=False)
    with TestClient(main.app) as c:
        yield c
    seed_module.seed(reset=True, verbose=False)


def _line(proposal, fragment):
    return next(ln for ln in proposal["lines"] if fragment in ln["name_raw"])


def _codes(line):
    return {f["code"] for f in line["flags"]}


def test_scan_requires_an_image(client):
    assert client.post("/api/purchases/scan").status_code == 422
    r = client.post("/api/purchases/scan", files={"image": ("e.jpg", b"", "image/jpeg")})
    assert r.status_code == 400


def test_scan_flags_price_scheme_expiry_and_new_item(client):
    r = client.post("/api/purchases/scan", files=IMG)
    assert r.status_code == 200
    p = r.json()
    assert p["source"] == "fixture" and p["demo_mode"] is True and p["latency_ms"] == 0
    assert p["kind"] == "purchase_bill" and p["status"] == "proposed" and p["action_id"]
    assert p["supplier"]["name"] == "Rajesh Distributors" and p["supplier"]["supplier_id"] == 1
    assert p["duplicate"]["is_duplicate"] is False
    assert len(p["lines"]) == 13

    surf = _line(p, "Surf")
    assert surf["product_id"] == 3 and surf["previous_rate"] == 42 and surf["rate"] == 45
    assert surf["rate_delta"] == 3 and {"price_increase", "scheme_missed"} <= _codes(surf)
    miss = next(f for f in surf["flags"] if f["code"] == "scheme_missed")
    assert miss["expected"] == 1 and miss["received"] == 0
    assert surf["free_qty_expected"] == 1 and surf["free_qty_received"] == 0

    bourn = _line(p, "Bournvita")
    assert bourn["product_id"] == 25 and "expiry_soon" in _codes(bourn)
    assert 0 <= bourn["days_to_expiry"] <= 60

    lays = _line(p, "Lays")
    assert lays["product_id"] is None and lays["is_new_candidate"] is True
    assert "new_product" in _codes(lays) and lays["new_product"]["mrp"] == 20

    # unchanged-rate lines are clean
    assert not ({"price_increase", "scheme_missed"} & _codes(_line(p, "Maggi")))

    s = p["summary"]
    assert s["price_increases"] == 1 and s["schemes_missed"] == 1 and s["new_products"] == 1
    assert s["expiring"] == 1 and s["matched"] == 12
    codes = {(f["code"], f.get("line_index")) for f in p["flags"]}
    assert ("price_increase", surf["index"]) in codes and ("scheme_missed", surf["index"]) in codes
    assert p["total"] == pytest.approx(sum(ln["line_total"] for ln in p["lines"]))
    msg = p["message_hi"]
    assert "Surf" in msg and "mehenga" in msg and "free packet nahi gina" in msg and "Bournvita" in msg


def test_confirm_commits_stock_cost_and_publishes(client):
    p = client.post("/api/purchases/scan", files=IMG).json()
    db = SessionLocal()
    try:
        before = stock_ops.current_stock(db, 3)
        moves_before = db.query(StockMove).filter(StockMove.kind == "restock").count()
        products_before = db.query(Product).count()
    finally:
        db.close()
    last_id = events.bus.replay("store")[-1]["id"] if events.bus.replay("store") else 0

    r = client.post(f"/api/purchases/{p['action_id']}/confirm")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "confirmed" and out["bill_id"]
    surf_update = next(u for u in out["stock_updates"] if u["product_id"] == 3)
    assert surf_update["added"] == 10 and surf_update["new_stock"] == before + 10
    assert out["new_products"] == []                    # new items need explicit confirmation
    assert len(out["stock_updates"]) == 12

    db = SessionLocal()
    try:
        assert stock_ops.current_stock(db, 3) == before + 10
        assert db.get(Product, 3).cost_price == 45
        assert db.query(Product).count() == products_before
        bill = db.get(PurchaseBill, out["bill_id"])
        assert bill.status == "confirmed" and bill.bill_no == "RD/2526/4471" and bill.supplier_id == 1
        assert len(bill.items) == 13
        surf_item = next(i for i in bill.items if i.product_id == 3)
        assert surf_item.prev_rate == 42 and surf_item.free_qty_expected == 1 and surf_item.free_qty_received == 0
        batch = db.query(StockBatch).filter(StockBatch.batch_no == "SE2609B", StockBatch.cost_price == 45).first()
        assert batch is not None and batch.supplier_id == 1 and batch.expiry is not None
        assert db.query(StockMove).filter(StockMove.kind == "restock").count() == moves_before + 12
        assert db.query(StockMove).filter(StockMove.ref == f"purchase:{bill.id}").count() == 12
    finally:
        db.close()

    new_events = [e for e in events.bus.replay("store", last_id) if e["type"] == "stock_updated"]
    assert new_events and new_events[-1]["data"]["reason"] == "purchase"
    assert any(x["product_id"] == 3 for x in new_events[-1]["data"]["products"])

    # confirming twice is refused
    assert client.post(f"/api/purchases/{p['action_id']}/confirm").status_code == 409

    # history + detail + suppliers
    hist = client.get("/api/purchases").json()
    assert hist[0]["id"] == out["bill_id"] and hist[0]["supplier"] == "Rajesh Distributors"
    detail = client.get(f"/api/purchases/{out['bill_id']}").json()
    assert len(detail["items"]) == 13
    sup = next(s for s in client.get("/api/purchases/suppliers").json() if s["id"] == 1)
    assert sup["bills"] >= 2 and sup["products"] > 0


def test_second_scan_of_same_bill_is_duplicate_and_price_now_matches(client):
    p = client.post("/api/purchases/scan", files=IMG).json()
    assert p["duplicate"]["is_duplicate"] is True and p["duplicate"]["bill_id"]
    assert any(f["code"] == "duplicate_bill" and f["severity"] == "error" for f in p["flags"])
    assert "pehle hi" in p["message_hi"]
    surf = _line(p, "Surf")
    assert surf["previous_rate"] == 45 and "price_increase" not in _codes(surf)   # history updated
    r = client.post(f"/api/purchases/{p['action_id']}/confirm")
    assert r.status_code == 409 and "already recorded" in r.json()["detail"]
    # cancel works on a proposal
    assert client.post(f"/api/purchases/{p['action_id']}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/purchases/{p['action_id']}/confirm").status_code == 409


def test_confirm_with_corrections_new_product_and_force(client):
    p = client.post("/api/purchases/scan", files=IMG).json()
    surf, lays = _line(p, "Surf"), _line(p, "Lays")
    db = SessionLocal()
    try:
        before = stock_ops.current_stock(db, 3)
        count = db.query(Product).count()
    finally:
        db.close()
    body = {"force": True, "lines": [
        {"index": surf["index"], "free_qty": 1},                       # the free packet did arrive
        {"index": lays["index"], "create_product": True},
        {"index": _line(p, "Haldi")["index"], "skip": True}]}
    r = client.post(f"/api/purchases/{p['action_id']}/confirm", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["new_products"] and out["new_products"][0]["name"].startswith("Lays")
    assert next(u for u in out["stock_updates"] if u["product_id"] == 3)["added"] == 11
    assert out["items_recorded"] == 12
    db = SessionLocal()
    try:
        assert stock_ops.current_stock(db, 3) == before + 11
        assert db.query(Product).count() == count + 1
        lays_p = db.get(Product, out["new_products"][0]["product_id"])
        assert lays_p.cost_price == 17 and lays_p.mrp == 20
        assert stock_ops.current_stock(db, lays_p.id) == 24
        item = db.query(PurchaseItem).filter(PurchaseItem.bill_id == out["bill_id"],
                                             PurchaseItem.product_id == 3).one()
        assert not any(f["code"] == "scheme_missed" for f in item.flags)   # corrected -> no flag
    finally:
        db.close()


def test_bad_edits(client):
    p = client.post("/api/purchases/scan", files=IMG).json()
    r = client.post(f"/api/purchases/{p['action_id']}/confirm", json={"force": True, "lines": [{"index": 99}]})
    assert r.status_code == 422
    assert client.post("/api/purchases/99999/confirm").status_code == 404
