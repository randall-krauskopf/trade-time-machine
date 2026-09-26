import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from generate import GUILD_ID, add_matchup_impact, build_snapshot, parse_discord_export, reconstruct_trades, refill_lineup, week_start


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

    def test_tuesday_trade_does_not_include_previous_week(self):
        self.assertEqual(week_start(2026, 2).astimezone(ZoneInfo("America/Chicago")).date().isoformat(), "2026-09-15")
        league = FakeLeague(datetime(2026, 9, 15, 18, tzinfo=ZoneInfo("America/Chicago")), self.players)
        trade = build_snapshot(league, [])["trades"][0]
        self.assertEqual(trade["weeks"], [2])
        self.assertEqual(trade["trade_week"], 2)

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
        league.box_scores = lambda week: [SimpleNamespace(
            home_team=left, away_team=right, home_score=100, away_score=90,
            home_lineup=[box_entry(2 if week == 1 else 1, "Received first" if week == 1 else "Received later", "WR", 20, 10, ["WR"])],
            away_lineup=[box_entry(1 if week == 1 else 2, "Sent first" if week == 1 else "Sent later", "WR", 10, 10, ["WR"])],
        )]
        trades = build_snapshot(league, [])["trades"]
        earlier = next(trade for trade in trades if trade["traded_at"] == first.astimezone(timezone.utc).isoformat())
        self.assertEqual(earlier["sides"][0]["received"][0]["weeks"]["2"], 13.6)
        self.assertEqual(earlier["sides"][0]["total_points"], 13.6)
        self.assertEqual(list(earlier["sides"][0]["impact"]["weeks"]), ["1"])
        self.assertEqual(earlier["impact_cutoff"]["last_week"], 1)

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

def lineup_player(player_id, slot, points, projected, eligible):
    return {"id": player_id, "name": f"P{player_id}", "slot": slot, "points": points, "projected": projected, "eligible": eligible}


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


def box_entry(player_id, name, slot, points, projected, eligible):
    return SimpleNamespace(playerId=player_id, name=name, slot_position=slot, points=points, projected_points=projected, eligibleSlots=eligible)


