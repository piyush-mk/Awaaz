"""Shared helpers for the advice tests (brief, reorder, munim, stock, admin). No tests here."""
import dataclasses
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import config
import main
import seed as seed_module
from services import festivals
from services.clock import today_local


def make_client_fixture():
    """Module-scoped TestClient that reseeds afterwards so mutations never leak."""

    @pytest.fixture(scope="module")
    def client():
        with TestClient(main.app) as c:
            yield c
        seed_module.seed(reset=True, verbose=False)

    return client


def real_dhanteras() -> dict:
    return next(f for f in festivals.load_festivals() if f["name"] == "Dhanteras")


def pin_dhanteras(monkeypatch, days_away: int = 8) -> None:
    """Make Dhanteras fall `days_away` days from today so tests keep passing after 6 Nov 2026.
    Diwali and the rest are dropped so only the pinned festival counts."""
    base = real_dhanteras()
    pinned = [{**base, "date": today_local() + timedelta(days=days_away)}]
    monkeypatch.setattr(festivals, "load_festivals", lambda: pinned)


def settings_with(**kw):
    return dataclasses.replace(config.settings, **kw)
