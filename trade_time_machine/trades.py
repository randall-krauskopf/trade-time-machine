"""Turn ESPN trade activities into data.json trade records.

A trade's `weeks` are the completed weeks that end after the trade, so its
received players' points are counted from the week it happened onward. The
week containing the trade is included even if its games were underway, and
`trade_week` labels it so the UI can show it separately. Points always follow
the *originally received* players, even after they are traded again.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .game_weeks import from_epoch_ms, transaction_week, week_start
from .models import DiscordMessage, EspnActivity, EspnPlayer, Trade, TradeSide
from .receipts import trade_receipts

SENT = "TRADE_SENT"
RECEIVED = "TRADE_RECEIVED"


def is_trade(activity: EspnActivity) -> bool:
    return any(action == SENT for _, action, _, _ in activity.actions)


def trades_since(feed: list[EspnActivity], cutoff: datetime) -> list[EspnActivity]:
    return [activity for activity in feed if from_epoch_ms(activity.date) >= cutoff and is_trade(activity)]


def fetch_traded_players(league: Any, activities: list[EspnActivity]) -> dict[int, EspnPlayer]:
    """Season stats for every player sent in any of the trades, keyed by player ID."""
    player_ids = sorted(
        {
            player.playerId
            for activity in activities
            for _, action, player, _ in activity.actions
            if action == SENT and player is not None
        }
    )
    players = league.player_info(playerId=player_ids) if player_ids else []
    if not isinstance(players, list):
        players = [players]
    return {player.playerId: player for player in players if player is not None}


def build_trade(
    activity: EspnActivity,
    season: int,
    completed_weeks: list[int],
    players_by_id: dict[int, EspnPlayer],
    messages: list[DiscordMessage],
) -> Trade:
    traded_at = from_epoch_ms(activity.date)
    sides = _sides(activity, traded_at)
    weeks = [week for week in completed_weeks if traded_at < week_start(season, week + 1)]
    trade_week = next((week for week in weeks if traded_at >= week_start(season, week)), None)
    for side in sides:
        _score_side(side, weeks, players_by_id)
    names = [player["name"] for side in sides for player in side["sent"]]
    return {
        "id": f"{activity.date}-{'-'.join(str(side['team_id']) for side in sides)}",
        "traded_at": traded_at.isoformat(),
        "transaction_week": transaction_week(season, traded_at),
        "weeks": weeks,
        "trade_week": trade_week,
        "sides": sides,
        "receipts": trade_receipts(messages, traded_at, names),
    }


def _sides(activity: EspnActivity, traded_at: datetime) -> list[dict[str, Any]]:
    """Both teams' sent/received players, ordered by team ID."""
    sides: dict[int, dict[str, Any]] = {}
    for team, action, player, _ in activity.actions:
        if action not in {SENT, RECEIVED} or player is None:
            continue
        side = sides.setdefault(
            team.team_id,
            {
                "team_id": team.team_id,
                "team": team.team_name.strip(),
                "sent": [],
                "received": [],
            },
        )
        side["sent" if action == SENT else "received"].append({"id": player.playerId, "name": player.name})
    if len(sides) != 2:
        raise ValueError(f"Expected two teams in ESPN trade at {traded_at.isoformat()}.")
    return sorted(sides.values(), key=lambda side: side["team_id"])


def _score_side(side: TradeSide, weeks: list[int], players_by_id: dict[int, EspnPlayer]) -> None:
    """Add per-week points for each received player and the side's totals.

    A missing stat stays None (never 0), and any None makes the week's and the
    side's totals None too.
    """
    for received in side["received"]:
        player = players_by_id.get(received["id"])
        received["weeks"] = {}
        for week in weeks:
            week_stats = getattr(player, "stats", {}).get(week) if player else None
            value = week_stats.get("points") if isinstance(week_stats, dict) else None
            received["weeks"][str(week)] = round(float(value), 2) if value is not None else None
    side["weekly_points"] = {
        str(week): (
            round(sum(player["weeks"][str(week)] for player in side["received"]), 2)
            if all(player["weeks"][str(week)] is not None for player in side["received"])
            else None
        )
        for week in weeks
    }
    side["total_points"] = (
        (
            round(sum(side["weekly_points"].values()), 2)
            if all(score is not None for score in side["weekly_points"].values())
            else None
        )
        if weeks
        else None
    )
