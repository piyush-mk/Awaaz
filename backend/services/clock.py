"""Store-local time. The database stores naive datetimes in India Standard Time
so that "today" and "yesterday" match what the shopkeeper sees on the wall."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_local() -> datetime:
    """Current time in IST as a naive datetime."""
    return datetime.now(IST).replace(tzinfo=None)


def today_local() -> date:
    return now_local().date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of a local calendar day."""
    start = datetime(day.year, day.month, day.day)
    return start, start + timedelta(days=1)
