"""Lineup math shared by the standings and weekly-moves stages.

Two different questions are answered here:

* `optimal_lineup_points` – the best possible score from a roster (hindsight;
  used for Alternate Universe standings so both worlds are compared fairly).
* `refill_lineup` – what a manager *would likely have started* without a trade
  (no hindsight; picks by ESPN projection, then sums actual points).
"""

from __future__ import annotations

from typing import Any

from .models import LineupEstimate, LineupPlayer, MatchupResult, Replacement

BENCH_SLOT = "BE"
STARTER_EXCLUDED_SLOTS = {BENCH_SLOT, "IR"}
NON_LINEUP_SLOTS = STARTER_EXCLUDED_SLOTS | {"ER", ""}
FLEX_SLOTS = {"RB/WR/TE", "RB/WR", "WR/TE", "OP"}


def box_player(player: Any) -> LineupPlayer:
    """Normalize an ESPN box-score player."""
    return {
        "id": player.playerId,
        "name": player.name,
        "slot": player.slot_position,
        "points": round(float(player.points or 0), 2),
        "projected": round(float(getattr(player, "projected_points", 0) or 0), 2),
        "eligible": list(getattr(player, "eligibleSlots", []) or []),
    }


def starting_slots(league: Any) -> list[str]:
    """One entry per starting slot, e.g. ["QB", "RB", "RB", "WR", ..., "RB/WR/TE"]."""
    return [
        slot
        for slot, count in league.settings.position_slot_counts.items()
        if slot not in NON_LINEUP_SLOTS
        for _ in range(count)
    ]


def matchup_result(score: float, opponent_score: float) -> MatchupResult:
    return "W" if score > opponent_score else "L" if score < opponent_score else "T"


def optimal_lineup_points(players: list[LineupPlayer], slots: list[str]) -> float:
    """Maximize actual points while assigning each player to at most one eligible slot.

    Dynamic programming over bitmasks of filled slots. Among the fullest
    achievable lineups the highest score wins, so negative scorers still start
    when nobody else can fill their slot.
    """
    best = {0: 0.0}
    for player in players:
        eligible = [index for index, slot in enumerate(slots) if slot in player["eligible"]]
        for mask, points in list(best.items()):
            for index in eligible:
                bit = 1 << index
                if mask & bit:
                    continue
                candidate = points + player["points"]
                if candidate > best.get(mask | bit, float("-inf")):
                    best[mask | bit] = candidate
    fullest = max(mask.bit_count() for mask in best)
    return round(max(points for mask, points in best.items() if mask.bit_count() == fullest), 2)


def refill_lineup(
    starters: list[LineupPlayer],
    bench: list[LineupPlayer],
    removed_ids: set[int],
    added: list[dict[str, Any]],
) -> LineupEstimate:
    """Estimate the team's lineup had the trade never happened.

    Starters who arrived in the trade are removed. Each vacated slot (dedicated slots before
    flex) gets the eligible bench or traded-away player with the highest ESPN *projection*.
    A traded-away player may also replace a remaining starter whose projection was lower.
    Choosing by projection avoids hindsight; actual points are then summed.
    """
    lineup = [dict(player) for player in starters if player["id"] not in removed_ids]
    vacated = sorted(
        (player["slot"] for player in starters if player["id"] in removed_ids),
        key=lambda slot: slot in FLEX_SLOTS,
    )
    lineup_ids = {player["id"] for player in lineup}
    pool_by_id = {
        player["id"]: player
        for player in bench + added
        if player["id"] not in removed_ids and player["id"] not in lineup_ids
    }
    pool = list(pool_by_id.values())
    added_ids = {player["id"] for player in added}
    changes: list[Replacement] = []
    for slot in vacated:
        eligible = [player for player in pool if slot in player.get("eligible", [])]
        if not eligible:
            changes.append({"slot": slot, "name": None, "points": 0.0, "replaced": None})
            continue
        best = max(eligible, key=lambda player: player.get("projected") or 0)
        pool.remove(best)
        lineup.append({**best, "slot": slot})
        changes.append({"slot": slot, "name": best["name"], "points": best["points"], "replaced": None})
    for player in sorted(
        (candidate for candidate in pool if candidate["id"] in added_ids),
        key=lambda candidate: -(candidate.get("projected") or 0),
    ):
        targets = [
            (index, current)
            for index, current in enumerate(lineup)
            if current["slot"] in player.get("eligible", [])
            and (current.get("projected") or 0) < (player.get("projected") or 0)
        ]
        if not targets:
            continue
        index, current = min(targets, key=lambda item: item[1].get("projected") or 0)
        lineup[index] = {**player, "slot": current["slot"]}
        changes.append(
            {
                "slot": current["slot"],
                "name": player["name"],
                "points": player["points"],
                "replaced": current["name"],
            }
        )
    return {
        "score": round(sum(player["points"] for player in lineup), 2),
        "replacements": changes,
    }
