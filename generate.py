#!/usr/bin/env python3
"""Generate a read-only, local snapshot of Premier and Champeens League trades."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent
# The ESPN helper library and private .env live in the AI-playground repo.
SCRIPTS = Path(os.environ.get(
    "FF_SCRIPTS_DIR", HERE.parent / "AI-playground" / "fantasy-football-league" / "scripts"
)).expanduser().resolve()
sys.path.insert(0, str(SCRIPTS / "src"))

from ff_espn.client import build_league  # noqa: E402
from ff_espn.config import LeagueConfig  # noqa: E402
from espn_api.requests.espn_requests import ESPNAccessDenied  # noqa: E402


PREMIER_LEAGUE_ID = 1851323
CHAMPEENS_LEAGUE_ID = 1695026336
# Discord receipts are only attached to Premier; Champeens channels are out of scope.
LEAGUES = (
    {"key": "premier", "label": "Premier", "league_id": PREMIER_LEAGUE_ID, "receipts": True},
    {"key": "champeens", "label": "Champeens", "league_id": CHAMPEENS_LEAGUE_ID, "receipts": False},
)
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


def week_start(year: int, week: int) -> datetime:
    """The first week begins Thursday; subsequent scoring weeks begin Tuesday."""
    september_first = date(year, 9, 1)
    labor_day = september_first + timedelta(days=(7 - september_first.weekday()) % 7)
    first_thursday = labor_day + timedelta(days=3)
    start = first_thursday if week == 1 else first_thursday + timedelta(days=5, weeks=week - 2)
    return datetime.combine(start, datetime.min.time(), LEAGUE_TIMEZONE)


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


def build_snapshot(league: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
    cutoff = datetime.combine(FIRST_TRADE_DATE, datetime.min.time(), LEAGUE_TIMEZONE)
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
            "weeks": weeks,
            "trade_week": trade_week,
            "sides": team_sides,
            "receipts": trade_receipts(messages, traded_at, names),
        })

    if hasattr(league, "box_scores"):
        add_matchup_impact(league, trades, players_by_id)

    return {
        "league": league.settings.name,
        "season": league.year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "completed_weeks": completed_weeks,
        "first_trade_date": FIRST_TRADE_DATE.isoformat(),
        "trades": trades,
        "source": source,
        "discord_imported": bool(messages),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discord-export", type=Path, help="Optional local JSON export of discord_messages.")
    parser.add_argument("--output", type=Path, default=HERE / "docs" / "data.json")
    args = parser.parse_args()
    config = LeagueConfig.from_env(SCRIPTS / ".env")
    messages = parse_discord_export(args.discord_export)
    leagues = []
    for spec in LEAGUES:
        league = build_league(replace(config, league_id=spec["league_id"]))
        snapshot = build_snapshot(league, messages if spec["receipts"] else [])
        snapshot.update(key=spec["key"], label=spec["label"], receipts_enabled=spec["receipts"])
        leagues.append(snapshot)
        print(f"{spec['label']}: {len(snapshot['trades'])} trades")
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "first_trade_date": FIRST_TRADE_DATE.isoformat(),
        "discord_imported": bool(messages),
        "leagues": leagues,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {sum(len(league['trades']) for league in leagues)} trades to {args.output}")


if __name__ == "__main__":
    main()
