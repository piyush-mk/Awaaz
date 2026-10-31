"""WA_LIVE_RECIPIENTS: real WhatsApp delivery only goes to numbers on the allowlist.

Regression: the live smoke test tried to send real WhatsApp messages to the demo shop's made-up customer
numbers (98100 00002 and friends), which can belong to real people. With an allowlist they stay in the
simulator. No network, no keys.
"""
import dataclasses

import pytest

from services import whatsapp as wa

DEMO = "919810000002"        # a seeded demo customer
OWNER = "917856944245"       # the number the owner wants real messages on


def with_settings(monkeypatch, **kw):
    monkeypatch.setattr(wa, "settings", dataclasses.replace(wa.settings, **kw))


def live(monkeypatch, recipients=""):
    with_settings(monkeypatch, wa_token="t", wa_phone_number_id="123", wa_live_recipients=recipients)


def test_empty_allowlist_allows_everyone(monkeypatch):
    live(monkeypatch, "")
    assert wa.live_recipients() == set()
    assert wa.recipient_allowed(DEMO) and wa.recipient_allowed(OWNER)


def test_allowlist_blocks_numbers_not_on_it(monkeypatch):
    live(monkeypatch, "+91 78569 44245")
    assert wa.recipient_allowed(OWNER)
    assert wa.recipient_allowed("7856944245")            # same number written differently
    assert not wa.recipient_allowed(DEMO)
    assert not wa.recipient_allowed(None)
    assert not wa.recipient_allowed("not a number")


def test_several_numbers_and_messy_input(monkeypatch):
    live(monkeypatch, " 917856944245 , +91-98765-43210 ,, ")
    assert wa.live_recipients() == {"7856944245", "9876543210"}
    assert wa.recipient_allowed("09876543210")


def test_notify_to_a_demo_number_stays_in_the_simulator(db, monkeypatch):
    scheduled = []
    monkeypatch.setattr(wa, "_schedule", scheduled.append)
    live(monkeypatch, OWNER)
    msg = wa.notify(db, DEMO, "demo customer message")
    assert scheduled == []                                # nothing scheduled for real delivery
    assert msg.channel == "sim" and msg.status == "delivered"


def test_notify_to_an_allowed_number_is_sent_for_real(db, monkeypatch):
    scheduled = []
    monkeypatch.setattr(wa, "_schedule", scheduled.append)
    live(monkeypatch, OWNER)
    msg = wa.notify(db, OWNER, "real message")
    db.commit()                                           # real delivery is queued after the commit
    assert msg.status == "queued" and scheduled == [msg.id]


@pytest.mark.anyio
async def test_deliver_itself_refuses_a_number_not_on_the_list(db, monkeypatch):
    """Defence in depth: even if something calls deliver() directly, nothing leaves for a blocked number."""
    live(monkeypatch, OWNER)
    msg = wa.notify(db, DEMO, "x")
    db.commit()
    calls = []
    monkeypatch.setattr(wa.http, "client", lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(AssertionError("network used")))
    assert await wa.deliver(msg.id) is False
    assert calls == []
