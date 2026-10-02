"""Alternate Universe standings: what if no trade had ever happened?

For each completed week:

1. Take every team's actual weekly roster from the box scores.
2. *Rewind* trades: move each traded player back to the team that owned him
   before his first trade, unless a later waiver/free-agent pickup started a
   new ownership chain (those moves are real and kept).
3. Score both worlds with the *optimal* lineup, so lineup-setting skill does
   not muddy the comparison, and replay every matchup.

`wins_change` = alternate wins - optimal actual wins, with ties counting as half.

Each week also records every manager's *lineup gap*: the best possible score
from that week's actual starters and bench (IR excluded) minus the points
their starters actually scored, i.e. the points left on the bench.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from .espn_source import fetch_transactions, is_executed_acquisition
from .game_weeks import completed_weeks, from_epoch_ms, local_midnight, week_start
from .lineups import (
    BENCH_SLOT,
    STARTER_EXCLUDED_SLOTS,
    box_player,
    matchup_result,
    optimal_lineup_points,
    starting_slots,
)
from .models import AlternateStandings, LineupGap, LineupPlayer, StandingsRow, Trade

OwnershipEvent = tuple[datetime, Literal["trade", "add"], int]
"""(when, kind, team). For "trade" the team is the *sender*; for "add" the acquiring team."""
Roster = dict[int, LineupPlayer]
Matchup = tuple[int, int, float, float]
"""(home team, away team, home score, away score)."""

OUTCOME_COLUMN = {"W": "wins", "L": "losses", "T": "ties"}


def alternate_standings(league: Any, trades: list[Trade], first_trade_date: date) -> AlternateStandings:
    """Rewind known trade transfers in weekly rosters, preserving actual waiver/FA moves."""
    slots = starting_slots(league)
    events = ownership_events(league, trades, local_midnight(first_trade_date))
    teams = {team.team_id: team.team_name.strip() for team in league.teams}
    standings = {team_id: _empty_row(team_id, name) for team_id, name in teams.items()}
    week_details = []
    for week in completed_weeks(league):
        rosters, matchups = weekly_rosters(league, week, set(teams))
        alternates, rewound = rewind_trades(rosters, events, week_start(league.year, week + 1))
        optimal_actual = _best_scores(rosters, slots)
        alternate = _best_scores(alternates, slots)
        for team_id in rosters:
            standings[team_id]["optimal_actual_points"] += optimal_actual[team_id]
            standings[team_id]["alternate_points"] += alternate[team_id]
        for home, away, home_score, away_score in matchups:
            for team_id, score, rival, rival_score in (
                (home, home_score, away, away_score),
                (away, away_score, home, home_score),
            ):
                row = standings[team_id]
                row["actual_points"] += score
                _record(row, "actual", matchup_result(score, rival_score))
                _record(row, "optimal_actual", matchup_result(optimal_actual[team_id], optimal_actual[rival]))
                _record(row, "alternate", matchup_result(alternate[team_id], alternate[rival]))
        lineups = [lineup_gap(team_id, teams[team_id], rosters[team_id], slots) for team_id in sorted(rosters)]
        week_details.append(
            {
                "week": week,
                "rewound_players": rewound,
                "lineups": lineups,
                "matchups": [
                    {
                        "home_team_id": home,
                        "away_team_id": away,
                        "home_score": home_score,
                        "away_score": away_score,
                    }
                    for home, away, home_score, away_score in matchups
                ],
            }
        )
    for row in standings.values():
        for key in ("actual_points", "alternate_points", "optimal_actual_points"):
            row[key] = round(row[key], 2)
        row["wins_change"] = (row["alternate_wins"] + row["alternate_ties"] / 2) - (
            row["optimal_actual_wins"] + row["optimal_actual_ties"] / 2
        )
    return {"weeks": week_details, "teams": list(standings.values()), "source": "weekly_box_scores"}


def lineup_gap(team_id: int, team: str, roster: Roster, slots: list[str]) -> LineupGap:
    """Points a manager left on the bench: best possible lineup minus the starters' actual points."""
    players = list(roster.values())
    starters = [player for player in players if player["slot"] not in STARTER_EXCLUDED_SLOTS]
    actual = round(sum(float(player["points"]) for player in starters), 2)
    optimal = optimal_lineup_points([player for player in players if player["slot"] != "IR"], slots)
    bench = [player for player in players if player["slot"] == BENCH_SLOT]
    top = max(bench, key=lambda player: (player["points"], -player["id"]), default=None)
    return {
        "team_id": team_id,
        "team": team,
        "actual_points": actual,
        "optimal_points": optimal,
        "points_left": max(0.0, round(optimal - actual, 2)),
        "top_bench": {"id": top["id"], "name": top["name"], "points": top["points"]} if top else None,
    }


