"""F12 parchi and the shelf-audit upgrade (fixture mode, no keys)."""
import pytest
from fastapi.testclient import TestClient

import main
import seed as seed_module
from database import SessionLocal
from models import StockMove
from routers import photo
from services import catalog, stock_ops
from services.types import Result

IMG = ("shelf.jpg", b"fake", "image/jpeg")


@pytest.fixture(scope="module")
def client():
    seed_module.seed(reset=True, verbose=False)
    with TestClient(main.app) as c:
        yield c
    seed_module.seed(reset=True, verbose=False)


def test_parchi_fixture_matches_lines_and_unmatched(client):
    assert client.post("/api/photo/parchi").status_code == 422
    r = client.post("/api/photo/parchi", files={"image": IMG})
    assert r.status_code == 200
    out = r.json()
    assert out["source"] == "fixture" and out["demo_mode"] is True and out["latency_ms"] == 0
    by_name = {ln["name"]: ln for ln in out["lines"]}
    assert set(by_name) == {"Maggi", "Cheeni", "Surf Excel", "Dal", "Doodh"}
    assert by_name["Maggi"]["qty"] == 2 and by_name["Maggi"]["line_total"] == 24
    assert by_name["Cheeni"]["qty"] == 1 and by_name["Cheeni"]["unit"] == "kg"
    assert by_name["Cheeni"]["sell_mode"] == "loose" and by_name["Cheeni"]["weigh_instruction"] == "1 kilo tolo"
    assert by_name["Dal"]["qty"] == 0.5 and by_name["Dal"]["weigh_instruction"] == "500 gram tolo"
    assert by_name["Dal"]["line_total"] == 70
    assert by_name["Surf Excel"]["product_id"] == 3 and "from_parchi" in by_name["Surf Excel"]["flags"]
    # CartLine shape the counter uses
    assert set(by_name["Maggi"]) >= {"product_id", "name", "name_hi", "qty", "unit", "sell_mode",
                                     "base_unit", "unit_price", "line_total", "gst_rate", "flags", "raw"}
    assert [u["name"] for u in out["unmatched"]] == ["kurkure"]
    assert out["total"] == pytest.approx(sum(ln["line_total"] for ln in out["lines"]))
    assert len(out["items_read"]) == 6 and "kurkure" in out["message_hi"]


def test_parchi_service_merges_duplicates_and_units(db):
    from services import parchi
    lines, unmatched = parchi.parse_rows(
        [{"name": "maggi", "qty": 2, "unit": "packet"}, {"name": "maggi", "qty": 3, "unit": ""},
         {"name": "tel", "qty": 500, "unit": "ml"}, {"name": "chawal", "qty": 2, "unit": "kilo"},
         {"name": "Surf Excel Easy Wash", "qty": 1, "unit": "pkt"}, {"name": "xyzzy", "qty": 1, "unit": ""}],
        catalog.load_index(db))
    by = {ln.name: ln for ln in lines}
    assert by["Maggi"].qty == 5 and by["Maggi"].line_total == 60
    assert by["Sarson Tel"].qty == 0.5 and by["Chawal"].qty == 2
    assert by["Surf Excel"].qty == 1
    assert [u["name"] for u in unmatched] == ["xyzzy"]


def test_legacy_parse_shape_and_dedupe(client):
    r = client.post("/api/photo/parse", files={"image": IMG}).json()
    assert r["demo_mode"] is True and r["source"] == "fixture"
    assert {i["name"] for i in r["items"]} == {"Maggi", "Parle-G", "Colgate", "Surf Excel"}
    assert set(r["items"][0]) == {"product_id", "name", "name_hi", "quantity", "unit", "price", "gst_rate"}


def test_aggregate_frames_takes_max_across_frames_and_sums_within(db):
    idx = catalog.load_index(db)
    frames = [
        [{"name": "Maggi noodles", "quantity": 5}, {"name": "Colgate", "quantity": 3}],
        [{"name": "Maggi", "quantity": 8}, {"name": "Surf Excel", "quantity": 2}, {"name": "Lays", "quantity": 2}],
        [{"name": "Maggi", "quantity": 6}, {"name": "Colgate", "quantity": 1}, {"name": "Colgate paste", "quantity": 2},
         {"name": "lays", "quantity": 4}],
    ]
    agg = photo.aggregate_frames(frames, idx)
    assert agg["counts"] == {1: 8.0, 5: 3.0, 3: 2.0}     # Colgate frame3 = 1 + 2 = 3, max(3, 3)
    assert agg["unmatched"] == {"Lays": 4.0}
    assert len(agg["per_frame"]) == 3


