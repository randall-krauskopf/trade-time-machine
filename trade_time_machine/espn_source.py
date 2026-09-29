"""Reading trades out of ESPN.

Two sources, tried in order:

* **activity** – the league's recent-activity feed. Complete, but members-only.
* **reconstructed** – when the feed is denied, rebuild trades from the public
  `mTransactions2` (accepted trades, without players) and `mRoster` views.

Either way the result is a list of *activities*: objects with `date` (epoch ms)
and `actions` tuples `(team, "TRADE_SENT" | "TRADE_RECEIVED", player, bid)`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from .models import EspnActivity

ACTIVITY_PAGE_SIZE = 100
ACQUISITION_TOLERANCE_MS = 60_000
"""An mRoster trade acquisition this close to an acceptance belongs to it."""
REVIEW_WINDOW_MS = 3 * 24 * 60 * 60 * 1000
"""Trades under league review execute up to this long after being accepted."""
ACQUISITION_TYPES = {"WAIVER", "FREEAGENT"}


def fetch_activity_feed(league: Any) -> list[EspnActivity]:
    """All pages of the recent-activity feed. Raises ESPNAccessDenied for non-members."""
    feed: list[Any] = []
    offset = 0
    while True:
        page = league.recent_activity(size=ACTIVITY_PAGE_SIZE, offset=offset)
        feed.extend(page)
        if len(page) < ACTIVITY_PAGE_SIZE:
            return feed
        offset += len(page)


def fetch_transactions(league: Any) -> list[dict[str, Any]]:
    """Every mTransactions2 record for the season (scoring periods 0..current_week), deduplicated by id."""
    transactions: dict[str, dict[str, Any]] = {}
    for period in range(int(league.current_week) + 1):
        data = league.espn_request.league_get(params={"view": "mTransactions2", "scoringPeriodId": period})
        for transaction in data.get("transactions", []):
            transactions.setdefault(transaction["id"], transaction)
    return list(transactions.values())


def is_executed_acquisition(transaction: dict[str, Any]) -> bool:
    """A waiver claim or free-agent pickup that actually went through."""
    return transaction.get("type") in ACQUISITION_TYPES and transaction.get("status") == "EXECUTED"


def fetch_reconstructed_trades(league: Any) -> list[EspnActivity]:
    """Rebuild accepted trades when ESPN's member-only activity feed is unavailable.

    Accepted-trade records omit their players, so players are recovered from
    (1) current roster entries acquired by trade at the exact acceptance timestamp and
    (2) direct team-to-team roster moves across the trade's scoring period, ignoring
    moves explained by a waiver or free-agent add.
    """
    transactions = fetch_transactions(league)
    accepts = [
        transaction
        for transaction in transactions
        if transaction.get("type") == "TRADE_ACCEPT" and transaction.get("status") in {"EXECUTED", None}
    ]
    adds = {
        (item.get("playerId"), item.get("toTeamId"))
        for transaction in transactions
        if is_executed_acquisition(transaction)
        for item in transaction.get("items", [])
        if item.get("type") == "ADD"
    }

    ownership_by_period = [{pick.playerId: pick.team.team_id for pick in league.draft}]
    acquired_by_trade: dict[int, list[tuple[int, int]]] = {}
    for period in range(1, int(league.current_week) + 1):
        data = league.espn_request.league_get(params={"view": "mRoster", "scoringPeriodId": period})
        ownership = {}
        for team in data.get("teams", []):
            for entry in team.get("roster", {}).get("entries", []):
                ownership[entry["playerId"]] = team["id"]
                if entry.get("acquisitionType") == "TRADE" and entry.get("acquisitionDate"):
                    acquired_by_trade.setdefault(entry["acquisitionDate"], []).append((entry["playerId"], team["id"]))
        ownership_by_period.append(ownership)
    return reconstruct_trades(league, accepts, adds, ownership_by_period, acquired_by_trade)


def _accepted_at(accept: dict[str, Any]) -> int:
    return accept.get("processDate") or accept["proposedDate"]


def _scoring_period(accept: dict[str, Any], period_count: int) -> int:
    return min(max(int(accept.get("scoringPeriodId") or 1), 1), period_count - 1)


def _match_acquisition_times(
    accepts: list[dict[str, Any]], acquired_by_trade: dict[int, list[tuple[int, int]]]
) -> dict[str, list[int]]:
    """Pair each accepted trade with the roster acquisition timestamps it produced.

    Trades under league review execute later than they are accepted, so
    unmatched accepts claim the next unclaimed time within REVIEW_WINDOW_MS.
    """
    matched = {
        accept["id"]: [
            acquired_at
            for acquired_at in acquired_by_trade
            if abs(acquired_at - _accepted_at(accept)) <= ACQUISITION_TOLERANCE_MS
        ]
        for accept in accepts
    }
    claimed = {acquired_at for times in matched.values() for acquired_at in times}
    for accept in sorted(accepts, key=_accepted_at):
        if matched[accept["id"]]:
            continue
        later = sorted(
            acquired_at
            for acquired_at in acquired_by_trade
            if acquired_at not in claimed and 0 <= acquired_at - _accepted_at(accept) <= REVIEW_WINDOW_MS
        )
        if later:
            matched[accept["id"]] = [later[0]]
            claimed.add(later[0])
    return matched


def reconstruct_trades(
    league: Any,
    accepts: list[dict[str, Any]],
    adds: set[tuple[int, int]],
    ownership_by_period: list[dict[int, int]],
    acquired_by_trade: dict[int, list[tuple[int, int]]],
) -> list[EspnActivity]:
    """Turn accepted-trade records into activities.

    `ownership_by_period[p]` maps player -> team after scoring period p (index 0 is the draft).
    `adds` holds (player, team) waiver/FA pickups so those moves are not mistaken for trades.
    """
    teams = {team.team_id: team for team in league.teams}
    player_map = getattr(league, "player_map", {})
    matched = _match_acquisition_times(accepts, acquired_by_trade)
    trades = []
    for accept in accepts:
        times = matched[accept["id"]]
        traded_at = min(times) if times else _accepted_at(accept)
        moves = {
            item["playerId"]: (item["fromTeamId"], item["toTeamId"])
            for item in accept.get("items", [])
            if item.get("type") == "TRADE"
        }
        received = [acquisition for acquired_at in times for acquisition in acquired_by_trade[acquired_at]]
        parties = {team_id for _, team_id in received} | {team_id for move in moves.values() for team_id in move}
        if len(parties) < 2:
            # The accepting team may be omitted when a league manager processes the trade.
            parties.add(accept.get("teamId"))
        parties.discard(None)
        period = _scoring_period(accept, len(ownership_by_period))
        before, after = ownership_by_period[period - 1], ownership_by_period[period]
        direct_moves = [
            (player_id, before[player_id], team_id)
            for player_id, team_id in after.items()
            if player_id in before and before[player_id] != team_id and (player_id, team_id) not in adds
        ]
        if len(parties) == 1:
            partners = {old for _, old, new in direct_moves if new in parties} | {
                new for _, old, new in direct_moves if old in parties
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
            and _scoring_period(candidate, len(ownership_by_period)) == period
            and candidate.get("teamId") in parties
            for candidate in accepts
        )
        if not shares_period:
            for player_id, old, new in direct_moves:
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
