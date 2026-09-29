"""Generator settings (generator.json) and ESPN credentials (.env / environment).

Everything season-specific lives in generator.json so the code carries no
league IDs, dates, or Discord channel IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
from typing import Any

CREDENTIAL_KEYS = ("ESPN_S2", "SWID")


@dataclass(frozen=True)
class LeagueConfig:
    key: str
    """Stable identifier used in URLs and trade IDs (e.g. "premier")."""
    label: str
    league_id: int
    receipts: bool
    """Whether Discord receipts are attached to this league's trades."""


@dataclass(frozen=True)
class DiscordConfig:
    guild_id: int
    channels: dict[int, str]
    """Channel ID -> display name. Messages from other channels are ignored."""


@dataclass(frozen=True)
class GeneratorConfig:
    season_year: int
    first_trade_date: date
    """Trades before local midnight on this date (league time zone) are excluded."""
    leagues: list[LeagueConfig]
    discord: DiscordConfig | None = None


def load_config(path: Path) -> GeneratorConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Generator config must be a JSON object.")
    year = data.get("season_year")
    if type(year) is not int or not 2000 <= year <= 2100:
        raise ValueError("season_year must be an integer between 2000 and 2100.")
    try:
        first_trade_date = date.fromisoformat(data["first_trade_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("first_trade_date must be an ISO date (YYYY-MM-DD).") from exc
    if first_trade_date.year != year:
        raise ValueError("first_trade_date must fall in season_year.")
    return GeneratorConfig(
        season_year=year,
        first_trade_date=first_trade_date,
        leagues=_parse_leagues(data.get("leagues")),
        discord=_parse_discord(data.get("discord")),
    )


def _parse_leagues(leagues: Any) -> list[LeagueConfig]:
    if not isinstance(leagues, list) or not leagues:
        raise ValueError("leagues must be a nonempty array.")
    parsed: list[LeagueConfig] = []
    for league in leagues:
        if not isinstance(league, dict) or not isinstance(league.get("key"), str) or not league["key"].strip():
            raise ValueError("Each league needs a nonempty key.")
        key = league["key"]
        if any(existing.key == key for existing in parsed):
            raise ValueError(f"Duplicate league key: {key}.")
        if not isinstance(league.get("label"), str) or not league["label"].strip():
            raise ValueError(f"League {key} needs a nonempty label.")
        if type(league.get("league_id")) is not int or league["league_id"] <= 0:
            raise ValueError(f"League {key} needs a positive numeric league_id.")
        if type(league.get("receipts")) is not bool:
            raise ValueError(f"League {key} needs a boolean receipts setting.")
        parsed.append(LeagueConfig(key, league["label"], league["league_id"], league["receipts"]))
    return parsed


def _parse_discord(discord: Any) -> DiscordConfig | None:
    if discord is None:
        return None
    if not isinstance(discord, dict):
        raise ValueError("discord must be an object with guild_id and channels.")
    guild_id = _snowflake(discord.get("guild_id"), "discord.guild_id")
    channels = discord.get("channels")
    if not isinstance(channels, dict) or not channels:
        raise ValueError("discord.channels must map channel IDs to names.")
    parsed = {}
    for channel_id, name in channels.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Discord channel {channel_id} needs a nonempty name.")
        parsed[_snowflake(channel_id, "discord channel ID")] = name
    return DiscordConfig(guild_id, parsed)


def _snowflake(value: Any, field: str) -> int:
    """Discord IDs are kept as strings in JSON because they exceed JavaScript's safe integers."""
    if not isinstance(value, str) or not value.isdigit():
        raise ValueError(f"{field} must be a numeric string.")
    return int(value)


def load_credentials(path: Path) -> dict[str, str]:
    """Read ESPN_S2 and SWID; environment variables win over the .env file."""
    credentials = {key: os.environ[key] for key in CREDENTIAL_KEYS if os.environ.get(key)}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key = key.strip()
            if separator and key in CREDENTIAL_KEYS and key not in credentials:
                value = value.strip().strip("\"'")
                if value:
                    credentials[key] = value
    if len(credentials) == 1:
        raise ValueError("Provide both ESPN_S2 and SWID for a private league, or neither for public leagues.")
    return credentials
