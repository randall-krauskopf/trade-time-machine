"""Deterministic stand-ins for espn_api League objects.

`activity_league()` exercises the member activity-feed path. It has these
trades:

- a pre-cutoff trade (excluded)
- a preseason trade (counted from Week 1)
- two Week 2 trades by one manager (bundled; one player passes through them)
- a trade in the in-progress Week 3 (no completed weeks yet)

It also has a waiver pickup and two completed weeks of box scores.

`reconstructed_league()` exercises the fallback used when ESPN's activity feed
is members-only: trades are rebuilt from accepted-trade records and rosters.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from espn_api.requests.espn_requests import ESPNAccessDenied

CHICAGO = ZoneInfo("America/Chicago")
SLOT_COUNTS = {"QB": 1, "RB": 1, "WR": 1, "RB/WR/TE": 1, "BE": 2, "IR": 1}
POSITION_SLOTS = {
    "QB": ["QB", "OP"],
    "RB": ["RB", "RB/WR/TE"],
    "WR": ["WR", "RB/WR/TE"],
}


def millis(when: datetime) -> int:
    return int(when.timestamp() * 1000)


def team(team_id: int, name: str) -> SimpleNamespace:
    # Trailing spaces mirror ESPN names; the generator strips them.
    return SimpleNamespace(team_id=team_id, team_name=f"{name} ")


TEAMS = {
    1: team(1, "All Gold"),
    2: team(2, "Boom Baum"),
    3: team(3, "Shiny Hineys"),
    4: team(4, "Cowboys"),
}

# player_id: (name, position, {week: (points, projected)})
PLAYERS = {
    101: ("QB Alpha", "QB", {1: (20.5, 18.0), 2: (15.2, 17.5)}),
    102: ("QB Bravo", "QB", {1: (12.0, 16.0), 2: (25.4, 16.5)}),
    103: ("QB Charlie", "QB", {1: (18.8, 17.0), 2: (9.6, 16.0)}),
    104: ("QB Delta", "QB", {1: (22.1, 19.0), 2: (19.9, 18.0)}),
    201: ("RB Alpha", "RB", {1: (8.4, 11.0), 2: (14.0, 11.5)}),
    202: ("RB Bravo", "RB", {1: (17.3, 13.0), 2: (6.1, 12.5)}),
    203: ("RB Charlie", "RB", {1: (11.0, 12.0), 2: (13.3, 12.0)}),
    204: ("RB Delta", "RB", {1: (5.5, 9.0), 2: (21.7, 10.0)}),
    206: ("RB Foxtrot", "RB", {1: (9.0, 10.0), 2: (7.5, 10.0)}),
    301: ("WR Alpha", "WR", {1: (19.9, 14.0), 2: (3.2, 14.5)}),
    302: ("WR Bravo", "WR", {1: (7.7, 12.0), 2: (16.6, 12.0)}),
    303: ("WR Charlie", "WR", {1: (13.1, 13.5), 2: (24.0, 13.0)}),
    304: ("WR Delta", "WR", {1: (9.9, 11.0), 2: (10.1, 11.0)}),
    305: ("WR Echo", "WR", {1: (12.2, 10.0), 2: (6.4, 10.5)}),
    401: ("Bench RB One", "RB", {1: (4.0, 8.0), 2: (12.5, 9.5)}),
    402: ("Bench WR Two", "WR", {1: (6.6, 7.0), 2: (2.0, 7.5)}),
    403: ("Bench WR Three", "WR", {1: (10.4, 9.0), 2: (8.8, 9.0)}),
    404: ("Bench RB Four", "RB", {1: (3.3, 6.0), 2: (15.5, 10.5)}),
    499: ("Waiver WR", "WR", {2: (11.1, 8.0)}),
}

# Box-score lineups by week and team: [(player_id, slot)].
LINEUPS = {
    1: {
        1: [(101, "QB"), (202, "RB"), (305, "WR"), (201, "RB/WR/TE"), (401, "BE")],
        2: [(102, "QB"), (206, "RB"), (301, "WR"), (302, "RB/WR/TE"), (402, "BE")],
        3: [(103, "QB"), (203, "RB"), (303, "WR"), (403, "RB/WR/TE")],
        4: [(104, "QB"), (204, "RB"), (304, "WR"), (404, "RB/WR/TE")],
    },
    2: {
        1: [(101, "QB"), (202, "RB"), (305, "WR"), (404, "RB/WR/TE"), (201, "BE")],
        2: [(102, "QB"), (206, "RB"), (301, "WR"), (302, "RB/WR/TE"), (499, "BE"), (402, "BE")],
        3: [(103, "QB"), (203, "RB"), (403, "WR"), (401, "RB/WR/TE")],
        4: [(104, "QB"), (204, "RB"), (304, "WR"), (303, "RB/WR/TE")],
    },
}
MATCHUPS = {1: [(1, 2), (3, 4)], 2: [(1, 3), (2, 4)]}


def player_namespace(player_id: int) -> SimpleNamespace:
    name, position, weeks = PLAYERS[player_id]
    return SimpleNamespace(
        playerId=player_id,
        name=name,
        eligibleSlots=POSITION_SLOTS[position],
        stats={week: {"points": points, "projected_points": projected} for week, (points, projected) in weeks.items()},
    )


def box_entry(player_id: int, slot: str, week: int) -> SimpleNamespace:
    name, position, weeks = PLAYERS[player_id]
    points, projected = weeks.get(week, (0.0, 0.0))
    return SimpleNamespace(
        playerId=player_id,
        name=name,
        slot_position=slot,
        points=points,
        projected_points=projected,
        eligibleSlots=POSITION_SLOTS[position],
    )


def lineup_score(lineup: list[SimpleNamespace]) -> float:
    return round(sum(entry.points for entry in lineup if entry.slot_position not in {"BE", "IR"}), 2)


def box_scores(week: int) -> list[SimpleNamespace]:
    boxes = []
    for home_id, away_id in MATCHUPS[week]:
        home = [box_entry(player_id, slot, week) for player_id, slot in LINEUPS[week][home_id]]
        away = [box_entry(player_id, slot, week) for player_id, slot in LINEUPS[week][away_id]]
        boxes.append(
            SimpleNamespace(
                home_team=TEAMS[home_id],
                away_team=TEAMS[away_id],
                home_score=lineup_score(home),
                away_score=lineup_score(away),
                home_lineup=home,
                away_lineup=away,
            )
        )
    return boxes


def trade_activity(when: datetime, *moves: tuple[int, int, int]) -> SimpleNamespace:
    """Each move is (player_id, from_team_id, to_team_id)."""
    actions = []
    for player_id, sender, receiver in moves:
        player = SimpleNamespace(playerId=player_id, name=PLAYERS[player_id][0])
        actions.append((TEAMS[sender], "TRADE_SENT", player, 0))
        actions.append((TEAMS[receiver], "TRADE_RECEIVED", player, 0))
    return SimpleNamespace(date=millis(when), actions=actions)


ACTIVITY_TRADES = [
    trade_activity(datetime(2026, 8, 29, 21, 0, tzinfo=CHICAGO), (104, 4, 3), (103, 3, 4)),
    trade_activity(datetime(2026, 9, 2, 19, 30, tzinfo=CHICAGO), (301, 1, 2), (202, 2, 1)),
    trade_activity(datetime(2026, 9, 15, 20, 5, tzinfo=CHICAGO), (303, 3, 4), (404, 4, 3)),
    trade_activity(datetime(2026, 9, 16, 9, 45, tzinfo=CHICAGO), (404, 3, 1), (401, 1, 3)),
    trade_activity(datetime(2026, 9, 23, 12, 0, tzinfo=CHICAGO), (302, 2, 4), (304, 4, 2)),
]

WAIVER = {
    "id": "waiver-499",
    "type": "WAIVER",
    "status": "EXECUTED",
    "processDate": millis(datetime(2026, 9, 16, 4, 0, tzinfo=CHICAGO)),
    "items": [{"type": "ADD", "playerId": 499, "toTeamId": 2}],
}

DISCORD_EXPORT = {
    "messages": [
        {
            "guild_id": "1160416084235661426",
            "channel_id": "1160416085326188557",
            "message_id": "9001",
            "sent_at": "2026-09-16T15:30:00Z",
            "author_name": "commish",
            "content": "Bench RB Four is on the move again",
        },
        {
            "guild_id": "1160416084235661426",
            "channel_id": "1160416085326188557",
            "message_id": "9002",
            "sent_at": "2026-09-16T16:00:00Z",
            "author_name": "bot",
            "author_bot": True,
            "content": "Bench RB Four traded",
        },
    ],
}


class ActivityLeague:
    def __init__(self) -> None:
        self.year = 2026
        self.current_week = 3
        self.settings = SimpleNamespace(name="Fixture Premier", position_slot_counts=SLOT_COUNTS)
        self.teams = list(TEAMS.values())
        self.espn_request = SimpleNamespace(league_get=self._league_get)

    def _league_get(self, params: dict) -> dict:
        if params.get("view") == "mTransactions2":
            return {"transactions": [WAIVER] if params["scoringPeriodId"] == 2 else []}
        raise AssertionError(f"Unexpected ESPN view: {params}")

    def recent_activity(self, size: int, offset: int) -> list[SimpleNamespace]:
        return list(reversed(ACTIVITY_TRADES))[offset : offset + size]

    def player_info(self, playerId: list[int]) -> list[SimpleNamespace]:
        return [player_namespace(player_id) for player_id in playerId]

    def box_scores(self, week: int) -> list[SimpleNamespace]:
        return box_scores(week)


def activity_league() -> ActivityLeague:
    return ActivityLeague()


class ReconstructedLeague:
    """Members-only feed and no box scores, so standings and weekly moves are omitted."""

    ACCEPTED_AT = millis(datetime(2026, 9, 10, 8, 0, tzinfo=CHICAGO))

    def __init__(self) -> None:
        self.year = 2026
        self.current_week = 2
        self.settings = SimpleNamespace(name="Fixture Champeens", position_slot_counts=SLOT_COUNTS)
        self.teams = [TEAMS[1], TEAMS[2]]
        self.player_map = {player_id: name for player_id, (name, _, _) in PLAYERS.items()}
        self.draft = [
            SimpleNamespace(playerId=101, team=TEAMS[1]),
            SimpleNamespace(playerId=102, team=TEAMS[2]),
            SimpleNamespace(playerId=201, team=TEAMS[1]),
        ]
        self.espn_request = SimpleNamespace(league_get=self._league_get)

    def _league_get(self, params: dict) -> dict:
        period = params["scoringPeriodId"]
        if params["view"] == "mTransactions2":
            if period != 1:
                return {"transactions": []}
            return {
                "transactions": [
                    {
                        "id": "accept-1",
                        "type": "TRADE_ACCEPT",
                        "status": "EXECUTED",
                        "teamId": 2,
                        "proposedDate": self.ACCEPTED_AT,
                        "scoringPeriodId": 1,
                        "items": [],
                    }
                ]
            }
        if params["view"] == "mRoster":
            acquired = {"acquisitionType": "TRADE", "acquisitionDate": self.ACCEPTED_AT + 250}
            return {
                "teams": [
                    {"id": 1, "roster": {"entries": [{"playerId": 102, **acquired}, {"playerId": 201}]}},
                    {"id": 2, "roster": {"entries": [{"playerId": 101, **acquired}]}},
                ]
            }
        raise AssertionError(f"Unexpected ESPN view: {params}")

    def recent_activity(self, size: int, offset: int) -> list[SimpleNamespace]:
        raise ESPNAccessDenied("members only")

    def player_info(self, playerId: list[int]) -> list[SimpleNamespace]:
        return [player_namespace(player_id) for player_id in playerId]


def reconstructed_league() -> ReconstructedLeague:
    return ReconstructedLeague()
