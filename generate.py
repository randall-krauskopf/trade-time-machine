#!/usr/bin/env python3
"""Generate a read-only, local snapshot of Premier and Champeens League trades."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from espn_api.football import League
from espn_api.requests.espn_requests import ESPNAccessDenied

HERE = Path(__file__).resolve().parent
GUILD_ID = 1160416084235661426
CHANNELS = {
    1160416085326188555: "general",
    1160416085326188556: "nfl-chat",
    1281464082809098260: "lspl-only-chat",
    1160416085326188557: "trade-talk",
    1278801017726570617: "espn-ffl-bot-premier",
}
TRADE_WINDOW = timedelta(days=2)
LEAGUE_TIMEZONE = ZoneInfo("America/Chicago")
FIRST_TRADE_DATE = date(2026, 8, 30)
ACQUISITION_TOLERANCE_MS = 60_000
REVIEW_WINDOW_MS = 3 * 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class GeneratorConfig:
    season_year: int
    first_trade_date: date
    leagues: list[dict[str, Any]]


def load_config(path: Path) -> GeneratorConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Generator config must be a JSON object.")
    year = data.get("season_year")
    if type(year) is not int or not 2000 <= year <= 2100:
        raise ValueError("season_year must be an integer between 2000 and 2100.")
    try:
        first_trade_date = date.fromisoformat(data["first_trade_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("first_trade_date must be an ISO date (YYYY-MM-DD).") from exc
    if first_trade_date.year != year:
        raise ValueError("first_trade_date must fall in season_year.")
    leagues = data.get("leagues")
    if not isinstance(leagues, list) or not leagues:
        raise ValueError("leagues must be a nonempty array.")
    keys = set()
    for league in leagues:
        if not isinstance(league, dict) or not isinstance(league.get("key"), str) or not league["key"].strip():
            raise ValueError("Each league needs a nonempty key.")
        if league["key"] in keys:
            raise ValueError(f"Duplicate league key: {league['key']}.")
        keys.add(league["key"])
        if not isinstance(league.get("label"), str) or not league["label"].strip():
            raise ValueError(f"League {league['key']} needs a nonempty label.")
        if type(league.get("league_id")) is not int or league["league_id"] <= 0:
            raise ValueError(f"League {league['key']} needs a positive numeric league_id.")
        if type(league.get("receipts")) is not bool:
            raise ValueError(f"League {league['key']} needs a boolean receipts setting.")
    return GeneratorConfig(year, first_trade_date, leagues)


def load_credentials(path: Path) -> dict[str, str]:
    credentials = {key: os.environ[key] for key in ("ESPN_S2", "SWID") if os.environ.get(key)}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key = key.strip()
            if separator and key in {"ESPN_S2", "SWID"} and key not in credentials:
                value = value.strip().strip("\"'")
                if value:
                    credentials[key] = value
    if len(credentials) == 1:
        raise ValueError("Provide both ESPN_S2 and SWID for a private league, or neither for public leagues.")
    return credentials


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


def parse_discord_export(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    messages = payload.get("messages") if isinstance(payload, dict) else payload
    if not isinstance(messages, list):
        raise ValueError("Discord export must be a JSON array or an object with a 'messages' array.")
    filtered = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Every Discord message must be an object.")
        try:
            guild = int(message["guild_id"])
            channel = int(message["channel_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Discord messages need numeric guild_id and channel_id.") from exc
        if guild != GUILD_ID or channel not in CHANNELS or message.get("deleted_at") or message.get("author_bot"):
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            sent_at = datetime.fromisoformat(message["sent_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError, AttributeError) as exc:
            raise ValueError("Discord messages need an ISO-8601 sent_at timestamp.") from exc
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        message_id = message.get("message_id")
        if message_id is None or not str(message_id).isdigit():
            raise ValueError("Discord messages need a numeric message_id.")
        filtered.append({
            "channel": CHANNELS[channel],
            "channel_id": channel,
            "message_id": str(message_id),
            "author": str(message.get("author_name") or "Unknown"),
            "content": content.strip()[:600],
            "sent_at": sent_at.astimezone(timezone.utc),
        })
    return filtered


def trade_receipts(
    messages: list[dict[str, Any]], traded_at: datetime, names: list[str]
) -> list[dict[str, str]]:
    patterns = [re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.IGNORECASE) for name in names]
    nearby = [
        message for message in messages
        if abs(message["sent_at"] - traded_at) <= TRADE_WINDOW
        and any(pattern.search(message["content"]) for pattern in patterns)
    ]
    nearby.sort(key=lambda message: abs(message["sent_at"] - traded_at))
    return [{
        "channel": message["channel"],
        "author": message["author"],
        "content": message["content"],
        "sent_at": message["sent_at"].isoformat(),
        "url": f"https://discord.com/channels/{GUILD_ID}/{message['channel_id']}/{message['message_id']}",
    } for message in nearby[:4]]


def activities(league: Any) -> list[Any]:
    all_activities: list[Any] = []
    offset = 0
    while True:
        page = league.recent_activity(size=100, offset=offset)
        all_activities.extend(page)
        if len(page) < 100:
            return all_activities
        offset += len(page)


def transaction_trades(league: Any) -> list[Any]:
    """Rebuild accepted trades when ESPN's member-only activity feed is unavailable.

    Accepted-trade records omit their players, so players are recovered from
    (1) current roster entries acquired by trade at the exact acceptance timestamp and
    (2) direct team-to-team roster moves across the trade's scoring period, ignoring
    moves explained by a waiver or free-agent add.
    """
    transactions: dict[str, dict[str, Any]] = {}
    for period in range(0, int(league.current_week) + 1):
        data = league.espn_request.league_get(params={"view": "mTransactions2", "scoringPeriodId": period})
        for transaction in data.get("transactions", []):
            transactions.setdefault(transaction["id"], transaction)
    accepts = [
        transaction for transaction in transactions.values()
        if transaction.get("type") == "TRADE_ACCEPT" and transaction.get("status") in {"EXECUTED", None}
    ]
    adds = {
        (item.get("playerId"), item.get("toTeamId"))
        for transaction in transactions.values()
        if transaction.get("type") in {"WAIVER", "FREEAGENT"} and transaction.get("status") == "EXECUTED"
        for item in transaction.get("items", []) if item.get("type") == "ADD"
    }

    snapshots = [{pick.playerId: pick.team.team_id for pick in league.draft}]
    acquired_by_trade: dict[int, list[tuple[int, int]]] = {}
    for period in range(1, int(league.current_week) + 1):
        data = league.espn_request.league_get(params={"view": "mRoster", "scoringPeriodId": period})
        snapshot = {}
        for team in data.get("teams", []):
            for entry in team.get("roster", {}).get("entries", []):
                snapshot[entry["playerId"]] = team["id"]
                if entry.get("acquisitionType") == "TRADE" and entry.get("acquisitionDate"):
                    acquired_by_trade.setdefault(entry["acquisitionDate"], []).append((entry["playerId"], team["id"]))
        snapshots.append(snapshot)
    return reconstruct_trades(league, accepts, adds, snapshots, acquired_by_trade)


def reconstruct_trades(
    league: Any,
    accepts: list[dict[str, Any]],
    adds: set[tuple[int, int]],
    snapshots: list[dict[int, int]],
    acquired_by_trade: dict[int, list[tuple[int, int]]],
) -> list[Any]:
    teams = {team.team_id: team for team in league.teams}
    player_map = getattr(league, "player_map", {})
    trades = []
    # Match each accepted trade to roster acquisition timestamps. Trades under league review
    # execute later than they are accepted, so unmatched accepts claim the next unclaimed time.
    matched: dict[str, list[int]] = {}
    for accept in accepts:
        accepted_at = accept.get("processDate") or accept["proposedDate"]
        matched[accept["id"]] = [
            acquired_at for acquired_at in acquired_by_trade
            if abs(acquired_at - accepted_at) <= ACQUISITION_TOLERANCE_MS
        ]
    claimed = {acquired_at for times in matched.values() for acquired_at in times}
    for accept in sorted(accepts, key=lambda item: item.get("processDate") or item["proposedDate"]):
        if matched[accept["id"]]:
            continue
        accepted_at = accept.get("processDate") or accept["proposedDate"]
        later = sorted(
            acquired_at for acquired_at in acquired_by_trade
            if acquired_at not in claimed and 0 <= acquired_at - accepted_at <= REVIEW_WINDOW_MS
        )
        if later:
            matched[accept["id"]] = [later[0]]
            claimed.add(later[0])
    for accept in accepts:
        times = matched[accept["id"]]
        traded_at = min(times) if times else accept.get("processDate") or accept["proposedDate"]
        moves = {
            item["playerId"]: (item["fromTeamId"], item["toTeamId"])
            for item in accept.get("items", []) if item.get("type") == "TRADE"
        }
        received = [acquisition for acquired_at in times for acquisition in acquired_by_trade[acquired_at]]
        parties = {team_id for _, team_id in received} | {team_id for move in moves.values() for team_id in move}
        if len(parties) < 2:
            # The accepting team may be omitted when a league manager processes the trade.
            parties.add(accept.get("teamId"))
        parties.discard(None)
        period = min(max(int(accept.get("scoringPeriodId") or 1), 1), len(snapshots) - 1)
        before, after = snapshots[period - 1], snapshots[period]
        direct = [
            (player_id, before[player_id], team_id) for player_id, team_id in after.items()
            if player_id in before and before[player_id] != team_id and (player_id, team_id) not in adds
        ]
        if len(parties) == 1:
            partners = {old for _, old, new in direct if new in parties} | {
                new for _, old, new in direct if old in parties
            }
            if len(partners) == 1:
                parties |= partners
        if len(parties) != 2:
            continue
        for player_id, team_id in received:
            (other_team,) = parties - {team_id}
            moves[player_id] = (other_team, team_id)
        # Only fall back to roster diffs when no other accepted trade in this period touches these teams.
        shares_period = any(
            candidate is not accept
            and min(max(int(candidate.get("scoringPeriodId") or 1), 1), len(snapshots) - 1) == period
            and candidate.get("teamId") in parties
            for candidate in accepts
        )
        if not shares_period:
            for player_id, old, new in direct:
                if {old, new} == parties:
                    moves.setdefault(player_id, (old, new))
        actions = []
        for player_id, (old, new) in moves.items():
            player = SimpleNamespace(playerId=player_id, name=player_map.get(player_id, f"Player {player_id}"))
            actions.append((teams[old], "TRADE_SENT", player, 0))
            actions.append((teams[new], "TRADE_RECEIVED", player, 0))
        if actions:
            trades.append(SimpleNamespace(date=traded_at, actions=actions))
    return trades


STARTER_EXCLUDED_SLOTS = {"BE", "IR"}
FLEX_SLOTS = {"RB/WR/TE", "RB/WR", "WR/TE", "OP"}


def refill_lineup(
    starters: list[dict[str, Any]],
    bench: list[dict[str, Any]],
    removed_ids: set[int],
    added: list[dict[str, Any]],
) -> dict[str, Any]:
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
    changes = []
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
            (index, current) for index, current in enumerate(lineup)
            if current["slot"] in player.get("eligible", [])
            and (current.get("projected") or 0) < (player.get("projected") or 0)
        ]
        if not targets:
            continue
        index, current = min(targets, key=lambda item: item[1].get("projected") or 0)
        lineup[index] = {**player, "slot": current["slot"]}
        changes.append({"slot": current["slot"], "name": player["name"], "points": player["points"], "replaced": current["name"]})
    return {
        "score": round(sum(player["points"] for player in lineup), 2),
        "replacements": changes,
    }


def result(score: float, opponent: float) -> str:
    return "W" if score > opponent else "L" if score < opponent else "T"


RESULT_VALUE = {"W": 1.0, "T": 0.5, "L": 0.0}


def box_player(player: Any) -> dict[str, Any]:
    return {
        "id": player.playerId,
        "name": player.name,
        "slot": player.slot_position,
        "points": round(float(player.points or 0), 2),
        "projected": round(float(getattr(player, "projected_points", 0) or 0), 2),
        "eligible": list(getattr(player, "eligibleSlots", []) or []),
    }


def optimal_lineup_points(players: list[dict[str, Any]], slots: list[str]) -> float:
    """Maximize actual points while assigning each player to at most one eligible slot."""
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


def alternate_standings(
    league: Any, trades: list[dict[str, Any]], first_trade_date: date = FIRST_TRADE_DATE
) -> dict[str, Any]:
    """Rewind known trade transfers in weekly rosters, preserving actual waiver/FA moves."""
    cutoff = datetime.combine(first_trade_date, datetime.min.time(), LEAGUE_TIMEZONE)
    slots = [
        slot for slot, count in league.settings.position_slot_counts.items()
        if slot not in STARTER_EXCLUDED_SLOTS | {"ER", ""}
        for _ in range(count)
    ]
    events: dict[int, list[tuple[datetime, str, int]]] = {}
    for trade in trades:
        traded_at = datetime.fromisoformat(trade["traded_at"])
        for side in trade["sides"]:
            for player in side["sent"]:
                events.setdefault(player["id"], []).append((traded_at, "trade", side["team_id"]))
    # ESPN's executed waiver/FA records tell us when a player entered a new ownership chain.
    transactions: dict[str, dict[str, Any]] = {}
    for period in range(int(league.current_week) + 1):
        data = league.espn_request.league_get(params={"view": "mTransactions2", "scoringPeriodId": period})
        for transaction in data.get("transactions", []):
            transactions.setdefault(transaction["id"], transaction)
    for transaction in transactions.values():
        if transaction.get("type") not in {"WAIVER", "FREEAGENT"} or transaction.get("status") != "EXECUTED":
            continue
        timestamp = transaction.get("processDate") or transaction.get("proposedDate")
        if not timestamp:
            raise ValueError(f"Executed acquisition {transaction['id']} has no timestamp.")
        when = datetime.fromtimestamp(timestamp / 1000, timezone.utc)
        if when < cutoff:
            continue
        for item in transaction.get("items", []):
            if item.get("type") == "ADD" and item.get("playerId") is not None:
                events.setdefault(item["playerId"], []).append((when, "add", item["toTeamId"]))
    for history in events.values():
        history.sort(key=lambda event: event[0])

    teams = {team.team_id: team.team_name.strip() for team in league.teams}
    standings = {
        team_id: {"team_id": team_id, "team": name, "actual_wins": 0, "actual_losses": 0,
                  "actual_ties": 0, "actual_points": 0.0, "alternate_wins": 0,
                  "alternate_losses": 0, "alternate_ties": 0, "alternate_points": 0.0,
                  "optimal_actual_wins": 0, "optimal_actual_losses": 0,
                  "optimal_actual_ties": 0, "optimal_actual_points": 0.0}
        for team_id, name in teams.items()
    }
    week_details = []
    for week in range(1, int(league.current_week)):
        end = week_start(league.year, week + 1)
        boxes = league.box_scores(week)
        rosters: dict[int, dict[int, dict[str, Any]]] = {}
        matchups = []
        for box in boxes:
            home_id, away_id = box.home_team.team_id, box.away_team.team_id
            if home_id not in teams or away_id not in teams:
                raise ValueError(f"Week {week} box score has an unknown team.")
            matchups.append((home_id, away_id, float(box.home_score), float(box.away_score)))
            for team_id, lineup in ((home_id, box.home_lineup), (away_id, box.away_lineup)):
                if team_id in rosters:
                    raise ValueError(f"Week {week} has duplicate box scores for team {team_id}.")
                rosters[team_id] = {player.playerId: box_player(player) for player in lineup}
        if set(rosters) != set(teams):
            raise ValueError(f"Week {week} is missing box scores for some teams.")
        alternates = {team_id: dict(roster) for team_id, roster in rosters.items()}
        moves = 0
        for player_id, history in events.items():
            actual_owner = next((team_id for team_id, roster in rosters.items() if player_id in roster), None)
            if actual_owner is None:
                continue
            origin = None
            has_trade = False
            for when, kind, owner in history:
                if when >= end:
                    break
                if kind == "add":
                    origin, has_trade = owner, False
                elif origin is None:
                    origin, has_trade = owner, True
                else:
                    has_trade = True
            if has_trade and origin in alternates and actual_owner != origin:
                alternates[origin][player_id] = alternates[actual_owner].pop(player_id)
                moves += 1
        optimal_actual_scores = {
            team_id: optimal_lineup_points(list(roster.values()), slots)
            for team_id, roster in rosters.items()
        }
        alternate_scores = {
            team_id: optimal_lineup_points(list(roster.values()), slots)
            for team_id, roster in alternates.items()
        }
        for team_id, roster in rosters.items():
            standings[team_id]["optimal_actual_points"] += optimal_actual_scores[team_id]
            standings[team_id]["alternate_points"] += alternate_scores[team_id]
        for home, away, home_score, away_score in matchups:
            for team_id, score, rival, rival_score in (
                (home, home_score, away, away_score), (away, away_score, home, home_score)
            ):
                row = standings[team_id]
                row["actual_points"] += score
                row[f"actual_{'wins' if score > rival_score else 'losses' if score < rival_score else 'ties'}"] += 1
                optimal_score = optimal_actual_scores[team_id]
                row[f"optimal_actual_{'wins' if optimal_score > optimal_actual_scores[rival] else 'losses' if optimal_score < optimal_actual_scores[rival] else 'ties'}"] += 1
                alt_score = alternate_scores[team_id]
                row[f"alternate_{'wins' if alt_score > alternate_scores[rival] else 'losses' if alt_score < alternate_scores[rival] else 'ties'}"] += 1
        week_details.append({"week": week, "rewound_players": moves})
    for row in standings.values():
        for key in ("actual_points", "alternate_points", "optimal_actual_points"):
            row[key] = round(row[key], 2)
        row["wins_change"] = (row["alternate_wins"] + row["alternate_ties"] / 2) - (row["optimal_actual_wins"] + row["optimal_actual_ties"] / 2)
    return {"weeks": week_details, "teams": list(standings.values()), "source": "weekly_box_scores"}


def add_matchup_impact(league: Any, trades: list[dict[str, Any]], players_by_id: dict[int, Any]) -> None:
    """Attach real-lineup matchup impact to each trade side, using weekly box scores."""
    box_cache: dict[int, dict[int, dict[str, Any]]] = {}
    chronological = sorted(trades, key=lambda trade: trade["traded_at"])

    def first_retrade(trade: dict[str, Any]) -> dict[str, Any] | None:
        for later in chronological:
            if later["traded_at"] <= trade["traded_at"]:
                continue
            for original_side in trade["sides"]:
                received = {player["id"]: player["name"] for player in original_side["received"]}
                later_side = next(
                    (side for side in later["sides"] if side["team_id"] == original_side["team_id"]), None
                )
                if later_side is None:
                    continue
                for player in later_side["sent"]:
                    if player["id"] in received:
                        recipient = next(
                            side for side in later["sides"] if side["team_id"] != original_side["team_id"]
                        )
                        return {
                            "player_id": player["id"],
                            "player": received[player["id"]],
                            "team": original_side["team"],
                            "team_id": original_side["team_id"],
                            "to_team_id": recipient["team_id"],
                            "traded_at": later["traded_at"],
                            "last_week": None,
                        }
        return None

    def week_boxes(week: int) -> dict[int, dict[str, Any]]:
        if week not in box_cache:
            teams: dict[int, dict[str, Any]] = {}
            for box in league.box_scores(week):
                for team, lineup, score, opponent in (
                    (box.home_team, box.home_lineup, box.home_score, box.away_team),
                    (box.away_team, box.away_lineup, box.away_score, box.home_team),
                ):
                    if not hasattr(team, "team_id"):
                        continue
                    players = [box_player(player) for player in lineup]
                    teams[team.team_id] = {
                        "score": round(float(score), 2),
                        "opponent_id": getattr(opponent, "team_id", None),
                        "opponent": opponent.team_name.strip() if hasattr(opponent, "team_name") else None,
                        "starters": [player for player in players if player["slot"] not in STARTER_EXCLUDED_SLOTS],
                        "bench": [player for player in players if player["slot"] == "BE"],
                    }
            box_cache[week] = teams
        return box_cache[week]

    def sent_player(player: dict[str, Any], week: int) -> dict[str, Any]:
        for team in week_boxes(week).values():
            for rostered in team["starters"] + team["bench"]:
                if rostered["id"] == player["id"]:
                    return {key: value for key, value in rostered.items() if key != "slot"}
        info = players_by_id.get(player["id"])
        week_stats = getattr(info, "stats", {}).get(week) if info else None
        week_stats = week_stats if isinstance(week_stats, dict) else {}
        return {
            "id": player["id"],
            "name": player["name"],
            "points": round(float(week_stats.get("points") or 0), 2),
            "projected": round(float(week_stats.get("projected_points") or 0), 2),
            "eligible": list(getattr(info, "eligibleSlots", []) or []),
        }

    for trade in trades:
        cutoff = first_retrade(trade)
        trade["impact_cutoff"] = cutoff
        for side in trade["sides"]:
            side["impact"] = {"weeks": {}, "wins_added": None, "net_points": None, "flips": 0}
        for week in trade["weeks"]:
            if cutoff and cutoff["traded_at"] <= week_start(league.year, week).isoformat():
                break
            boxes = week_boxes(week)
            if cutoff and cutoff["traded_at"] < week_start(league.year, week + 1).isoformat():
                original_box = boxes.get(cutoff["team_id"])
                new_box = boxes.get(cutoff["to_team_id"])
                if not original_box or not new_box:
                    break
                original_ids = {player["id"] for player in original_box["starters"] + original_box["bench"]}
                new_ids = {player["id"] for player in new_box["starters"] + new_box["bench"]}
                if cutoff["player_id"] not in original_ids or cutoff["player_id"] in new_ids:
                    break
            if week == trade["trade_week"] and not any(
                player["id"] in {rostered["id"] for rostered in boxes.get(side["team_id"], {}).get("starters", []) + boxes.get(side["team_id"], {}).get("bench", [])}
                for side in trade["sides"] for player in side["received"]
            ):
                continue  # The trade wasn't reflected in lineups until the following week.
            alternates: dict[int, dict[str, Any]] = {}
            for side in trade["sides"]:
                box = boxes.get(side["team_id"])
                if box is None:
                    continue
                received_ids = {player["id"] for player in side["received"]}
                started = [player for player in box["starters"] if player["id"] in received_ids]
                benched = [player for player in box["bench"] if player["id"] in received_ids]
                alternate = refill_lineup(
                    box["starters"], box["bench"], received_ids,
                    [sent_player(player, week) for player in side["sent"]],
                )
                alternates[side["team_id"]] = {
                    "box": box,
                    "alternate": alternate,
                    "started": started,
                    "benched": benched,
                }
            for side in trade["sides"]:
                entry = alternates.get(side["team_id"])
                if entry is None:
                    continue
                box = entry["box"]
                opponent_box = boxes.get(box["opponent_id"])
                if opponent_box is None:
                    continue
                opponent_score = opponent_box["score"]
                # Undo the trade for the opponent too when they were the trade partner.
                opponent_alt = alternates.get(box["opponent_id"], {}).get("alternate", {}).get("score", opponent_score)
                actual = result(box["score"], opponent_score)
                alternate_result = result(entry["alternate"]["score"], opponent_alt)
                side["impact"]["weeks"][str(week)] = {
                    "started_points": round(sum(player["points"] for player in entry["started"]), 2),
                    "benched_points": round(sum(player["points"] for player in entry["benched"]), 2),
                    "started": [{"name": player["name"], "slot": player["slot"], "points": player["points"]} for player in entry["started"]],
                    "replacements": entry["alternate"]["replacements"],
                    "score": box["score"],
                    "alt_score": entry["alternate"]["score"],
                    "net_points": round(box["score"] - entry["alternate"]["score"], 2),
                    "opponent": box["opponent"],
                    "opponent_is_partner": box["opponent_id"] in alternates,
                    "opponent_score": opponent_score,
                    "opponent_alt_score": opponent_alt,
                    "result": actual,
                    "alt_result": alternate_result,
                    "flipped": actual != alternate_result,
                }
        for side in trade["sides"]:
            weeks = side["impact"]["weeks"].values()
            if weeks:
                side["impact"]["wins_added"] = round(sum(RESULT_VALUE[w["result"]] - RESULT_VALUE[w["alt_result"]] for w in weeks), 1)
                side["impact"]["net_points"] = round(sum(w["net_points"] for w in weeks), 2)
                side["impact"]["flips"] = sum(1 for w in weeks if w["flipped"])
        if cutoff:
            counted = [int(week) for side in trade["sides"] for week in side["impact"]["weeks"]]
            cutoff["last_week"] = max(counted) if counted else None


def weekly_roster_moves(
    league: Any, trades: list[dict[str, Any]], players_by_id: dict[int, Any]
) -> dict[str, Any]:
    """Grade each manager's combined trade activity within a Tuesday-to-Tuesday week."""
    rows = []
    for week in range(1, int(league.current_week)):
        weekly_trades = [trade for trade in trades if trade["transaction_week"] == week]
        if not weekly_trades:
            continue
        bundles: dict[int, dict[str, Any]] = {}
        for trade in weekly_trades:
            for side in trade["sides"]:
                bundle = bundles.setdefault(side["team_id"], {
                    "team_id": side["team_id"], "team": side["team"], "trade_ids": [],
                    "received": {}, "sent": {},
                })
                bundle["trade_ids"].append(trade["id"])
                bundle["received"].update({player["id"]: player["name"] for player in side["received"]})
                bundle["sent"].update({player["id"]: player["name"] for player in side["sent"]})

        boxes: dict[int, dict[str, Any]] = {}
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
                    "bench": [player for player in players if player["slot"] == "BE"],
                }

        def player_for_week(player_id: int, name: str) -> dict[str, Any]:
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

        alternates = {}
        for team_id, bundle in bundles.items():
            box = boxes.get(team_id)
            if box is None:
                continue
            received_ids = set(bundle["received"]) - set(bundle["sent"])
            sent_ids = set(bundle["sent"]) - set(bundle["received"])
            alternate = refill_lineup(
                box["starters"], box["bench"], received_ids,
                [player_for_week(player_id, bundle["sent"][player_id]) for player_id in sent_ids],
            )
            alternates[team_id] = {
                "alternate": alternate,
                "received_ids": received_ids,
                "sent_ids": sent_ids,
            }

        for team_id, bundle in bundles.items():
            box = boxes.get(team_id)
            alternate = alternates.get(team_id)
            if box is None or alternate is None or box["opponent_id"] not in boxes:
                continue
            opponent_box = boxes[box["opponent_id"]]
            opponent_alt = alternates.get(box["opponent_id"], {}).get(
                "alternate", {"score": opponent_box["score"]}
            )["score"]
            actual_result = result(box["score"], opponent_box["score"])
            alternate_result = result(alternate["alternate"]["score"], opponent_alt)
            rows.append({
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
                "opponent_alternate_score": opponent_alt,
                "result": actual_result,
                "alternate_result": alternate_result,
                "flipped": actual_result != alternate_result,
                "replacements": alternate["alternate"]["replacements"],
                "snapshot_status": "reconstructed_from_trades_and_weekly_box_score",
            })
    return {"rows": rows, "source": "weekly_trade_bundles"}


