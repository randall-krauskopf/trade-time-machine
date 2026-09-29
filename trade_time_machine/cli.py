"""Command line entry point: fetch every configured league and write data.json."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

from espn_api.football import League

from .config import load_config, load_credentials
from .receipts import parse_discord_export
from .snapshot import build_snapshot

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
"""Bump when data.json changes shape; keep schema/data.schema.json in sync."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a read-only snapshot of Lana Straw league trades.")
    parser.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "generator.json",
        help="League IDs, season year, and inclusive Central-time cutoff (default: generator.json).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=REPO_ROOT / ".env",
        help="Local ESPN_S2 and SWID credentials (default: .env); environment variables take precedence.",
    )
    parser.add_argument("--discord-export", type=Path, help="Optional local JSON export of discord_messages.")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "docs" / "data.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = load_config(args.config)
    credentials = load_credentials(args.env_file)
    messages = parse_discord_export(args.discord_export, config.discord)
    espn_auth = {key.lower(): value for key, value in credentials.items()}
    leagues = []
    for spec in config.leagues:
        league = League(league_id=spec.league_id, year=config.season_year, **espn_auth)
        snapshot = build_snapshot(league, messages if spec.receipts else [], config.first_trade_date)
        snapshot.update(key=spec.key, label=spec.label, receipts_enabled=spec.receipts)
        leagues.append(snapshot)
        print(f"{spec.label}: {len(snapshot['trades'])} trades")
    output = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "first_trade_date": config.first_trade_date.isoformat(),
        "discord_imported": bool(messages),
        "leagues": leagues,
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {sum(len(league['trades']) for league in leagues)} trades to {args.output}")
