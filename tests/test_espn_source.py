from types import SimpleNamespace
import unittest

from trade_time_machine.espn_source import (
    fetch_activity_feed,
    fetch_reconstructed_trades,
    fetch_transactions,
    reconstruct_trades,
)


class ReconstructTradesTest(unittest.TestCase):
    def setUp(self):
        self.league = SimpleNamespace(
            teams=[SimpleNamespace(team_id=team_id, team_name=f"Team {team_id}") for team_id in (1, 2, 3)],
            player_map={10: "Kept", 11: "Retraded", 12: "Waiver pickup", 20: "Other kept"},
        )

    def received(self, trades):
        return sorted(
            (team.team_id, player.name)
            for trade in trades
            for team, action, player, _ in trade.actions
            if action == "TRADE_RECEIVED"
        )

    def test_uses_acquisitions_and_unambiguous_roster_moves(self):
        accepted_at = 1_000_000
        accepts = [{"id": "a", "teamId": 2, "proposedDate": accepted_at, "scoringPeriodId": 1, "items": []}]
        snapshots = [{10: 1, 11: 2, 12: 1, 20: 2}, {10: 2, 11: 1, 12: 3, 20: 1}]
        trades = reconstruct_trades(
            self.league,
            accepts,
            {(12, 3)},
            snapshots,
            {accepted_at + 500: [(10, 2), (20, 1)]},
        )
        self.assertEqual(self.received(trades), [(1, "Other kept"), (1, "Retraded"), (2, "Kept")])
        self.assertEqual(trades[0].date, accepted_at + 500)

    def test_review_delayed_trade_claims_next_acquisition_time(self):
        accepted_at = 1_000_000
        executed_at = accepted_at + 6 * 60 * 60 * 1000
        accepts = [{"id": "a", "teamId": 1, "proposedDate": accepted_at, "scoringPeriodId": 1, "items": []}]
        trades = reconstruct_trades(
            self.league,
            accepts,
            set(),
            [{10: 1, 20: 2}, {10: 2, 20: 1}],
            {executed_at: [(10, 2), (20, 1)]},
        )
        self.assertEqual(trades[0].date, executed_at)
        self.assertEqual(self.received(trades), [(1, "Other kept"), (2, "Kept")])

    def test_listed_trade_items_are_used_directly(self):
        accepts = [
            {
                "id": "a",
                "teamId": 1,
                "proposedDate": 5,
                "scoringPeriodId": 1,
                "items": [{"type": "TRADE", "playerId": 10, "fromTeamId": 1, "toTeamId": 3}],
            }
        ]
        trades = reconstruct_trades(self.league, accepts, set(), [{}, {}], {})
        self.assertEqual(self.received(trades), [(3, "Kept")])
        self.assertEqual(trades[0].date, 5)

    def test_single_known_party_infers_the_only_roster_partner(self):
        accepts = [{"id": "a", "teamId": 1, "proposedDate": 5, "scoringPeriodId": 1, "items": []}]
        trades = reconstruct_trades(self.league, accepts, set(), [{10: 1, 20: 2}, {10: 2, 20: 1}], {})
        self.assertEqual(self.received(trades), [(1, "Other kept"), (2, "Kept")])

    def test_ambiguous_trades_are_skipped(self):
        # One known party and two possible partners in the roster diff: no safe guess.
        accepts = [{"id": "a", "teamId": 1, "proposedDate": 5, "scoringPeriodId": 1, "items": []}]
        trades = reconstruct_trades(self.league, accepts, set(), [{10: 1, 11: 1}, {10: 2, 11: 3}], {})
        self.assertEqual(trades, [])

    def test_shared_period_disables_roster_diff_fallback(self):
        accepts = [
            {
                "id": "a",
                "teamId": 1,
                "proposedDate": 5,
                "scoringPeriodId": 1,
                "items": [{"type": "TRADE", "playerId": 10, "fromTeamId": 1, "toTeamId": 2}],
            },
            {
                "id": "b",
                "teamId": 2,
                "proposedDate": 9,
                "scoringPeriodId": 1,
                "items": [{"type": "TRADE", "playerId": 20, "fromTeamId": 2, "toTeamId": 1}],
            },
        ]
        trades = reconstruct_trades(self.league, accepts, set(), [{10: 1, 11: 1, 20: 2}, {10: 2, 11: 2, 20: 1}], {})
        self.assertEqual([self.received([trade]) for trade in trades], [[(2, "Kept")], [(1, "Other kept")]])


class EspnFetchTest(unittest.TestCase):
    def test_activity_feed_reads_every_page(self):
        feed = list(range(250))
        league = SimpleNamespace(recent_activity=lambda size, offset: feed[offset : offset + size])
        self.assertEqual(fetch_activity_feed(league), feed)

    def test_transactions_are_deduplicated_across_periods(self):
        seen = []

        def league_get(params):
            seen.append(params["scoringPeriodId"])
            return {"transactions": [{"id": "same"}, {"id": f"p{params['scoringPeriodId']}"}]}

        league = SimpleNamespace(current_week=2, espn_request=SimpleNamespace(league_get=league_get))
        self.assertEqual([t["id"] for t in fetch_transactions(league)], ["same", "p0", "p1", "p2"])
        self.assertEqual(seen, [0, 1, 2])

    def test_reconstruction_ignores_pending_trades_and_waiver_moves(self):
        teams = [SimpleNamespace(team_id=team_id, team_name=f"Team {team_id}") for team_id in (1, 2)]
        views = {
            "mTransactions2": {
                "transactions": [
                    {
                        "id": "t",
                        "type": "TRADE_ACCEPT",
                        "status": "EXECUTED",
                        "teamId": 1,
                        "proposedDate": 100,
                        "scoringPeriodId": 1,
                        "items": [],
                    },
                    {"id": "p", "type": "TRADE_ACCEPT", "status": "PENDING", "teamId": 2, "proposedDate": 100},
                    {
                        "id": "w",
                        "type": "WAIVER",
                        "status": "EXECUTED",
                        "items": [{"type": "ADD", "playerId": 30, "toTeamId": 2}],
                    },
                ]
            },
            "mRoster": {
                "teams": [
                    {
                        "id": 1,
                        "roster": {"entries": [{"playerId": 20, "acquisitionType": "TRADE", "acquisitionDate": 100}]},
                    },
                    {
                        "id": 2,
                        "roster": {
                            "entries": [
                                {"playerId": 10, "acquisitionType": "TRADE", "acquisitionDate": 100},
                                {"playerId": 30, "acquisitionType": "WAIVER", "acquisitionDate": 50},
                            ]
                        },
                    },
                ]
            },
        }
        league = SimpleNamespace(
            current_week=1,
            teams=teams,
            player_map={10: "Ten", 20: "Twenty", 30: "Thirty"},
            draft=[
                SimpleNamespace(playerId=10, team=teams[0]),
                SimpleNamespace(playerId=20, team=teams[1]),
                SimpleNamespace(playerId=30, team=teams[0]),
            ],
            espn_request=SimpleNamespace(league_get=lambda params: views[params["view"]]),
        )
        (trade,) = fetch_reconstructed_trades(league)
        received = sorted(
            (team.team_id, player.name) for team, action, player, _ in trade.actions if action == "TRADE_RECEIVED"
        )
        self.assertEqual(received, [(1, "Twenty"), (2, "Ten")])


if __name__ == "__main__":
    unittest.main()
