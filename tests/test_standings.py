from datetime import date, timedelta
from types import SimpleNamespace
import unittest

from tests.fixtures.builders import box_entry
from trade_time_machine.game_weeks import week_start
from trade_time_machine.standings import alternate_standings, lineup_gap


class AlternateStandingsTest(unittest.TestCase):
    def test_rewinds_trade_but_respects_later_waiver_acquisition(self):
        original = SimpleNamespace(team_id=1, team_name="Original")
        recipient = SimpleNamespace(team_id=2, team_name="Recipient")
        traded = box_entry(100, "Traded", "WR", 25, 10, ["WR"])
        qb_a = box_entry(101, "QB A", "QB", 10, 8, ["QB"])
        qb_b = box_entry(201, "QB B", "QB", 10, 8, ["QB"])
        league = SimpleNamespace(
            year=2026,
            current_week=3,
            teams=[original, recipient],
            settings=SimpleNamespace(position_slot_counts={"QB": 1, "WR": 1, "BE": 4, "IR": 1}),
            box_scores=lambda week: [
                SimpleNamespace(
                    home_team=original,
                    away_team=recipient,
                    home_score=10,
                    away_score=35,
                    home_lineup=[qb_a],
                    away_lineup=[qb_b, traded],
                )
            ],
        )
        waiver = {
            "id": "waiver",
            "type": "WAIVER",
            "status": "EXECUTED",
            "processDate": int((week_start(2026, 2) + timedelta(hours=1)).timestamp() * 1000),
            "items": [{"type": "ADD", "playerId": 100, "toTeamId": 2}],
        }
        league.espn_request = SimpleNamespace(
            league_get=lambda params: {
                "transactions": [waiver] if params["scoringPeriodId"] == 2 else [],
            }
        )
        trade = {
            "traded_at": (week_start(2026, 1) - timedelta(days=1)).isoformat(),
            "sides": [
                {"team_id": 1, "sent": [{"id": 100}]},
                {"team_id": 2, "sent": [{"id": 200}]},
            ],
        }
        standings = alternate_standings(league, [trade], date(2026, 8, 30))
        a, b = standings["teams"]
        self.assertEqual(
            [{"week": week["week"], "rewound_players": week["rewound_players"]} for week in standings["weeks"]],
            [
                {"week": 1, "rewound_players": 1},
                {"week": 2, "rewound_players": 0},
            ],
        )
        self.assertEqual((a["actual_wins"], a["alternate_wins"], a["alternate_losses"]), (0, 1, 1))
        self.assertEqual((a["optimal_actual_points"], a["alternate_points"]), (20, 45))
        self.assertEqual((b["alternate_points"], b["actual_points"]), (45, 70))

    def test_no_trades_preserves_optimal_current_roster_results(self):
        home = SimpleNamespace(team_id=1, team_name="Home")
        away = SimpleNamespace(team_id=2, team_name="Away")
        league = SimpleNamespace(
            year=2026,
            current_week=2,
            teams=[home, away],
            settings=SimpleNamespace(position_slot_counts={"QB": 1}),
            espn_request=SimpleNamespace(league_get=lambda params: {"transactions": []}),
            box_scores=lambda week: [
                SimpleNamespace(
                    home_team=home,
                    away_team=away,
                    home_score=3,
                    away_score=6,
                    home_lineup=[
                        box_entry(1, "Starter", "QB", 3, 0, ["QB"]),
                        box_entry(2, "Bench", "BE", 9, 0, ["QB"]),
                    ],
                    away_lineup=[box_entry(3, "Opponent", "QB", 6, 0, ["QB"])],
                )
            ],
        )
        standings = alternate_standings(league, [], date(2026, 8, 30))
        home_row = standings["teams"][0]
        self.assertEqual((home_row["actual_losses"], home_row["optimal_actual_wins"]), (1, 1))
        self.assertEqual(home_row["wins_change"], 0)
        self.assertEqual(home_row["alternate_points"], home_row["optimal_actual_points"])


