import unittest

from tests.fixtures.builders import lineup_player
from trade_time_machine.lineups import optimal_lineup_points, refill_lineup


class RefillLineupTest(unittest.TestCase):
    def test_fills_dedicated_slot_before_flex_by_projection(self):
        starters = [
            lineup_player(1, "RB", 20, 15, ["RB", "RB/WR/TE"]),
            lineup_player(2, "RB/WR/TE", 10, 12, ["WR", "RB/WR/TE"]),
            lineup_player(3, "WR", 5, 8, ["WR", "RB/WR/TE"]),
        ]
        bench = [
            lineup_player(4, "BE", 30, 5, ["RB", "RB/WR/TE"]),
            lineup_player(5, "BE", 2, 9, ["RB", "RB/WR/TE"]),
        ]
        outcome = refill_lineup(starters, bench, {1, 2}, [])
        # RB slot goes to the higher projection (P5), not the hindsight pick (P4); flex gets P4.
        self.assertEqual([(c["slot"], c["name"]) for c in outcome["replacements"]], [("RB", "P5"), ("RB/WR/TE", "P4")])
        self.assertEqual(outcome["score"], 37)

    def test_sent_player_can_bump_lower_projected_starter(self):
        starters = [lineup_player(1, "WR", 4, 6, ["WR", "RB/WR/TE"])]
        sent = [{"id": 9, "name": "Star", "points": 25, "projected": 18, "eligible": ["WR", "RB/WR/TE"]}]
        outcome = refill_lineup(starters, [], set(), sent)
        self.assertEqual(outcome["score"], 25)
        self.assertEqual(outcome["replacements"][0]["replaced"], "P1")

    def test_slot_without_eligible_replacement_scores_zero(self):
        starters = [lineup_player(1, "TE", 12, 9, ["TE"]), lineup_player(2, "QB", 20, 18, ["QB"])]
        bench = [lineup_player(3, "BE", 8, 7, ["WR"])]
        outcome = refill_lineup(starters, bench, {1}, [])
        self.assertEqual(outcome["score"], 20)
        self.assertEqual(outcome["replacements"], [{"slot": "TE", "name": None, "points": 0.0, "replaced": None}])

    def test_traded_away_player_already_on_roster_is_not_counted_twice(self):
        starters = [lineup_player(1, "WR", 10, 12, ["WR"]), lineup_player(2, "WR", 20, 18, ["WR"])]
        sent = [{"id": 2, "name": "P2", "points": 20, "projected": 18, "eligible": ["WR"]}]
        outcome = refill_lineup(starters, [], {1}, sent)
        self.assertEqual(outcome["score"], 20)
        self.assertIsNone(outcome["replacements"][0]["name"])


class OptimalLineupTest(unittest.TestCase):
    def test_optimal_lineup_respects_dedicated_and_flex_slots(self):
        players = [
            lineup_player(1, "BE", 20, 0, ["RB", "RB/WR/TE"]),
            lineup_player(2, "BE", 30, 0, ["RB/WR/TE"]),
            lineup_player(3, "BE", 25, 0, ["WR", "RB/WR/TE"]),
            lineup_player(4, "BE", 40, 0, ["WR"]),
        ]
        self.assertEqual(optimal_lineup_points(players, ["RB", "WR", "RB/WR/TE"]), 90)
        self.assertEqual(optimal_lineup_points(players[:1], ["RB", "WR"]), 20)
        self.assertEqual(optimal_lineup_points([lineup_player(5, "BE", -3, 0, ["D/ST"])], ["D/ST"]), -3)


if __name__ == "__main__":
    unittest.main()
