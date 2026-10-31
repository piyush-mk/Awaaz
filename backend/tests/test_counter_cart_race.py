"""Two requests opening the same brand-new cart at once must both succeed (regression: HTTP 500)."""
from database import SessionLocal
from models import Cart as CartRow
from services import counter


def test_lost_race_on_new_cart_uses_the_winners_cart(monkeypatch):
    sid = "race-test-cart"
    other = SessionLocal()
    try:
        other.query(CartRow).filter(CartRow.id == sid).delete()
        other.add(CartRow(id=sid, lines=[], status="open"))  # the request that won the race
        other.commit()

        db = SessionLocal()
        try:
            real_get, calls = db.get, {"n": 0}

            def stale_get(model, ident, *a, **kw):
                calls["n"] += 1
                # the first lookup happens before the winner committed, so it sees nothing
                return None if calls["n"] == 1 else real_get(model, ident, *a, **kw)

            monkeypatch.setattr(db, "get", stale_get)
            cart = counter.get_cart(db, sid)  # used to raise UNIQUE constraint failed: carts.id
            assert cart.id == sid and cart.status == "open"
            assert calls["n"] == 2
        finally:
            db.close()
    finally:
        other.query(CartRow).filter(CartRow.id == sid).delete()
        other.commit()
        other.close()


def test_normal_new_cart_is_still_created():
    sid = "race-test-normal"
    db = SessionLocal()
    try:
        db.query(CartRow).filter(CartRow.id == sid).delete()
        db.commit()
        cart = counter.get_cart(db, sid)
        assert cart.id == sid and cart.lines == []
        db.rollback()
    finally:
        db.close()
