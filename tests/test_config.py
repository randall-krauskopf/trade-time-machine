from datetime import date, datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import generate
from tests.fixtures.builders import FakeLeague, player
from trade_time_machine.config import load_config, load_credentials


class ConfigurationTests(unittest.TestCase):
    def test_repository_config_is_valid(self):
        config = load_config(Path(__file__).resolve().parent.parent / "generator.json")
        self.assertEqual(config.season_year, 2026)
        self.assertEqual(config.first_trade_date, date(2026, 8, 30))
        self.assertEqual([league.key for league in config.leagues], ["premier", "champeens"])
        self.assertIn("trade-talk", config.discord.channels.values())

    def test_invalid_config_fails_with_context(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "generator.json"
            for payload, message in (
                ({"season_year": "2026", "first_trade_date": "2026-08-30", "leagues": [{}]}, "season_year"),
                ({"season_year": 2026, "first_trade_date": "2025-08-30", "leagues": [{}]}, "first_trade_date"),
                (
                    {
                        "season_year": 2026,
                        "first_trade_date": "2026-08-30",
                        "leagues": [
                            {"key": "same", "label": "A", "league_id": 1, "receipts": False},
                            {"key": "same", "label": "B", "league_id": 2, "receipts": False},
                        ],
                    },
                    "Duplicate league key",
                ),
            ):
                with self.subTest(message=message):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        load_config(path)

    def test_every_league_and_discord_field_is_validated(self):
        base = {"season_year": 2026, "first_trade_date": "2026-08-30"}
        league = {"key": "premier", "label": "Premier", "league_id": 1, "receipts": False}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "generator.json"
            for payload, message in (
                ([], "JSON object"),
                ({**base, "first_trade_date": "August 30"}, "ISO date"),
                ({**base, "leagues": []}, "nonempty array"),
                ({**base, "leagues": [{**league, "key": " "}]}, "nonempty key"),
                ({**base, "leagues": [{**league, "label": ""}]}, "nonempty label"),
                ({**base, "leagues": [{**league, "league_id": "1"}]}, "positive numeric league_id"),
                ({**base, "leagues": [{**league, "receipts": "yes"}]}, "boolean receipts"),
                ({**base, "leagues": [league], "discord": []}, "guild_id and channels"),
                ({**base, "leagues": [league], "discord": {"guild_id": 1, "channels": {"2": "a"}}}, "numeric string"),
                ({**base, "leagues": [league], "discord": {"guild_id": "1", "channels": {}}}, "map channel IDs"),
                ({**base, "leagues": [league], "discord": {"guild_id": "1", "channels": {"x": "a"}}}, "numeric string"),
                ({**base, "leagues": [league], "discord": {"guild_id": "1", "channels": {"2": " "}}}, "nonempty name"),
            ):
                with self.subTest(message=message):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        load_config(path)

    def test_discord_section_is_optional_and_parsed_to_integers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "generator.json"
            payload = {
                "season_year": 2026,
                "first_trade_date": "2026-08-30",
                "leagues": [{"key": "premier", "label": "Premier", "league_id": 1, "receipts": False}],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(load_config(path).discord)
            payload["discord"] = {"guild_id": "10", "channels": {"20": "trade-talk"}}
            path.write_text(json.dumps(payload), encoding="utf-8")
            discord = load_config(path).discord
            self.assertEqual((discord.guild_id, discord.channels), (10, {20: "trade-talk"}))

    def test_credentials_are_local_and_environment_takes_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("# Private values\nESPN_S2='file-token'\nSWID={file-id}\n", encoding="utf-8")
            with patch.dict("os.environ", {"ESPN_S2": "env-token"}, clear=True):
                self.assertEqual(load_credentials(path), {"ESPN_S2": "env-token", "SWID": "{file-id}"})
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(load_credentials(path), {"ESPN_S2": "file-token", "SWID": "{file-id}"})
                self.assertEqual(load_credentials(Path(folder) / "missing"), {})
                path.write_text("ESPN_S2=token\nSWID=\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "both ESPN_S2 and SWID"):
                    load_credentials(path)

    def test_main_uses_repo_local_config_and_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config_path = root / "generator.json"
            config_path.write_text(
                json.dumps(
                    {
                        "season_year": 2026,
                        "first_trade_date": "2026-09-10",
                        "leagues": [{"key": "test", "label": "Test league", "league_id": 42, "receipts": False}],
                    }
                ),
                encoding="utf-8",
            )
            credentials_path = root / ".env"
            credentials_path.write_text("ESPN_S2=local-token\nSWID={local-id}\n", encoding="utf-8")
            output_path = root / "data.json"
            players = {1: player(1, "A", {1: 1}), 2: player(2, "B", {1: 2})}
            league = FakeLeague(datetime(2026, 9, 9, tzinfo=ZoneInfo("America/Chicago")), players)
            league.trades.append(FakeLeague(datetime(2026, 9, 10, tzinfo=ZoneInfo("America/Chicago")), players).trade)
            with (
                patch.dict("os.environ", {}, clear=True),
                patch("trade_time_machine.cli.League", return_value=league) as espn,
                patch(
                    "sys.argv",
                    [
                        "generate.py",
                        "--config",
                        str(config_path),
                        "--env-file",
                        str(credentials_path),
                        "--output",
                        str(output_path),
                    ],
                ),
            ):
                generate.main()
            espn.assert_called_once_with(league_id=42, year=2026, espn_s2="local-token", swid="{local-id}")
            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(data["first_trade_date"], "2026-09-10")
            self.assertEqual(data["leagues"][0]["key"], "test")
            self.assertEqual(len(data["leagues"][0]["trades"]), 1)
            self.assertNotIn("local-token", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
