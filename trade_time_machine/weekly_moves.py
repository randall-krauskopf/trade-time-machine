"""Weekly Moves: grade each manager's combined trades within one game week.

All of a manager's trades in the same game week are *bundled*. Players who
arrive and leave within the week cancel out, so only net arrivals and net
departures matter. The no-trade score comes from `refill_lineup`: remove net
arrivals from the lineup and back-fill by projection, including net departures.
The opponent's no-trade score is used when they traded that week too.
"""

from __future__ import annotations

from typing import Any

from .game_weeks import completed_weeks
from .lineups import BENCH_SLOT, STARTER_EXCLUDED_SLOTS, box_player, matchup_result, refill_lineup
from .models import EspnPlayer, LineupEstimate, Trade, WeeklyRosterMoves, WeeklyRow

TeamWeek = dict[str, Any]
"""One team's box score: score, opponent_id, opponent name, starters, bench."""


def weekly_roster_moves(
    league: Any,
    trades: list[Trade],
    players_by_id: dict[int, EspnPlayer],
    *,
    unavailable_team_weeks: set[tuple[int, int]] | None = None,
    weeks: list[int] | None = None,
) -> WeeklyRosterMoves:
    """Grade each manager's combined trade activity within a Tuesday-to-Tuesday week."""
    rows: list[WeeklyRow] = []
    omitted = []
    for week in weeks if weeks is not None else completed_weeks(league):
        weekly_trades = [trade for trade in trades if trade["transaction_week"] == week]
        if not weekly_trades:
            continue
        bundles = bundle_trades(weekly_trades)
        boxes = team_weeks(league, week)
        alternates = {
            team_id: _no_trade_lineup(bundle, boxes[team_id], boxes, players_by_id, week)
            for team_id, bundle in bundles.items()
            if team_id in boxes and (week, team_id) not in (unavailable_team_weeks or set())
        }
        for team_id, bundle in bundles.items():
            box = boxes.get(team_id)
            alternate = alternates.get(team_id)
            opponent_id = box["opponent_id"] if box else None
            if (
                box is None
                or alternate is None
                or opponent_id not in boxes
                or (week, opponent_id) in (unavailable_team_weeks or set())
            ):
                if unavailable_team_weeks is not None:
                    omitted.append({"week": week, "team_id": team_id})
                continue
            opponent_box = boxes[box["opponent_id"]]
            opponent_alternate = alternates.get(box["opponent_id"], {}).get(
                "alternate", {"score": opponent_box["score"]}
            )["score"]
            actual_result = matchup_result(box["score"], opponent_box["score"])
            alternate_result = matchup_result(alternate["alternate"]["score"], opponent_alternate)
            rows.append(
                {
                    "week": week,
                    "team_id": team_id,
                    "team": bundle["team"],
                    "trade_count": len(set(bundle["trade_ids"])),
                    "trade_ids": bundle["trade_ids"],
                    "received": [
                        {"id": player_id, "name": bundle["received"][player_id]}
                        for player_id in sorted(alternate["received_ids"])
                    ],
                    "sent": [
                        {"id": player_id, "name": bundle["sent"][player_id]}
                        for player_id in sorted(alternate["sent_ids"])
                    ],
                    "actual_score": box["score"],
                    "alternate_score": alternate["alternate"]["score"],
                    "net_points": round(box["score"] - alternate["alternate"]["score"], 2),
                    "opponent": box["opponent"],
                    "opponent_score": opponent_box["score"],
                    "opponent_alternate_score": opponent_alternate,
                    "result": actual_result,
                    "alternate_result": alternate_result,
                    "flipped": actual_result != alternate_result,
                    "replacements": alternate["alternate"]["replacements"],
                    "snapshot_status": "reconstructed_from_trades_and_weekly_box_score",
                }
            )
    result: WeeklyRosterMoves = {"rows": rows, "source": "weekly_trade_bundles"}
    if unavailable_team_weeks is not None:
        result["omitted"] = omitted
    return result


def bundle_trades(weekly_trades: list[Trade]) -> dict[int, dict[str, Any]]:
    """Per team: trade IDs plus every player received and sent (id -> name) across the week."""
    bundles: dict[int, dict[str, Any]] = {}
    for trade in weekly_trades:
        for side in trade["sides"]:
            bundle = bundles.setdefault(
                side["team_id"],
                {
                    "team_id": side["team_id"],
                    "team": side["team"],
                    "trade_ids": [],
                    "received": {},
                    "sent": {},
                },
            )
            bundle["trade_ids"].append(trade["id"])
            bundle["received"].update({player["id"]: player["name"] for player in side["received"]})
            bundle["sent"].update({player["id"]: player["name"] for player in side["sent"]})
    return bundles


def team_weeks(league: Any, week: int) -> dict[int, TeamWeek]:
    """Each team's score, opponent, starters, and bench for the week. Byes (no team) are skipped."""
    boxes: dict[int, TeamWeek] = {}
    for box in league.box_scores(week):
        for team, lineup, score, opponent in (
            (box.home_team, box.home_lineup, box.home_score, box.away_team),
            (box.away_team, box.away_lineup, box.away_score, box.home_team),
        ):
            if not hasattr(team, "team_id"):
                continue
            players = [box_player(player) for player in lineup]
            boxes[team.team_id] = {
                "score": round(float(score), 2),
                "opponent_id": getattr(opponent, "team_id", None),
                "opponent": opponent.team_name.strip() if hasattr(opponent, "team_name") else None,
                "starters": [player for player in players if player["slot"] not in STARTER_EXCLUDED_SLOTS],
                "bench": [player for player in players if player["slot"] == BENCH_SLOT],
            }
    return boxes


def _player_for_week(
    player_id: int, name: str, boxes: dict[int, TeamWeek], players_by_id: dict[int, EspnPlayer], week: int
) -> dict[str, Any]:
    """A departed player's week: from whichever box score has him, else his season stats."""
    for box in boxes.values():
        for rostered in box["starters"] + box["bench"]:
            if rostered["id"] == player_id:
                return {key: value for key, value in rostered.items() if key != "slot"}
    info = players_by_id.get(player_id)
    stats = getattr(info, "stats", {}).get(week) if info else None
    stats = stats if isinstance(stats, dict) else {}
    return {
        "id": player_id,
        "name": name,
        "points": round(float(stats.get("points") or 0), 2),
        "projected": round(float(stats.get("projected_points") or 0), 2),
        "eligible": list(getattr(info, "eligibleSlots", []) or []),
    }


def _no_trade_lineup(
    bundle: dict[str, Any],
    box: TeamWeek,
    boxes: dict[int, TeamWeek],
    players_by_id: dict[int, EspnPlayer],
    week: int,
) -> dict[str, Any]:
    received_ids = set(bundle["received"]) - set(bundle["sent"])
    sent_ids = set(bundle["sent"]) - set(bundle["received"])
    alternate: LineupEstimate = refill_lineup(
        box["starters"],
        box["bench"],
        received_ids,
        [_player_for_week(player_id, bundle["sent"][player_id], boxes, players_by_id, week) for player_id in sent_ids],
    )
    return {"alternate": alternate, "received_ids": received_ids, "sent_ids": sent_ids}
