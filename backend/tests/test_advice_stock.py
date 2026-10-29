"""Stock views, missed-sale leaderboard, expiry claims and dashboard v2."""
import pytest

from services.clock import today_local
from tests.test_advice_common import make_client_fixture

client = make_client_fixture()


def by_name(rows, name):
    return next(r for r in rows if r["name"] == name)


def test_stock_list_is_rich(client):
    j = client.get("/api/stock").json()
    assert j["count"] == 40 and len(j["items"]) == 40
    ghee = by_name(j["items"], "Amul Ghee 500ml")
    assert ghee["qty"] == 3 and ghee["days_of_cover"] == pytest.approx(2.0, abs=0.2)
    assert ghee["status"] == "medium" and ghee["unit"] == "pouch"
    assert ghee["last_cost_price"] is None and ghee["cost_price"] == 305
    assert ghee["margin_per_unit"] == 35 and ghee["margin_pct"] == pytest.approx(10.3, abs=0.1)
    assert ghee["batches"] and ghee["next_expiry"] and ghee["supplier_name"] == "Laxmi Festival Mart"
    surf = by_name(j["items"], "Surf Excel")
    assert len(surf["batches"]) == 2 and surf["last_cost_price"] == 42
    assert surf["batches"][0]["expiry"] <= surf["batches"][1]["expiry"]
    assert surf["margin_per_unit"] == 3  # 45 - 42 (last distributor rate)
    assert j["summary"]["low_count"] == 3
    assert {"product_id", "qty", "threshold", "status", "days_of_cover", "batches", "next_expiry",
            "last_cost_price", "margin_pct", "stock_value"} <= set(ghee)


def test_stock_filters_and_sort(client):
    low = client.get("/api/stock", params={"status": "low"}).json()["items"]
    assert {r["name"] for r in low} == {"Tata Salt", "Aashirvaad Atta 5kg", "Vim Bar"}
    q = client.get("/api/stock", params={"q": "ghee"}).json()
    assert q["count"] == 1
    cov = client.get("/api/stock", params={"sort": "cover"}).json()["items"]
    covers = [r["days_of_cover"] for r in cov if r["days_of_cover"] is not None]
    assert covers == sorted(covers) and cov[0]["days_of_cover"] is not None


def test_cover_endpoint(client):
    j = client.get("/api/stock/cover", params={"max_days": 3}).json()
    names = [r["name"] for r in j["items"]]
    assert "Amul Ghee 500ml" in names
    assert all(r["days_of_cover"] <= 3 for r in j["items"])
    assert [r["days_of_cover"] for r in j["items"]] == sorted(r["days_of_cover"] for r in j["items"])


def test_expiry_lists_batches_with_claim(client):
    j = client.get("/api/stock/expiry").json()
    milk = by_name(j["items"], "Doodh")
    assert milk["days_left"] == 2 and milk["claim_amount"] == 40 * 28 == 1120
    assert "₹1,120 ka claim" in milk["suggested_action"] and "Sharma Dairy" in milk["suggested_action"]
    assert j["total_claim"] == pytest.approx(sum(r["claim_amount"] for r in j["items"]))
    assert [r["days_left"] for r in j["items"]] == sorted(r["days_left"] for r in j["items"])
    assert client.get("/api/stock/expiry", params={"days": 1}).json()["count"] == 0
    wide = client.get("/api/stock/expiry", params={"days": 120}).json()
    assert wide["count"] > j["count"]
    bread = by_name(client.get("/api/stock/expiry", params={"days": 3}).json()["items"], "Bread")
    assert "wapas karein" in bread["suggested_action"]


def test_missed_leaderboard(client):
    j = client.get("/api/stock/missed").json()
    top = j["items"][0]
    assert top["product_name"] == "Kurkure" and top["count"] == 6 and top["last_asked"]
    assert top["in_catalog"] is False and "6 baar" in top["suggestion"]
    assert j["total_asks"] == 7
    r = client.post("/api/stock/missed", json={"product_name": "kurkure"}).json()
    assert r["asked_this_week"] == 7
    assert client.get("/api/stock/missed").json()["items"][0]["count"] == 7
    m = client.post("/api/stock/missed", json={"product_name": "maggi"}).json()
    assert m["product_id"] == 1
    assert client.post("/api/stock/missed", json={"product_name": ""}).status_code == 422


def test_product_detail(client):
    j = client.get("/api/stock/product/20").json()
    assert j["name"] == "Amul Ghee 500ml" and j["qty"] == 3 and len(j["sales_30d"]) == 30
    assert j["sales_30d"][-1]["date"] == today_local().isoformat()
    assert j["supplier"]["name"] == "Laxmi Festival Mart" and j["recent_moves"]
    surf = client.get("/api/stock/product/3").json()
    assert surf["purchases"][0]["rate"] == 42 and len(surf["batches"]) == 2
    assert client.get("/api/stock/product/9999").status_code == 404


def test_set_prices(client):
    r = client.post("/api/stock/prices", json={"items": [{"name": "bread", "price": 50},
                                                         {"name": "zzzz unknown", "price": 5}]}).json()
    assert r["updated"][0]["old_price"] == 45 and r["updated"][0]["new_price"] == 50
    assert len(r["skipped"]) == 1
    assert by_name(client.get("/api/stock").json()["items"], "Bread")["price"] == 50
    assert client.post("/api/stock/prices", json={"items": []}).status_code == 422


def test_dashboard_v2(client):
    j = client.get("/api/dashboard/v2").json()
    today = today_local().isoformat()
    assert len(j["series"]) == 14 and j["series"][-1]["date"] == today and j["series"][-1]["partial"]
    assert [s["date"] for s in j["series"]] == sorted(s["date"] for s in j["series"])
    assert j["yesterday"]["sales"] == 8420 and j["yesterday"]["vs_last_week_pct"] == 12.0
    assert j["today"]["sales"] == 7270 == j["series"][-1]["total"]
    assert sum(h["total"] for h in j["hourly"]) == pytest.approx(7270)
    assert j["payment_split"]["cash"] == 4850 and j["payment_split"]["upi"] == 2420
    assert sum(j["payment_split"].values()) == pytest.approx(7270)
    assert set(j["payment_split"]) == {"cash", "upi", "khata", "postpaid", "card"}
    assert 5 < j["margin"]["margin_pct"] < 40 and j["today"]["margin"] == j["margin"]["margin"]
    assert len(j["top_items"]) == 5 and j["low_stock_count"] == 3
    assert j["udhaar"]["total_outstanding"] > 8000 and j["total_stock_value"] > 0


def test_legacy_dashboard_unchanged(client):
    d = client.get("/api/dashboard").json()
    assert set(d) == {"total_stock_value", "today_sales", "low_stock_count", "top_selling",
                      "recent_transactions"}
    assert d["today_sales"] == 7270.0
