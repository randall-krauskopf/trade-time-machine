"""Small builders for unit tests: fake ESPN players, box entries, and a one-trade league."""

from types import SimpleNamespace


def player(player_id, name, week_points):
    return SimpleNamespace(
        playerId=player_id,
        name=name,
        stats={week: {"points": points} for week, points in week_points.items()},
    )


def box_entry(player_id, name, slot, points, projected, eligible):
    return SimpleNamespace(
        playerId=player_id,
        name=name,
        slot_position=slot,
        points=points,
        projected_points=projected,
        eligibleSlots=eligible,
    )


def lineup_player(player_id, slot, points, projected, eligible):
    return {
        "id": player_id,
        "name": f"P{player_id}",
        "slot": slot,
        "points": points,
        "projected": projected,
        "eligible": eligible,
    }


class FakeLeague:
    def __init__(self, traded_at, players, additional_trades=None):
        self.year = 2026
        self.current_week = 3
        self.settings = SimpleNamespace(name="Test Premier", position_slot_counts={"WR": 1})
        left = SimpleNamespace(team_id=2, team_name="All Gold")
        right = SimpleNamespace(team_id=10, team_name="Boom Baum")
        self.teams = [left, right]
        self.espn_request = SimpleNamespace(league_get=lambda params: {"transactions": []})
        self.trade = SimpleNamespace(
            date=int(traded_at.timestamp() * 1000),
            actions=[
                (left, "TRADE_SENT", players[1], 0),
                (right, "TRADE_RECEIVED", players[1], 0),
                (right, "TRADE_SENT", players[2], 0),
                (left, "TRADE_RECEIVED", players[2], 0),
            ],
        )
        self.players = players
        self.trades = [self.trade, *(additional_trades or [])]

    def recent_activity(self, size, offset):
        return self.trades[offset : offset + size]

    def player_info(self, playerId):
        return [self.players[key] for key in playerId]