def test_shelf_audit_three_frames_variance_and_confirm(client, monkeypatch):
    # book stock (seed): Maggi 12, Colgate 12, Surf 15, Parle-G 20, cost 11 / 41 / 42 / 8.6
    per_frame = iter([
        [{"name": "Maggi", "quantity": 4}, {"name": "Colgate", "quantity": 12}],
        [{"name": "Maggi", "quantity": 9}, {"name": "Surf Excel", "quantity": 10}, {"name": "Cheeni", "quantity": 3}],
        [{"name": "Maggi", "quantity": 7}, {"name": "Parle-G", "quantity": 25}, {"name": "Kurkure", "quantity": 4}],
    ])

    async def fake(data, mime, task):
        return Result(next(per_frame), "openrouter", 5)

    monkeypatch.setattr(photo.vision, "extract_json_from_image", fake)
    files = [("images", (f"f{i}.jpg", b"frame", "image/jpeg")) for i in range(3)]
    r = client.post("/api/photo/shelf-audit", files=files)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["frames"] == 3 and out["frames_read"] == 3 and out["source"] == "openrouter"
    assert out["demo_mode"] is False and "latency_ms" in out and out["status"] == "proposed"
    rows = {x["name"]: x for x in out["rows"]}
    assert rows["Maggi"]["counted"] == 9 and rows["Maggi"]["expected"] == 12      # max(4, 9, 7)
    assert rows["Maggi"]["variance"] == -3 and rows["Maggi"]["variance_value"] == -33
    assert rows["Surf Excel"]["variance"] == -5 and rows["Surf Excel"]["variance_value"] == -210
    assert rows["Colgate"]["variance_value"] == 0 and rows["Colgate"]["status"] == "ok"
    assert rows["Parle-G"]["status"] == "excess" and rows["Parle-G"]["variance"] == 5
    assert [s["name"] for s in out["skipped"]] == ["Cheeni"]                       # loose goods are not counted
    assert out["unmatched"] == [{"name": "Kurkure", "counted": 4.0}]
    t = out["totals"]
    assert t["loss_value"] == -243 and t["gain_value"] == pytest.approx(43) and t["short"] == 2 and t["excess"] == 1
    assert t["total_variance_value"] == pytest.approx(-200)
    assert "nuksaan" in out["message_hi"]

    db = SessionLocal()
    try:
        assert stock_ops.current_stock(db, 1) == 12
    finally:
        db.close()
    c = client.post(f"/api/photo/shelf-audit/{out['action_id']}/confirm", json={"counts": {"1": 10}})
    assert c.status_code == 200, c.text
    done = c.json()
    adj = {a["name"]: a for a in done["adjustments"]}
    assert adj["Maggi"]["new_stock"] == 10 and adj["Maggi"]["change"] == -2        # corrected count wins
    assert adj["Surf Excel"]["change"] == -5 and adj["Parle-G"]["change"] == 5 and "Colgate" not in adj
    db = SessionLocal()
    try:
        assert stock_ops.current_stock(db, 1) == 10
        assert stock_ops.current_stock(db, 3) == 10
        assert stock_ops.current_stock(db, 9) == 25
        moves = db.query(StockMove).filter(StockMove.ref == f"audit:{out['action_id']}").all()
        assert len(moves) == 3 and {m.kind for m in moves} == {"audit"}
    finally:
        db.close()
    assert client.post(f"/api/photo/shelf-audit/{out['action_id']}/confirm").status_code == 409
    assert client.post(f"/api/photo/shelf-audit/{out['action_id']}/cancel").status_code == 409


def test_shelf_audit_fixture_single_frame_and_cancel(client):
    assert client.post("/api/photo/shelf-audit").status_code == 422
    r = client.post("/api/photo/shelf-audit", files={"image": IMG})
    assert r.status_code == 200
    out = r.json()
    assert out["source"] == "fixture" and out["demo_mode"] is True and out["frames"] == 1
    assert {x["name"] for x in out["rows"]} == {"Maggi", "Parle-G", "Colgate", "Surf Excel"}
    assert out["totals"]["loss_value"] < 0
    assert client.post(f"/api/photo/shelf-audit/{out['action_id']}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/photo/shelf-audit/{out['action_id']}/confirm").status_code == 409
    assert client.post("/api/photo/shelf-audit/9999/confirm").status_code == 404
