"""Static festival calendar (data/festivals.json) and demand multipliers."""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "festivals.json"


@lru_cache(maxsize=1)
def load_festivals() -> list[dict[str, Any]]:
    """All festivals sorted by date, each with `date` parsed to a date object."""
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))["festivals"]
    out = [{**f, "date": date.fromisoformat(f["date"])} for f in raw]
    return sorted(out, key=lambda f: f["date"])


def upcoming(today: date, horizon_days: int = 14) -> list[dict[str, Any]]:
    """Festivals from today up to `horizon_days` ahead, each with `days_away`."""
    end = today + timedelta(days=horizon_days)
    return [{**f, "days_away": (f["date"] - today).days}
            for f in load_festivals() if today <= f["date"] <= end]


def next_festival(today: date) -> Optional[dict[str, Any]]:
    found = upcoming(today, horizon_days=365)
    return found[0] if found else None


def multiplier(tags: list[str], festival: dict[str, Any]) -> float:
    """Highest multiplier among a product's festival tags (1.0 if none apply)."""
    mults = festival.get("multipliers", {})
    return max([float(mults[t]) for t in tags or [] if t in mults] or [1.0])


def product_multiplier(tags: list[str], today: date, horizon_days: int = 14) -> float:
    """Largest multiplier from any festival in the horizon (1.0 if none)."""
    return max([multiplier(tags, f) for f in upcoming(today, horizon_days)] or [1.0])
