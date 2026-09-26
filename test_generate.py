import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from generate import GUILD_ID, build_snapshot, parse_discord_export, reconstruct_trades, week_start


def player(player_id, name, week_points):
    return SimpleNamespace(
        playerId=player_id,
        name=name,
        stats={week: {"points": points} for week, points in week_points.items()},
    )


class FakeLeague:
    def __init__(self, traded_at, players, additional_trades=None):
        self.year = 2026
        self.current_week = 3
        self.settings = SimpleNamespace(name="Test Premier")
        left = SimpleNamespace(team_id=2, team_name="All Gold")
        right = SimpleNamespace(team_id=10, team_name="Boom Baum")
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
        return self.trades[offset:offset + size]

    def player_info(self, playerId):
        return [self.players[key] for key in playerId]


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.players = {
            1: player(1, "Cam Skattebo", {1: 14.1, 2: 4.9}),
            2: player(2, "TreVeyon Henderson", {1: 0.0, 2: 13.6}),
        }

    def test_full_weeks_and_received_player_points(self):
        league = FakeLeague(week_start(2026, 1).replace(day=9), self.players)
        trade = build_snapshot(league, [])["trades"][0]
        self.assertEqual(trade["weeks"], [1, 2])
        self.assertEqual(trade["sides"][0]["total_points"], 13.6)
        self.assertEqual(trade["sides"][1]["total_points"], 19.0)
        self.assertEqual(trade["sides"][0]["received"][0]["name"], "TreVeyon Henderson")

    def test_midweek_trade_includes_completed_trade_week(self):
        league = FakeLeague(week_start(2026, 2) + timedelta(hours=2), self.players)
        trade = build_snapshot(league, [])["trades"][0]
        self.assertEqual(trade["weeks"], [2])
        self.assertEqual(trade["trade_week"], 2)
        self.assertEqual(trade["sides"][0]["total_points"], 13.6)

    def test_trade_after_last_completed_week_has_no_final_scores(self):
        league = FakeLeague(week_start(2026, 3) + timedelta(hours=2), self.players)
        trade = build_snapshot(league, [])["trades"][0]
        self.assertEqual(trade["weeks"], [])
        self.assertIsNone(trade["trade_week"])
        self.assertIsNone(trade["sides"][0]["total_points"])

    def test_missing_points_are_not_reported_as_zero(self):
        self.players[2].stats.pop(2)
        league = FakeLeague(week_start(2026, 1).replace(day=9), self.players)
        side = build_snapshot(league, [])["trades"][0]["sides"][0]
        self.assertIsNone(side["weekly_points"]["2"])
        self.assertIsNone(side["total_points"])

    def test_cutoff_uses_league_local_date_inclusively(self):
        chicago = ZoneInfo("America/Chicago")
        before = datetime(2026, 8, 29, 23, 59, tzinfo=chicago)
        cutoff = datetime(2026, 8, 30, 0, 0, tzinfo=chicago)
        league = FakeLeague(before, self.players)
        # A midnight-local trade is included, even though both timestamps
        # occur on August 30 in UTC.
        at_cutoff = FakeLeague(cutoff, self.players).trade
        league.trades.append(at_cutoff)
        snapshot = build_snapshot(league, [])
        self.assertEqual(snapshot["first_trade_date"], "2026-08-30")
        self.assertEqual(len(snapshot["trades"]), 1)
        self.assertEqual(snapshot["trades"][0]["traded_at"], cutoff.astimezone(timezone.utc).isoformat())

    def test_later_retrade_does_not_remove_points_from_original_deal(self):
        first = week_start(2026, 1) - timedelta(days=1)
        second = week_start(2026, 2) + timedelta(hours=2)
        league = FakeLeague(first, self.players)
        original = league.trade
        later = FakeLeague(second, self.players).trade
        # Henderson is sent away by the original receiving team in the later deal.
        left, right = later.actions[0][0], later.actions[1][0]
        later.actions = [
            (left, "TRADE_SENT", self.players[2], 0),
            (right, "TRADE_RECEIVED", self.players[2], 0),
            (right, "TRADE_SENT", self.players[1], 0),
            (left, "TRADE_RECEIVED", self.players[1], 0),
        ]
        league.trades = [later, original]
        trades = build_snapshot(league, [])["trades"]
        earlier = next(trade for trade in trades if trade["traded_at"] == first.isoformat())
        self.assertEqual(earlier["sides"][0]["received"][0]["weeks"]["2"], 13.6)
        self.assertEqual(earlier["sides"][0]["total_points"], 13.6)

    def test_discord_filter_and_proximity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "messages.json"
            path.write_text(json.dumps([
                {
                    "guild_id": str(GUILD_ID), "channel_id": "1160416085326188557",
                    "message_id": "12345", "sent_at": "2026-09-09T09:00:00Z",
                    "author_name": "coach", "content": "TreVeyon Henderson is a steal",
                },
                {
                    "guild_id": str(GUILD_ID), "channel_id": "1278864199740686466",
                    "message_id": "12346", "sent_at": "2026-09-09T09:00:00Z",
                    "author_name": "coach", "content": "TreVeyon Henderson is a steal",
                },
            ]), encoding="utf-8")
            messages = parse_discord_export(path)
            self.assertEqual(len(messages), 1)
            league = FakeLeague(week_start(2026, 1).replace(day=9), self.players)
            receipt = build_snapshot(league, messages)["trades"][0]["receipts"][0]
            self.assertEqual(receipt["channel"], "trade-talk")
            self.assertTrue(receipt["url"].endswith("/12345"))

    def test_bad_export_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "messages.json"
            path.write_text('{"messages": {}}', encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_discord_export(path)


class ReconstructTradesTest(unittest.TestCase):
    def setUp(self):
        self.league = SimpleNamespace(
            teams=[SimpleNamespace(team_id=team_id, team_name=f"Team {team_id}") for team_id in (1, 2, 3)],
            player_map={10: "Kept", 11: "Retraded", 12: "Waiver pickup", 20: "Other kept"},
        )

    def received(self, trades):
        return sorted((team.team_id, player.name) for trade in trades
                      for team, action, player, _ in trade.actions if action == "TRADE_RECEIVED")

    def test_uses_acquisitions_and_unambiguous_roster_moves(self):
        accepted_at = 1_000_000
        accepts = [{"id": "a", "teamId": 2, "proposedDate": accepted_at, "scoringPeriodId": 1, "items": []}]
        snapshots = [{10: 1, 11: 2, 12: 1, 20: 2}, {10: 2, 11: 1, 12: 3, 20: 1}]
        trades = reconstruct_trades(
            self.league, accepts, {(12, 3)}, snapshots,
            {accepted_at + 500: [(10, 2), (20, 1)]},
        )
        self.assertEqual(self.received(trades), [(1, "Other kept"), (1, "Retraded"), (2, "Kept")])
        self.assertEqual(trades[0].date, accepted_at + 500)

    def test_review_delayed_trade_claims_next_acquisition_time(self):
        accepted_at = 1_000_000
        executed_at = accepted_at + 6 * 60 * 60 * 1000
        accepts = [{"id": "a", "teamId": 1, "proposedDate": accepted_at, "scoringPeriodId": 1, "items": []}]
        trades = reconstruct_trades(
            self.league, accepts, set(), [{10: 1, 20: 2}, {10: 2, 20: 1}],
            {executed_at: [(10, 2), (20, 1)]},
        )
        self.assertEqual(trades[0].date, executed_at)
        self.assertEqual(self.received(trades), [(1, "Other kept"), (2, "Kept")])


if __name__ == "__main__":
    unittest.main()
