"""Assemble one league's section of data.json."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from espn_api.requests.espn_requests import ESPNAccessDenied

from .espn_source import fetch_activity_feed, fetch_reconstructed_trades
from .game_weeks import completed_weeks, local_midnight
from .models import DiscordMessage, LeagueSnapshot
from .standings import alternate_standings
from .trades import build_trade, fetch_traded_players, trades_since
from .weekly_moves import weekly_roster_moves


def build_snapshot(league: Any, messages: list[DiscordMessage], first_trade_date: date) -> LeagueSnapshot:
    try:
        feed = fetch_activity_feed(league)
        source = "activity"
    except ESPNAccessDenied:
        # The activity feed is member-only; the transactions and roster views are readable.
        feed = fetch_reconstructed_trades(league)
        source = "reconstructed"
    activities = trades_since(feed, local_midnight(first_trade_date))
    players_by_id = fetch_traded_players(league, activities)
    weeks = completed_weeks(league)
    trades = [build_trade(activity, league.year, weeks, players_by_id, messages) for activity in activities]

    # Test doubles without box scores skip the standings and weekly stages.
    if hasattr(league, "box_scores"):
        standings = alternate_standings(league, trades, first_trade_date)
        roster_moves = weekly_roster_moves(league, trades, players_by_id)
    else:
        standings = None
        roster_moves = None

    return {
        "league": league.settings.name,
        "season": league.year,
        "generated_at": datetime.now(UTC).isoformat(),
        "completed_weeks": weeks,
        "first_trade_date": first_trade_date.isoformat(),
        "trades": trades,
        "alternate_standings": standings,
        "weekly_roster_moves": roster_moves,
        "source": source,
        "discord_imported": bool(messages),
    }
