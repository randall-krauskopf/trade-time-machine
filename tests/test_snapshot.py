from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo

from tests.fixtures.builders import FakeLeague, box_entry, player
from trade_time_machine.game_weeks import week_start
from trade_time_machine.snapshot import build_snapshot

FIRST_TRADE_DATE = date(2026, 8, 30)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.players = {
            1: player(1, "Cam Skattebo", {1: 14.1, 2: 4.9}),
            2: player(2, "TreVeyon Henderson", {1: 0.0, 2: 13.6}),
        }

    def test_full_weeks_and_received_player_points(self):
        league = FakeLeague(week_start(2026, 1).replace(day=9), self.players)
        trade = build_snapshot(league, [], FIRST_TRADE_DATE)["trades"][0]
        self.assertEqual(trade["weeks"], [1, 2])
        self.assertEqual(trade["sides"][0]["total_points"], 13.6)
        self.assertEqual(trade["sides"][1]["total_points"], 19.0)
        self.assertEqual(trade["sides"][0]["received"][0]["name"], "TreVeyon Henderson")

    def test_midweek_trade_includes_completed_trade_week(self):
        league = FakeLeague(week_start(2026, 2) + timedelta(hours=2), self.players)
        trade = build_snapshot(league, [], FIRST_TRADE_DATE)["trades"][0]
        self.assertEqual(trade["weeks"], [2])
        self.assertEqual(trade["trade_week"], 2)
        self.assertEqual(trade["sides"][0]["total_points"], 13.6)

    def test_tuesday_trade_does_not_include_previous_week(self):
        self.assertEqual(week_start(2026, 2).astimezone(ZoneInfo("America/Chicago")).date().isoformat(), "2026-09-15")
        league = FakeLeague(datetime(2026, 9, 15, 18, tzinfo=ZoneInfo("America/Chicago")), self.players)
        trade = build_snapshot(league, [], FIRST_TRADE_DATE)["trades"][0]
        self.assertEqual(trade["weeks"], [2])
        self.assertEqual(trade["trade_week"], 2)

    def test_trade_after_last_completed_week_has_no_final_scores(self):
        league = FakeLeague(week_start(2026, 3) + timedelta(hours=2), self.players)
        trade = build_snapshot(league, [], FIRST_TRADE_DATE)["trades"][0]
        self.assertEqual(trade["weeks"], [])
        self.assertIsNone(trade["trade_week"])
        self.assertIsNone(trade["sides"][0]["total_points"])

    def test_missing_points_are_not_reported_as_zero(self):
        self.players[2].stats.pop(2)
        league = FakeLeague(week_start(2026, 1).replace(day=9), self.players)
        side = build_snapshot(league, [], FIRST_TRADE_DATE)["trades"][0]["sides"][0]
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
        snapshot = build_snapshot(league, [], FIRST_TRADE_DATE)
        self.assertEqual(snapshot["first_trade_date"], "2026-08-30")
        self.assertEqual(len(snapshot["trades"]), 1)
        self.assertEqual(snapshot["trades"][0]["traded_at"], cutoff.astimezone(UTC).isoformat())

    def test_configured_cutoff_is_local_midnight_inclusive(self):
        before = datetime(2026, 9, 1, 23, 59, tzinfo=ZoneInfo("America/Chicago"))
        at_cutoff = datetime(2026, 9, 2, 0, 0, tzinfo=ZoneInfo("America/Chicago"))
        league = FakeLeague(before, self.players)
        league.trades.append(FakeLeague(at_cutoff, self.players).trade)
        configured = build_snapshot(league, [], date(2026, 9, 2))
        self.assertEqual(len(configured["trades"]), 1)
        self.assertEqual(configured["first_trade_date"], "2026-09-02")
        self.assertEqual(len(build_snapshot(league, [], date(2026, 9, 1))["trades"]), 2)

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
        league.box_scores = lambda week: [
            SimpleNamespace(
                home_team=left,
                away_team=right,
                home_score=100,
                away_score=90,
                home_lineup=[
                    box_entry(
                        2 if week == 1 else 1, "Received first" if week == 1 else "Received later", "WR", 20, 10, ["WR"]
                    )
                ],
                away_lineup=[
                    box_entry(1 if week == 1 else 2, "Sent first" if week == 1 else "Sent later", "WR", 10, 10, ["WR"])
                ],
            )
        ]
        trades = build_snapshot(league, [], FIRST_TRADE_DATE)["trades"]
        earlier = next(trade for trade in trades if trade["traded_at"] == first.astimezone(UTC).isoformat())
        self.assertEqual(earlier["sides"][0]["received"][0]["weeks"]["2"], 13.6)
        self.assertEqual(earlier["sides"][0]["total_points"], 13.6)
        self.assertNotIn("impact_cutoff", earlier)
        self.assertTrue(all("impact" not in side for side in earlier["sides"]))

    def test_single_player_lookup_and_non_trades(self):
        league = FakeLeague(week_start(2026, 1).replace(day=9), self.players)
        waiver = SimpleNamespace(
            date=league.trade.date, actions=[(league.teams[0], "WAIVER ADDED", self.players[1], 5)]
        )
        league.trades.append(waiver)
        league.player_info = lambda playerId: self.players[1] if playerId == [1] else None
        league.trade.actions = league.trade.actions[:2] + [(league.teams[1], "TRADE_SENT", None, 0)]
        trade = build_snapshot(league, [], FIRST_TRADE_DATE)["trades"][0]
        self.assertEqual([side["team_id"] for side in trade["sides"]], [2, 10])
        self.assertEqual(trade["sides"][1]["received"][0]["weeks"], {"1": 14.1, "2": 4.9})

    def test_one_sided_trade_fails_loudly(self):
        league = FakeLeague(week_start(2026, 1).replace(day=9), self.players)
        league.trade.actions = league.trade.actions[:1]
        with self.assertRaisesRegex(ValueError, "two teams"):
            build_snapshot(league, [], FIRST_TRADE_DATE)

    def test_reconstructed_source_when_activity_feed_is_denied(self):
        from unittest.mock import patch

        from espn_api.requests.espn_requests import ESPNAccessDenied

        league = FakeLeague(week_start(2026, 1).replace(day=9), self.players)
        league.recent_activity = lambda size, offset: (_ for _ in ()).throw(ESPNAccessDenied("members only"))
        with patch("trade_time_machine.snapshot.fetch_reconstructed_trades", return_value=[league.trade]):
            snapshot = build_snapshot(league, [], FIRST_TRADE_DATE)
        self.assertEqual(snapshot["source"], "reconstructed")
        self.assertEqual(len(snapshot["trades"]), 1)


if __name__ == "__main__":
    unittest.main()