def build_snapshot(
    league: Any, messages: list[dict[str, Any]], first_trade_date: date = FIRST_TRADE_DATE
) -> dict[str, Any]:
    cutoff = datetime.combine(first_trade_date, datetime.min.time(), LEAGUE_TIMEZONE)
    try:
        league_activities = activities(league)
        source = "activity"
    except ESPNAccessDenied:
        # The activity feed is member-only; the transactions and roster views are readable.
        league_activities = transaction_trades(league)
        source = "reconstructed"
    trade_activities = [
        activity for activity in league_activities
        if datetime.fromtimestamp(activity.date / 1000, timezone.utc) >= cutoff
        and any(action == "TRADE_SENT" for _, action, _, _ in activity.actions)
    ]
    player_ids = sorted({
        player.playerId for activity in trade_activities
        for _, action, player, _ in activity.actions
        if action == "TRADE_SENT" and player is not None
    })
    players = league.player_info(playerId=player_ids) if player_ids else []
    if not isinstance(players, list):
        players = [players]
    players_by_id = {player.playerId: player for player in players if player is not None}

    # Week currently in progress is excluded even when some games have concluded.
    completed_weeks = list(range(1, int(league.current_week)))
    trades = []
    for activity in trade_activities:
        traded_at = datetime.fromtimestamp(activity.date / 1000, timezone.utc)
        sides: dict[int, dict[str, Any]] = {}
        for team, action, player, _ in activity.actions:
            if action not in {"TRADE_SENT", "TRADE_RECEIVED"} or player is None:
                continue
            side = sides.setdefault(team.team_id, {
                "team_id": team.team_id,
                "team": team.team_name.strip(),
                "sent": [],
                "received": [],
            })
            if action == "TRADE_SENT":
                side["sent"].append({"id": player.playerId, "name": player.name})
            else:
                side["received"].append({"id": player.playerId, "name": player.name})
        if len(sides) != 2:
            raise ValueError(f"Expected two teams in ESPN trade at {traded_at.isoformat()}.")

        # Include the completed scoring week containing the trade, even if
        # games were already underway. The UI labels that week separately.
        weeks = [week for week in completed_weeks if traded_at < week_start(league.year, week + 1)]
        trade_week = next(
            (week for week in weeks if traded_at >= week_start(league.year, week)), None
        )
        for side in sides.values():
            # Keep the original received-player set fixed even after later trades.
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
                round(sum(side["weekly_points"].values()), 2)
                if all(score is not None for score in side["weekly_points"].values())
                else None
            ) if weeks else None

        team_sides = sorted(sides.values(), key=lambda side: side["team_id"])
        names = [player["name"] for side in team_sides for player in side["sent"]]
        trades.append({
            "id": f"{activity.date}-{'-'.join(str(side['team_id']) for side in team_sides)}",
            "traded_at": traded_at.isoformat(),
            "transaction_week": transaction_week(league.year, traded_at),
            "weeks": weeks,
            "trade_week": trade_week,
            "sides": team_sides,
            "receipts": trade_receipts(messages, traded_at, names),
        })

    if hasattr(league, "box_scores"):
        standings = alternate_standings(league, trades, first_trade_date)
        roster_moves = weekly_roster_moves(league, trades, players_by_id)
    else:
        standings = None
        roster_moves = None

    return {
        "league": league.settings.name,
        "season": league.year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "completed_weeks": completed_weeks,
        "first_trade_date": first_trade_date.isoformat(),
        "trades": trades,
        "alternate_standings": standings,
        "weekly_roster_moves": roster_moves,
        "source": source,
        "discord_imported": bool(messages),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "generator.json",
                        help="League IDs, season year, and inclusive Central-time cutoff (default: generator.json).")
    parser.add_argument("--env-file", type=Path, default=HERE / ".env",
                        help="Local ESPN_S2 and SWID credentials (default: .env); environment variables take precedence.")
    parser.add_argument("--discord-export", type=Path, help="Optional local JSON export of discord_messages.")
    parser.add_argument("--output", type=Path, default=HERE / "docs" / "data.json")
    args = parser.parse_args()
    config = load_config(args.config)
    credentials = load_credentials(args.env_file)
    messages = parse_discord_export(args.discord_export)
    leagues = []
    for spec in config.leagues:
        league = League(league_id=spec["league_id"], year=config.season_year, **{
            key.lower(): credentials[key] for key in ("ESPN_S2", "SWID") if key in credentials
        })
        snapshot = build_snapshot(league, messages if spec["receipts"] else [], config.first_trade_date)
        snapshot.update(key=spec["key"], label=spec["label"], receipts_enabled=spec["receipts"])
        leagues.append(snapshot)
        print(f"{spec['label']}: {len(snapshot['trades'])} trades")
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "first_trade_date": config.first_trade_date.isoformat(),
        "discord_imported": bool(messages),
        "leagues": leagues,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {sum(len(league['trades']) for league in leagues)} trades to {args.output}")


if __name__ == "__main__":
    main()
