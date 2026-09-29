from datetime import timedelta
import unittest
from zoneinfo import ZoneInfo

from trade_time_machine.game_weeks import transaction_week, week_start


class GameWeekTests(unittest.TestCase):
    def test_transaction_weeks_turn_over_tuesday_morning(self):
        tuesday = week_start(2026, 2)
        self.assertEqual(transaction_week(2026, tuesday - timedelta(seconds=1)), 1)
        self.assertEqual(transaction_week(2026, tuesday), 2)
        self.assertEqual(transaction_week(2026, week_start(2026, 3)), 3)

    def test_week_one_starts_thursday_after_labor_day(self):
        chicago = ZoneInfo("America/Chicago")
        self.assertEqual(week_start(2026, 1).astimezone(chicago).date().isoformat(), "2026-09-10")
        self.assertEqual(week_start(2026, 2).astimezone(chicago).date().isoformat(), "2026-09-15")
        # Labor Day on September 1 (2025) still yields a Thursday kickoff that week.
        self.assertEqual(week_start(2025, 1).astimezone(chicago).date().isoformat(), "2025-09-04")

    def test_preseason_transactions_count_as_week_one(self):
        self.assertEqual(transaction_week(2026, week_start(2026, 1) - timedelta(days=10)), 1)


if __name__ == "__main__":
    unittest.main()
