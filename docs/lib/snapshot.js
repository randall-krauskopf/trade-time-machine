// data.json: version check and the flattened trade list used by trade pages. Pure.
//
// The shape is defined by schema/data.schema.json; bump SCHEMA_VERSION together
// with SCHEMA_VERSION in trade_time_machine/cli.py.

import {leagueDateKey} from "./format.js";
import {archiveTradeId} from "./trades.js";

export const SCHEMA_VERSION = 1;

/** Fail fast when data.json was written by an incompatible generator version. */
export function assertSupportedSnapshot(data) {
  if (data?.schema_version !== SCHEMA_VERSION) {
    throw new Error(`data.json schema version ${data?.schema_version} is not supported (expected ${SCHEMA_VERSION}).`);
  }
  if (!Array.isArray(data.leagues)) throw new Error("data.json has no leagues.");
  return data;
}

/**
 * Validate data.json and flatten every league's trades into one newest-first list.
 * Trade IDs are prefixed with the league key ("premier-<id>") because the raw IDs
 * are only unique within a league; weekly rows keep the raw IDs.
 */
export function normalizeSnapshot(data) {
  assertSupportedSnapshot(data);
  const leagues = data.leagues;
  for (const league of leagues) {
    if (!Array.isArray(league.trades)) throw new Error(`data.json is missing trades for ${league.label || "a league"}.`);
    league.trades = league.trades.filter((trade) => leagueDateKey(trade.traded_at) >= data.first_trade_date);
  }
  const trades = leagues
    .flatMap((league) => league.trades.map((trade) => ({
      ...trade,
      id: archiveTradeId(league, trade.id),
      league,
      league_key: league.key,
      league_label: league.label,
    })))
    .sort((a, b) => Date.parse(b.traded_at) - Date.parse(a.traded_at));
  return {...data, leagues, trades};
}

/** Context-bar parts for trade pages: cutoff date plus per-league trade and week counts. */
export function tradeContext(snapshot) {
  return [
    `trades from ${snapshot.first_trade_date}`,
    ...snapshot.leagues.map((league) => `${league.label} ${league.trades.length} trades · ${league.completed_weeks.length} completed weeks`),
  ];
}
