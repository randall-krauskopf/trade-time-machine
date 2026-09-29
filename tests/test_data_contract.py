"""The published snapshot and the golden fixture must match schema/data.schema.json."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "data.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def errors_in(data: dict) -> list[str]:
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in VALIDATOR.iter_errors(data)
    ]


class DataContractTest(unittest.TestCase):
    def test_schema_is_valid(self):
        Draft202012Validator.check_schema(SCHEMA)

    def test_published_snapshot_matches_schema(self):
        data = json.loads((ROOT / "docs" / "data.json").read_text(encoding="utf-8"))
        self.assertEqual(errors_in(data), [])

    def test_golden_fixture_matches_schema(self):
        data = json.loads((ROOT / "tests" / "fixtures" / "data.expected.json").read_text(encoding="utf-8"))
        # The golden file masks timestamps; restore a valid one for format checks.
        data["generated_at"] = "2026-09-29T00:00:00+00:00"
        for league in data["leagues"]:
            league["generated_at"] = data["generated_at"]
        self.assertEqual(errors_in(data), [])

    def test_schema_rejects_unknown_results(self):
        data = json.loads((ROOT / "docs" / "data.json").read_text(encoding="utf-8"))
        rows = next(
            league["weekly_roster_moves"]["rows"] for league in data["leagues"] if league["weekly_roster_moves"]
        )
        rows[0]["result"] = "X"
        self.assertTrue(any("result" in error for error in errors_in(data)))

    def test_trade_ids_in_weekly_rows_exist_in_same_league(self):
        data = json.loads((ROOT / "docs" / "data.json").read_text(encoding="utf-8"))
        for league in data["leagues"]:
            trade_ids = {trade["id"] for trade in league["trades"]}
            for row in (league["weekly_roster_moves"] or {"rows": []})["rows"]:
                with self.subTest(league=league["key"], week=row["week"], team=row["team"]):
                    self.assertLessEqual(set(row["trade_ids"]), trade_ids)


if __name__ == "__main__":
    unittest.main()