class MatchupImpactTest(unittest.TestCase):
    def retrade_fixture(self, retraded_in_original_lineup, retraded_in_new_lineup):
        original_team = SimpleNamespace(team_id=2, team_name="Original recipient")
        partner = SimpleNamespace(team_id=10, team_name="First partner")
        new_team = SimpleNamespace(team_id=3, team_name="New recipient")
        opponent = SimpleNamespace(team_id=4, team_name="Other opponent")
        first = (week_start(2026, 1) - timedelta(days=1)).isoformat()
        later = (week_start(2026, 2) + timedelta(days=2)).isoformat()
        trades = [
            {
                "traded_at": first, "trade_week": None, "weeks": [1, 2, 3],
                "sides": [
                    {"team_id": 2, "team": original_team.team_name, "received": [{"id": 100, "name": "Player A"}], "sent": [{"id": 200, "name": "Player B"}]},
                    {"team_id": 10, "team": partner.team_name, "received": [{"id": 200, "name": "Player B"}], "sent": [{"id": 100, "name": "Player A"}]},
                ],
            },
            {
                "traded_at": later, "trade_week": 2, "weeks": [2, 3],
                "sides": [
                    {"team_id": 2, "team": original_team.team_name, "received": [{"id": 300, "name": "Player C"}], "sent": [{"id": 100, "name": "Player A"}]},
                    {"team_id": 3, "team": new_team.team_name, "received": [{"id": 100, "name": "Player A"}], "sent": [{"id": 300, "name": "Player C"}]},
                ],
            },
        ]

        def weekly_boxes(week):
            old_lineup = [
                box_entry(100 if week == 1 or retraded_in_original_lineup and week == 2 else 400, "Player A" if week == 1 or retraded_in_original_lineup and week == 2 else "Other WR", "WR", 25, 12, ["WR"]),
                box_entry(500, "QB", "QB", 75, 15, ["QB"]),
            ]
            new_lineup = [
                box_entry(100 if week == 3 or retraded_in_new_lineup and week == 2 else 600, "Player A" if week == 3 or retraded_in_new_lineup and week == 2 else "New WR", "WR", 10, 10, ["WR"]),
            ]
            return [
                SimpleNamespace(home_team=original_team, away_team=partner, home_score=100, away_score=90,
                                home_lineup=old_lineup, away_lineup=[box_entry(200, "Player B", "RB", 90, 10, ["RB"])]),
                SimpleNamespace(home_team=new_team, away_team=opponent, home_score=10, away_score=20,
                                home_lineup=new_lineup, away_lineup=[box_entry(700, "Other QB", "QB", 20, 10, ["QB"])]),
            ]

        return SimpleNamespace(year=2026, box_scores=weekly_boxes), trades

    def test_later_retrade_stops_both_original_sides_after_last_valid_week(self):
        league, trades = self.retrade_fixture(False, True)
        add_matchup_impact(league, trades, {})
        original = trades[0]
        self.assertEqual(original["impact_cutoff"]["player"], "Player A")
        self.assertEqual(original["impact_cutoff"]["last_week"], 1)
        self.assertEqual(original["impact_cutoff"]["team"], "Original recipient")
        for side in original["sides"]:
            self.assertEqual(list(side["impact"]["weeks"]), ["1"])
        self.assertEqual(original["sides"][0]["impact"]["net_points"], 25)
        self.assertIsNone(trades[1]["impact_cutoff"])

    def test_midweek_retrade_keeps_week_only_when_original_lineup_has_player(self):
        league, trades = self.retrade_fixture(True, False)
        add_matchup_impact(league, trades, {})
        self.assertEqual(trades[0]["impact_cutoff"]["last_week"], 2)
        self.assertEqual(list(trades[0]["sides"][0]["impact"]["weeks"]), ["1", "2"])

    def test_ambiguous_midweek_lineup_stops_at_prior_week(self):
        league, trades = self.retrade_fixture(True, True)
        add_matchup_impact(league, trades, {})
        self.assertEqual(trades[0]["impact_cutoff"]["last_week"], 1)
        self.assertEqual(list(trades[0]["sides"][0]["impact"]["weeks"]), ["1"])

    def test_other_trades_and_lineup_changes_do_not_end_tracking(self):
        league, trades = self.retrade_fixture(True, False)
        trades[1]["sides"][0]["sent"][0] = {"id": 400, "name": "Other WR"}
        trades[1]["sides"][1]["received"][0] = {"id": 400, "name": "Other WR"}
        add_matchup_impact(league, trades, {})
        self.assertIsNone(trades[0]["impact_cutoff"])
        self.assertEqual(list(trades[0]["sides"][0]["impact"]["weeks"]), ["1", "2", "3"])

    def test_retrade_before_first_scoring_week_has_no_impact_weeks(self):
        league, trades = self.retrade_fixture(False, True)
        trades[1]["traded_at"] = (week_start(2026, 1) - timedelta(hours=1)).isoformat()
        add_matchup_impact(league, trades, {})
        self.assertIsNone(trades[0]["impact_cutoff"]["last_week"])
        self.assertEqual(trades[0]["sides"][0]["impact"]["weeks"], {})
        self.assertIsNone(trades[0]["sides"][0]["impact"]["wins_added"])

    def test_partner_opponent_is_rescored_and_flip_counted(self):
        left = SimpleNamespace(team_id=2, team_name="All Gold")
        right = SimpleNamespace(team_id=10, team_name="Boom Baum")
        # Week 2: All Gold started the WR they received (id 100); Boom Baum started the RB it received (id 200).
        box = SimpleNamespace(
            home_team=left, away_team=right, home_score=100.0, away_score=95.0,
            home_lineup=[
                box_entry(100, "Got WR", "WR", 30, 14, ["WR", "RB/WR/TE"]),
                box_entry(101, "AG Bench WR", "BE", 5, 10, ["WR", "RB/WR/TE"]),
                box_entry(102, "AG QB", "QB", 70, 20, ["QB"]),
            ],
            away_lineup=[
                box_entry(200, "Got RB", "RB", 10, 12, ["RB", "RB/WR/TE"]),
                box_entry(201, "BB Bench RB", "BE", 1, 8, ["RB", "RB/WR/TE"]),
                box_entry(202, "BB QB", "QB", 85, 20, ["QB"]),
            ],
        )
        league = SimpleNamespace(box_scores=lambda week: [box])
        trade = {
            "traded_at": (week_start(2026, 1) - timedelta(days=1)).isoformat(),
            "trade_week": 1,
            "weeks": [2],
            "sides": [
                {"team_id": 2, "received": [{"id": 100, "name": "Got WR"}], "sent": [{"id": 200, "name": "Got RB"}]},
                {"team_id": 10, "received": [{"id": 200, "name": "Got RB"}], "sent": [{"id": 100, "name": "Got WR"}]},
            ],
        }
        add_matchup_impact(league, [trade], {})
        gold, boom = (side["impact"] for side in trade["sides"])
        week = gold["weeks"]["2"]
        # All Gold without the trade: QB 70 + bench WR 5 (RB Got RB can't fill WR) = 75.
        self.assertEqual(week["alt_score"], 75)
        # Boom Baum without the trade: Got WR has no WR slot to fill, so bench RB 1 + QB 85 = 86.
        self.assertEqual(week["opponent_alt_score"], 86)
        self.assertTrue(week["opponent_is_partner"])
        self.assertEqual((week["result"], week["alt_result"]), ("W", "L"))
        self.assertEqual(gold["wins_added"], 1.0)
        self.assertEqual(boom["wins_added"], -1.0)
        self.assertEqual(gold["flips"], 1)
        self.assertEqual(week["started_points"], 30)

    def test_trade_week_skipped_when_lineups_predate_trade(self):
        left = SimpleNamespace(team_id=2, team_name="All Gold")
        right = SimpleNamespace(team_id=10, team_name="Boom Baum")
        box = SimpleNamespace(
            home_team=left, away_team=right, home_score=50.0, away_score=40.0,
            home_lineup=[box_entry(200, "Still Here", "RB", 50, 10, ["RB"])],
            away_lineup=[box_entry(100, "Still There", "WR", 40, 10, ["WR"])],
        )
        league = SimpleNamespace(box_scores=lambda week: [box])
        trade = {
            "traded_at": (week_start(2026, 2) + timedelta(hours=1)).isoformat(),
            "trade_week": 2,
            "weeks": [2],
            "sides": [
                {"team_id": 2, "received": [{"id": 100, "name": "Still There"}], "sent": [{"id": 200, "name": "Still Here"}]},
                {"team_id": 10, "received": [{"id": 200, "name": "Still Here"}], "sent": [{"id": 100, "name": "Still There"}]},
            ],
        }
        add_matchup_impact(league, [trade], {})
        self.assertEqual(trade["sides"][0]["impact"]["weeks"], {})
        self.assertIsNone(trade["sides"][0]["impact"]["wins_added"])


if __name__ == "__main__":
    unittest.main()
