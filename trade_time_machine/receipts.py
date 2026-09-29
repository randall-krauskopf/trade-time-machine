"""Discord "receipts": league chat messages that mention a trade's players.

Receipts come only from a local export (never fetched live). Messages are
kept when they are in a configured channel, not from a bot, not deleted,
and within TRADE_WINDOW of the trade.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re

from .config import DiscordConfig
from .models import DiscordMessage, Receipt

TRADE_WINDOW = timedelta(days=2)
MAX_RECEIPTS_PER_TRADE = 4
MAX_CONTENT_LENGTH = 600


def parse_discord_export(path: Path | None, discord: DiscordConfig | None) -> list[DiscordMessage]:
    if path is None:
        return []
    if discord is None:
        raise ValueError("A Discord export needs a discord section (guild_id, channels) in generator.json.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    messages = payload.get("messages") if isinstance(payload, dict) else payload
    if not isinstance(messages, list):
        raise ValueError("Discord export must be a JSON array or an object with a 'messages' array.")
    filtered: list[DiscordMessage] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Every Discord message must be an object.")
        try:
            guild = int(message["guild_id"])
            channel = int(message["channel_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Discord messages need numeric guild_id and channel_id.") from exc
        if (
            guild != discord.guild_id
            or channel not in discord.channels
            or message.get("deleted_at")
            or message.get("author_bot")
        ):
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            sent_at = datetime.fromisoformat(message["sent_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError, AttributeError) as exc:
            raise ValueError("Discord messages need an ISO-8601 sent_at timestamp.") from exc
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=UTC)
        message_id = message.get("message_id")
        if message_id is None or not str(message_id).isdigit():
            raise ValueError("Discord messages need a numeric message_id.")
        filtered.append(
            {
                "channel": discord.channels[channel],
                "url": f"https://discord.com/channels/{discord.guild_id}/{channel}/{message_id}",
                "author": str(message.get("author_name") or "Unknown"),
                "content": content.strip()[:MAX_CONTENT_LENGTH],
                "sent_at": sent_at.astimezone(UTC),
            }
        )
    return filtered


def trade_receipts(messages: list[DiscordMessage], traded_at: datetime, player_names: list[str]) -> list[Receipt]:
    """The closest-in-time messages that mention any traded player by whole-word name."""
    patterns = [re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.IGNORECASE) for name in player_names]
    nearby = [
        message
        for message in messages
        if abs(message["sent_at"] - traded_at) <= TRADE_WINDOW
        and any(pattern.search(message["content"]) for pattern in patterns)
    ]
    nearby.sort(key=lambda message: abs(message["sent_at"] - traded_at))
    return [
        {
            "channel": message["channel"],
            "author": message["author"],
            "content": message["content"],
            "sent_at": message["sent_at"].isoformat(),
            "url": message["url"],
        }
        for message in nearby[:MAX_RECEIPTS_PER_TRADE]
    ]