class BoxScoreValidationTest(unittest.TestCase):
    def league(self, boxes, transactions=()):
        home = SimpleNamespace(team_id=1, team_name="Home")
        away = SimpleNamespace(team_id=2, team_name="Away")
        stranger = SimpleNamespace(team_id=9, team_name="Stranger")
        entry = box_entry(1, "QB", "QB", 1, 0, ["QB"])

        def box(left, right):
            return SimpleNamespace(
                home_team=left,
                away_team=right,
                home_score=1,
                away_score=1,
                home_lineup=[entry],
                away_lineup=[],
            )

        pairs = {
            "normal": [(home, away)],
            "unknown": [(home, stranger)],
            "duplicate": [(home, away), (home, away)],
            "missing": [],
        }[boxes]
        return SimpleNamespace(
            year=2026,
            current_week=2,
            teams=[home, away],
            settings=SimpleNamespace(position_slot_counts={"QB": 1}),
            espn_request=SimpleNamespace(league_get=lambda params: {"transactions": list(transactions)}),
            box_scores=lambda week: [box(left, right) for left, right in pairs],
        )

    def test_rejects_inconsistent_box_scores(self):
        for boxes, error in (
            ("unknown", "unknown team"),
            ("duplicate", "duplicate box scores"),
            ("missing", "missing box scores"),
        ):
            with self.subTest(boxes=boxes), self.assertRaisesRegex(ValueError, error):
                alternate_standings(self.league(boxes), [], date(2026, 8, 30))

    def test_acquisitions_need_timestamps_and_respect_the_cutoff(self):
        undated = {"id": "w", "type": "FREEAGENT", "status": "EXECUTED", "items": []}
        with self.assertRaisesRegex(ValueError, "no timestamp"):
            alternate_standings(self.league("normal", [undated]), [], date(2026, 8, 30))
        preseason = {**undated, "processDate": 1_000, "items": [{"type": "ADD", "playerId": 1, "toTeamId": 2}]}
        standings = alternate_standings(self.league("normal", [preseason]), [], date(2026, 8, 30))
        self.assertEqual([(week["week"], week["rewound_players"]) for week in standings["weeks"]], [(1, 0)])
        self.assertEqual(standings["teams"][0]["actual_ties"], 1)


class LineupGapTest(unittest.TestCase):
    @staticmethod
    def player(player_id, slot, points, eligible):
        return {
            "id": player_id,
            "name": f"P{player_id}",
            "slot": slot,
            "points": points,
            "projected": 0,
            "eligible": eligible,
        }

    def test_points_left_compare_best_lineup_with_actual_starters_and_ignore_ir(self):
        roster = {
            1: self.player(1, "QB", 10, ["QB"]),
            2: self.player(2, "WR", 4, ["WR", "RB/WR/TE"]),
            3: self.player(3, "RB/WR/TE", 3, ["RB", "RB/WR/TE"]),
            4: self.player(4, "BE", 20, ["WR", "RB/WR/TE"]),
            5: self.player(5, "BE", 20, ["QB"]),
            6: self.player(6, "IR", 50, ["RB", "RB/WR/TE"]),
        }
        gap = lineup_gap(7, "Team", roster, ["QB", "WR", "RB/WR/TE"])
        self.assertEqual(
            gap,
            {
                "team_id": 7,
                "team": "Team",
                "actual_points": 17.0,
                "optimal_points": 44.0,
                "points_left": 27.0,
                "top_bench": {"id": 4, "name": "P4", "points": 20},
            },
        )

    def test_perfect_lineup_without_bench_leaves_nothing(self):
        gap = lineup_gap(1, "Team", {1: self.player(1, "QB", 9.5, ["QB"])}, ["QB"])
        self.assertEqual((gap["points_left"], gap["top_bench"]), (0.0, None))


if __name__ == "__main__":
    unittest.main()