def ownership_events(league: Any, trades: list[Trade], cutoff: datetime) -> dict[int, list[OwnershipEvent]]:
    """Each player's trades and waiver/FA pickups since the cutoff, oldest first."""
    events: dict[int, list[OwnershipEvent]] = {}
    for trade in trades:
        traded_at = datetime.fromisoformat(trade["traded_at"])
        for side in trade["sides"]:
            for player in side["sent"]:
                events.setdefault(player["id"], []).append((traded_at, "trade", side["team_id"]))
    # ESPN's executed waiver/FA records tell us when a player entered a new ownership chain.
    for transaction in fetch_transactions(league):
        if not is_executed_acquisition(transaction):
            continue
        timestamp = transaction.get("processDate") or transaction.get("proposedDate")
        if not timestamp:
            raise ValueError(f"Executed acquisition {transaction['id']} has no timestamp.")
        when = from_epoch_ms(timestamp)
        if when < cutoff:
            continue
        for item in transaction.get("items", []):
            if item.get("type") == "ADD" and item.get("playerId") is not None:
                events.setdefault(item["playerId"], []).append((when, "add", item["toTeamId"]))
    for history in events.values():
        history.sort(key=lambda event: event[0])
    return events


def weekly_rosters(league: Any, week: int, team_ids: set[int]) -> tuple[dict[int, Roster], list[Matchup]]:
    """Every team's full roster (starters and bench) and the week's matchups, validated."""
    rosters: dict[int, Roster] = {}
    matchups: list[Matchup] = []
    for box in league.box_scores(week):
        home_id, away_id = box.home_team.team_id, box.away_team.team_id
        if home_id not in team_ids or away_id not in team_ids:
            raise ValueError(f"Week {week} box score has an unknown team.")
        matchups.append((home_id, away_id, float(box.home_score), float(box.away_score)))
        for team_id, lineup in ((home_id, box.home_lineup), (away_id, box.away_lineup)):
            if team_id in rosters:
                raise ValueError(f"Week {week} has duplicate box scores for team {team_id}.")
            rosters[team_id] = {player.playerId: box_player(player) for player in lineup}
    if set(rosters) != team_ids:
        raise ValueError(f"Week {week} is missing box scores for some teams.")
    return rosters, matchups


def rewind_trades(
    rosters: dict[int, Roster], events: dict[int, list[OwnershipEvent]], week_end: datetime
) -> tuple[dict[int, Roster], int]:
    """Return the no-trade rosters for a week and how many players moved back.

    A player's *origin* is the team that held him before his first trade in
    the current ownership chain; a waiver/FA pickup starts a new chain.
    """
    alternates = {team_id: dict(roster) for team_id, roster in rosters.items()}
    moved = 0
    for player_id, history in events.items():
        actual_owner = next((team_id for team_id, roster in rosters.items() if player_id in roster), None)
        if actual_owner is None:
            continue
        origin = None
        has_trade = False
        for when, kind, owner in history:
            if when >= week_end:
                break
            if kind == "add":
                origin, has_trade = owner, False
            elif origin is None:
                origin, has_trade = owner, True
            else:
                has_trade = True
        if has_trade and origin in alternates and actual_owner != origin:
            alternates[origin][player_id] = alternates[actual_owner].pop(player_id)
            moved += 1
    return alternates, moved


def _best_scores(rosters: dict[int, Roster], slots: list[str]) -> dict[int, float]:
    return {team_id: optimal_lineup_points(list(roster.values()), slots) for team_id, roster in rosters.items()}


def _empty_row(team_id: int, name: str) -> dict[str, Any]:
    row: dict[str, Any] = {"team_id": team_id, "team": name}
    for world in ("actual", "alternate", "optimal_actual"):
        row.update({f"{world}_wins": 0, f"{world}_losses": 0, f"{world}_ties": 0, f"{world}_points": 0.0})
    return row


def _record(row: StandingsRow | dict[str, Any], world: str, outcome: str) -> None:
    row[f"{world}_{OUTCOME_COLUMN[outcome]}"] += 1
