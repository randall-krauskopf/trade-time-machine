"""Typed shapes for ESPN inputs and the data.json output.

The output types mirror schema/data.schema.json, which the contract tests
enforce. ESPN inputs are Protocols so test fakes (SimpleNamespace) and real
espn_api objects both fit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, NotRequired, Protocol, TypedDict

MatchupResult = Literal["W", "L", "T"]


# --- ESPN inputs -----------------------------------------------------------


class EspnTeam(Protocol):
    team_id: int
    team_name: str


class EspnPlayer(Protocol):
    """A player from `League.player_info`; `stats` is keyed by scoring week."""

    playerId: int
    name: str
    stats: dict[int, dict[str, Any]]


class EspnBoxPlayer(Protocol):
    playerId: int
    name: str
    slot_position: str
    points: float | None
    projected_points: float | None
    eligibleSlots: list[str]


class EspnBoxScore(Protocol):
    home_team: EspnTeam
    away_team: EspnTeam
    home_score: float
    away_score: float
    home_lineup: list[EspnBoxPlayer]
    away_lineup: list[EspnBoxPlayer]


class EspnActivity(Protocol):
    """One feed entry. `date` is epoch milliseconds; actions are (team, action, player, bid)."""

    date: int
    actions: list[tuple[EspnTeam, str, Any, int]]


# --- Generator internals ---------------------------------------------------


class LineupPlayer(TypedDict):
    id: int
    name: str
    slot: str
    points: float
    projected: float
    eligible: list[str]


class Replacement(TypedDict):
    slot: str
    name: str | None
    points: float
    replaced: str | None


class LineupEstimate(TypedDict):
    score: float
    replacements: list[Replacement]


class DiscordMessage(TypedDict):
    """A filtered export message; `url` is its permalink."""

    channel: str
    url: str
    author: str
    content: str
    sent_at: datetime


# --- data.json output ------------------------------------------------------


class PlayerRef(TypedDict):
    id: int
    name: str


class ReceivedPlayer(PlayerRef):
    weeks: dict[str, float | None]


class TradeSide(TypedDict):
    team_id: int
    team: str
    sent: list[PlayerRef]
    received: list[ReceivedPlayer]
    weekly_points: dict[str, float | None]
    total_points: float | None


class Receipt(TypedDict):
    channel: str
    author: str
    content: str
    sent_at: str
    url: str


class Trade(TypedDict):
    id: str
    traded_at: str
    transaction_week: int
    weeks: list[int]
    trade_week: int | None
    sides: list[TradeSide]
    receipts: list[Receipt]


class StandingsRow(TypedDict):
    team_id: int
    team: str
    actual_wins: int
    actual_losses: int
    actual_ties: int
    actual_points: float
    alternate_wins: int
    alternate_losses: int
    alternate_ties: int
    alternate_points: float
    optimal_actual_wins: int
    optimal_actual_losses: int
    optimal_actual_ties: int
    optimal_actual_points: float
    wins_change: float


class BenchPlayer(TypedDict):
    id: int
    name: str
    points: float


class LineupGap(TypedDict):
    team_id: int
    team: str
    actual_points: float
    optimal_points: float
    points_left: float
    top_bench: BenchPlayer | None


class ActualMatchup(TypedDict):
    home_team_id: int
    away_team_id: int
    home_score: float
    away_score: float


class AlternateWeek(TypedDict):
    week: int
    rewound_players: int
    lineups: list[LineupGap]
    matchups: list[ActualMatchup]


class AlternateStandings(TypedDict):
    weeks: list[AlternateWeek]
    teams: list[StandingsRow]
    source: Literal["weekly_box_scores"]


class WeeklyRow(TypedDict):
    week: int
    team_id: int
    team: str
    trade_count: int
    trade_ids: list[str]
    received: list[PlayerRef]
    sent: list[PlayerRef]
    actual_score: float
    alternate_score: float
    net_points: float
    opponent: str | None
    opponent_score: float
    opponent_alternate_score: float
    result: MatchupResult
    alternate_result: MatchupResult
    flipped: bool
    replacements: list[Replacement]
    snapshot_status: Literal["reconstructed_from_trades_and_weekly_box_score"]


class WeeklyRosterMoves(TypedDict):
    rows: list[WeeklyRow]
    source: Literal["weekly_trade_bundles"]
    omitted: NotRequired[list[OmittedWeeklyRow]]


class OmittedWeeklyRow(TypedDict):
    week: int
    team_id: int


class HistoricalTeam(TypedDict):
    team_id: int
    team: str


class LeagueSnapshot(TypedDict, total=False):
    league: str
    season: int
    generated_at: str
    completed_weeks: list[int]
    first_trade_date: str
    trades: list[Trade]
    alternate_standings: AlternateStandings | None
    weekly_roster_moves: WeeklyRosterMoves | None
    source: Literal["activity", "reconstructed"]
    discord_imported: bool
    # Added by the CLI from generator.json.
    key: str
    label: str
    receipts_enabled: bool
    teams: list[HistoricalTeam]
