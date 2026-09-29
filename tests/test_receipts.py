from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from tests.fixtures.builders import FakeLeague, player
from trade_time_machine.config import DiscordConfig
from trade_time_machine.game_weeks import week_start
from trade_time_machine.receipts import parse_discord_export, trade_receipts
from trade_time_machine.snapshot import build_snapshot

DISCORD = DiscordConfig(1160416084235661426, {1160416085326188557: "trade-talk"})


class DiscordReceiptTests(unittest.TestCase):
    def setUp(self):
        self.players = {
            1: player(1, "Cam Skattebo", {1: 14.1, 2: 4.9}),
            2: player(2, "TreVeyon Henderson", {1: 0.0, 2: 13.6}),
        }

    def test_discord_filter_and_proximity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "messages.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "guild_id": str(DISCORD.guild_id),
                            "channel_id": "1160416085326188557",
                            "message_id": "12345",
                            "sent_at": "2026-09-09T09:00:00Z",
                            "author_name": "coach",
                            "content": "TreVeyon Henderson is a steal",
                        },
                        {
                            "guild_id": str(DISCORD.guild_id),
                            "channel_id": "1278864199740686466",
                            "message_id": "12346",
                            "sent_at": "2026-09-09T09:00:00Z",
                            "author_name": "coach",
                            "content": "TreVeyon Henderson is a steal",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            messages = parse_discord_export(path, DISCORD)
            self.assertEqual(len(messages), 1)
            league = FakeLeague(week_start(2026, 1).replace(day=9), self.players)
            receipt = build_snapshot(league, messages, date(2026, 8, 30))["trades"][0]["receipts"][0]
            self.assertEqual(receipt["channel"], "trade-talk")
            self.assertTrue(receipt["url"].endswith("/12345"))

    def test_bad_export_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "messages.json"
            path.write_text('{"messages": {}}', encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_discord_export(path, DISCORD)

    def test_export_requires_discord_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "messages.json"
            path.write_text("[]", encoding="utf-8")
            self.assertEqual(parse_discord_export(None, None), [])
            with self.assertRaisesRegex(ValueError, "discord section"):
                parse_discord_export(path, None)

    def test_skips_noise_and_rejects_malformed_messages(self):
        good = {
            "guild_id": str(DISCORD.guild_id),
            "channel_id": "1160416085326188557",
            "message_id": "1",
            "sent_at": "2026-09-09T09:00:00",
            "author_name": None,
            "content": "  hi  ",
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "messages.json"
            path.write_text(
                json.dumps(
                    {
                        "messages": [
                            good,
                            {**good, "guild_id": "999"},
                            {**good, "author_bot": True},
                            {**good, "deleted_at": "2026-09-09T10:00:00Z"},
                            {**good, "content": "   "},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (message,) = parse_discord_export(path, DISCORD)
            self.assertEqual((message["author"], message["content"]), ("Unknown", "hi"))
            self.assertEqual(message["sent_at"].utcoffset().total_seconds(), 0)
            for bad, error in (
                ("not a message", "must be an object"),
                ({**good, "channel_id": "general"}, "numeric guild_id"),
                ({**good, "sent_at": "yesterday"}, "ISO-8601"),
                ({**good, "message_id": "abc"}, "numeric message_id"),
            ):
                with self.subTest(error=error):
                    path.write_text(json.dumps([bad]), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, error):
                        parse_discord_export(path, DISCORD)

    def test_receipts_match_whole_names_and_keep_the_closest_four(self):
        traded_at = datetime(2026, 9, 9, 12, tzinfo=UTC)
        messages = [
            {
                "channel": "trade-talk",
                "url": f"u{hours}",
                "author": "a",
                "content": text,
                "sent_at": traded_at + timedelta(hours=hours),
            }
            for hours, text in (
                (5, "Cam is back"),
                (-1, "cam!"),
                (2, "CAM"),
                (3, "Cam."),
                (1, "cam"),
                (0, "Cameron"),
                (49, "Cam late"),
            )
        ]
        receipts = trade_receipts(messages, traded_at, ["Cam"])
        self.assertEqual([receipt["url"] for receipt in receipts], ["u-1", "u1", "u2", "u3"])


if __name__ == "__main__":
    unittest.main()
