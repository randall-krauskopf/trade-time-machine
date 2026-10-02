from types import SimpleNamespace
import unittest

from tests.fixtures.builders import box_entry
from trade_time_machine.weekly_moves import weekly_roster_moves


class WeeklyRosterMovesTest(unittest.TestCase):
    def test_bundles_same_week_trades_and_cancels_intermediate_players(self):
        manager = SimpleNamespace(team_id=1, team_name="Manager")
        opponent = SimpleNamespace(team_id=2, team_name="Opponent")
        league = SimpleNamespace(
            year=2026,
            current_week=2,
            box_scores=lambda week: [
                SimpleNamespace(
                    home_team=manager,
                    away_team=opponent,
                    home_score=100,
                    away_score=95,
                    home_lineup=[
                        box_entry(300, "Final WR", "WR", 30, 14, ["WR"]),
                        box_entry(400, "QB", "QB", 70, 20, ["QB"]),
                        box_entry(500, "Bench WR", "BE", 5, 8, ["WR"]),
                        box_entry(700, "Injured WR", "IR", 0, 0, ["WR"]),
                    ],
                    away_lineup=[box_entry(600, "Opponent QB", "QB", 95, 20, ["QB"])],
                )
            ],
        )
        trades = [
            {
                "id": "one",
                "transaction_week": 1,
                "sides": [
                    {
                        "team_id": 1,
                        "team": "Manager",
                        "received": [{"id": 200, "name": "Middle WR"}],
                        "sent": [{"id": 100, "name": "Original WR"}],
                    },
                    {
                        "team_id": 2,
                        "team": "Opponent",
                        "received": [{"id": 100, "name": "Original WR"}],
                        "sent": [{"id": 200, "name": "Middle WR"}],
                    },
                ],
            },
            {
                "id": "two",
                "transaction_week": 1,
                "sides": [
                    {
                        "team_id": 1,
                        "team": "Manager",
                        "received": [{"id": 300, "name": "Final WR"}],
                        "sent": [{"id": 200, "name": "Middle WR"}],
                    },
                    {
                        "team_id": 3,
                        "team": "Third",
                        "received": [{"id": 200, "name": "Middle WR"}],
                        "sent": [{"id": 300, "name": "Final WR"}],
                    },
                ],
            },
        ]
        players = {
            100: SimpleNamespace(
                playerId=100,
                name="Original WR",
                eligibleSlots=["WR"],
                stats={1: {"points": 10, "projected_points": 12}},
            ),
        }
        row = next(row for row in weekly_roster_moves(league, trades, players)["rows"] if row["team_id"] == 1)
        self.assertEqual(row["trade_count"], 2)
        self.assertEqual(row["received"], [{"id": 300, "name": "Final WR"}])
        self.assertEqual(row["sent"], [{"id": 100, "name": "Original WR"}])
        self.assertEqual(row["alternate_score"], 80)
        self.assertEqual(row["net_points"], 20)
        self.assertEqual((row["alternate_result"], row["result"], row["flipped"]), ("L", "W", True))
        self.assertEqual(
            row["final_lineup"],
            [
                {"id": 300, "name": "Final WR", "slot": "WR", "points": 30.0},
                {"id": 400, "name": "QB", "slot": "QB", "points": 70.0},
                {"id": 500, "name": "Bench WR", "slot": "BE", "points": 5.0},
                {"id": 700, "name": "Injured WR", "slot": "IR", "points": 0.0},
            ],
        )

    def test_quiet_weeks_and_byes_produce_no_rows(self):
        manager = SimpleNamespace(team_id=1, team_name="Manager")
        league = SimpleNamespace(
            year=2026,
            current_week=3,
            box_scores=lambda week: [
                SimpleNamespace(
                    home_team=manager,
                    away_team=0,
                    home_score=50,
                    away_score=0,
                    home_lineup=[box_entry(1, "QB", "QB", 50, 20, ["QB"])],
                    away_lineup=[],
                )
            ],
        )
        trades = [
            {
                "id": "t",
                "transaction_week": 2,
                "sides": [
                    {
                        "team_id": 1,
                        "team": "Manager",
                        "received": [{"id": 1, "name": "QB"}],
                        "sent": [{"id": 2, "name": "Old QB"}],
                    },
                    {
                        "team_id": 2,
                        "team": "Other",
                        "received": [{"id": 2, "name": "Old QB"}],
                        "sent": [{"id": 1, "name": "QB"}],
                    },
                ],
            }
        ]
        # Week 1 has no trades; in week 2 the manager is on bye (no opponent) and the partner has no box score.
        self.assertEqual(weekly_roster_moves(league, trades, {})["rows"], [])


if __name__ == "__main__":
    unittest.main()
