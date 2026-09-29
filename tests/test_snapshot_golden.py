"""Golden snapshot: the whole generator pipeline against deterministic fake leagues.

Any change to data.json output shows up as a diff here. If the change is
intentional, regenerate the expected file with:

    UPDATE_GOLDEN=1 .venv/bin/python -m unittest tests.test_snapshot_golden
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.fixtures.fake_espn import DISCORD_EXPORT, activity_league, reconstructed_league
from trade_time_machine import cli

EXPECTED = Path(__file__).parent / "fixtures" / "data.expected.json"
LEAGUE_CLASS = "trade_time_machine.cli.League"
CONFIG = {
    "season_year": 2026,
    "first_trade_date": "2026-08-30",
    "leagues": [
        {"key": "premier", "label": "Premier", "league_id": 1, "receipts": True},
        {"key": "champeens", "label": "Champeens", "league_id": 2, "receipts": False},
    ],
    "discord": {"guild_id": "1160416084235661426", "channels": {"1160416085326188557": "trade-talk"}},
}


def fake_league(league_id: int, **_: object) -> object:
    return {1: activity_league, 2: reconstructed_league}[league_id]()


def without_timestamps(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: "<generated_at>" if key == "generated_at" else without_timestamps(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [without_timestamps(item) for item in value]
    return value


def generate_fixture_snapshot() -> dict:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / "generator.json").write_text(json.dumps(CONFIG), encoding="utf-8")
        (root / "discord.json").write_text(json.dumps(DISCORD_EXPORT), encoding="utf-8")
        output = root / "data.json"
        argv = [
            "--config",
            str(root / "generator.json"),
            "--env-file",
            str(root / "missing.env"),
            "--discord-export",
            str(root / "discord.json"),
            "--output",
            str(output),
        ]
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(LEAGUE_CLASS, side_effect=fake_league),
            patch("builtins.print"),
        ):
            cli.main(argv)
        return without_timestamps(json.loads(output.read_text(encoding="utf-8")))


class GoldenSnapshotTest(unittest.TestCase):
    maxDiff = None

    def test_fixture_snapshot_matches_expected_output(self):
        actual = generate_fixture_snapshot()
        if os.environ.get("UPDATE_GOLDEN"):
            EXPECTED.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
