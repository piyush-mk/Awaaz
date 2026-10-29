"""F8 reorder: per-supplier purchase orders and sending them over the WhatsApp outbox."""
import pytest

from models import Message, PendingAction
from services import events
from tests.test_advice_common import make_client_fixture, pin_dhanteras

client = make_client_fixture()


@pytest.fixture(autouse=True)
def festival(monkeypatch):
    pin_dhanteras(monkeypatch, 8)


def _order(orders, name):
    return next(o for o in orders if o["supplier_name"] == name)


def test_draft_puts_ghee_in_festival_supplier_po(client):
    r = client.post("/api/reorder/draft")
    assert r.status_code == 200
    j = r.json()
    laxmi = _order(j["orders"], "Laxmi Festival Mart")
    ghee = next(ln for ln in laxmi["lines"] if ln["name"].startswith("Amul Ghee"))
    assert ghee["multiplier"] == 4.0 and ghee["festival"] == "Dhanteras"
    assert "Dhanteras se pehle 4x demand" in ghee["reason"] and "2 din ka stock" in ghee["reason"]
    # need = 1.5/day x lead 3 x 4 + safety 6 - stock 3 = 21
    assert ghee["qty"] == 21 and ghee["current_stock"] == 3
    assert laxmi["total_est"] == pytest.approx(sum(ln["est_amount"] for ln in laxmi["lines"]), abs=0.01)
    rajesh = _order(j["orders"], "Rajesh Distributors")
    assert any(ln["name"] == "Maggi" for ln in rajesh["lines"])
    maggi = next(ln for ln in rajesh["lines"] if ln["name"] == "Maggi")
    assert maggi["qty"] % 12 == 0  # rounded to the carton pack size
    assert laxmi["status"] == "proposed" and laxmi["action_id"] > 0


def test_draft_is_stored_as_pending_action(client, db):
    j = client.post("/api/reorder/draft").json()
    ids = [o["action_id"] for o in j["orders"]]
    rows = db.query(PendingAction).filter(PendingAction.id.in_(ids)).all()
    assert {r.kind for r in rows} == {"purchase_order"} and {r.status for r in rows} == {"proposed"}
    listed = client.get("/api/reorder", params={"status": "proposed"}).json()
    assert set(ids) <= {o["action_id"] for o in listed["orders"]}


def test_redraft_cancels_older_drafts(client):
    first = client.post("/api/reorder/draft").json()
    old = _order(first["orders"], "Laxmi Festival Mart")["action_id"]
    second = client.post("/api/reorder/draft", json={"supplier_id": 4}).json()
    assert [o["supplier_name"] for o in second["orders"]] == ["Laxmi Festival Mart"]
    assert client.post(f"/api/reorder/{old}/send").status_code == 409


def test_send_creates_supplier_message(client, db):
    order = _order(client.post("/api/reorder/draft").json()["orders"], "Laxmi Festival Mart")
    last = max([e["id"] for e in events.bus.replay("store")] or [0])
    r = client.post(f"/api/reorder/{order['action_id']}/send",
                    json={"edits": [{"product_id": 20, "qty": 24}], "note": "Subah tak bhej dein"})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "sent" and j["message"]["supplier_id"] == 4
    assert j["message"]["to"] == "919810000104"
    body = j["message"]["body"]
    assert "Amul Ghee 500ml: 24 pouch" in body and "Dhanteras" in body and "Subah tak bhej dein" in body
    msg = db.get(Message, j["message"]["id"])
    assert msg is not None and msg.supplier_id == 4 and msg.direction == "out"
    assert j["order"]["status"] == "confirmed"
    assert next(ln for ln in j["order"]["lines"] if ln["product_id"] == 20)["qty"] == 24
    assert [e for e in events.bus.replay("store", last) if e["type"] == "reorder_sent"]
    assert client.post(f"/api/reorder/{order['action_id']}/send").status_code == 409
    sent = client.get("/api/reorder", params={"status": "confirmed"}).json()["orders"]
    assert any(o["action_id"] == order["action_id"] for o in sent)


def test_send_validation(client):
    assert client.post("/api/reorder/99999/send").status_code == 404
    order = _order(client.post("/api/reorder/draft").json()["orders"], "Rajesh Distributors")
    only = [{"product_id": ln["product_id"], "qty": 0} for ln in order["lines"]]
    assert client.post(f"/api/reorder/{order['action_id']}/send", json={"edits": only}).status_code == 422
    assert client.post(f"/api/reorder/{order['action_id']}/send",
                       json={"edits": [{"product_id": 9999, "qty": 1}]}).status_code == 404
