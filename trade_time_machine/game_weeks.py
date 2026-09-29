"""League calendar rules.

A *game week* (also called a transaction week) runs Tuesday 00:00 to the next
Tuesday 00:00 in the league time zone. Week 1 is special: it starts on the
Thursday after Labor Day. A *completed week* is any week before ESPN's
`current_week`; the in-progress week is never scored.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

LEAGUE_TIMEZONE = ZoneInfo("America/Chicago")


def week_start(year: int, week: int) -> datetime:
    """The first week begins Thursday; subsequent scoring weeks begin Tuesday."""
    september_first = date(year, 9, 1)
    labor_day = september_first + timedelta(days=(7 - september_first.weekday()) % 7)
    first_thursday = labor_day + timedelta(days=3)
    start = first_thursday if week == 1 else first_thursday + timedelta(days=5, weeks=week - 2)
    return datetime.combine(start, datetime.min.time(), LEAGUE_TIMEZONE)


def transaction_week(year: int, traded_at: datetime) -> int:
    """Bucket transactions into game weeks that turn over Tuesday at midnight."""
    week = 1
    while traded_at >= week_start(year, week + 1):
        week += 1
    return week


def local_midnight(day: date) -> datetime:
    """Start of `day` in the league time zone (used for the inclusive trade cutoff)."""
    return datetime.combine(day, datetime.min.time(), LEAGUE_TIMEZONE)


def completed_weeks(league: Any) -> list[int]:
    """Weeks with final scores. The week in progress is excluded even if some games ended."""
    return list(range(1, int(league.current_week)))


def from_epoch_ms(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp / 1000, UTC)
