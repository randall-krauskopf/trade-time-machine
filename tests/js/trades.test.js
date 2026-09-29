import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {countOf, formatPoints, formatSigned, leagueDateKey} from "../../docs/lib/format.js";
import {SCHEMA_VERSION, assertSupportedSnapshot, normalizeSnapshot, tradeContext} from "../../docs/lib/snapshot.js";
import {archiveHref, filterTrades, leadStory, playersExchanged, teamKey, tradeTeams} from "../../docs/lib/trades.js";

const snapshotPath = new URL("../../docs/data.json", import.meta.url);

function side(teamId, team, weeklyPoints, received = 1) {
  return {team_id: teamId, team, weekly_points: weeklyPoints, received: Array.from({length: received}, (_, index) => ({id: index}))};
}

test("formatting uses em dashes for unknowns and a typographic minus", () => {
  assert.equal(formatPoints(null), "—");
  assert.equal(formatPoints(3), "3.00");
  assert.equal(formatSigned(-1.25, 2), "−1.25");
  assert.equal(formatSigned(2), "+2.0");
  assert.equal(formatSigned(0), "0.0");
  assert.equal(formatSigned(undefined), "—");
  assert.equal(countOf(1, "loss", "losses"), "1 loss");
  assert.equal(countOf(0.5, "loss", "losses"), "0.5 losses");
});

test("league dates are Central time", () => {
  // 03:00 UTC on Aug 30 is still Aug 29 in Chicago.
  assert.equal(leagueDateKey("2026-08-30T03:00:00+00:00"), "2026-08-29");
  assert.equal(leagueDateKey("2026-08-30T05:00:00+00:00"), "2026-08-30");
});

test("snapshot version and shape are checked before rendering", () => {
  assert.throws(() => assertSupportedSnapshot({schema_version: 0, leagues: []}), /schema version 0 is not supported/);
  assert.throws(() => assertSupportedSnapshot({schema_version: SCHEMA_VERSION}), /no leagues/);
  assert.throws(() => normalizeSnapshot({schema_version: SCHEMA_VERSION, leagues: [{label: "Premier"}]}), /missing trades for Premier/);
});

test("normalizing prefixes IDs by league, applies the cutoff, and sorts newest first", () => {
  const trade = (id, tradedAt) => ({id, traded_at: tradedAt, sides: []});
  const snapshot = normalizeSnapshot({
    schema_version: SCHEMA_VERSION,
    first_trade_date: "2026-08-30",
    leagues: [
      {key: "premier", label: "Premier", completed_weeks: [1], trades: [
        trade("early", "2026-08-30T03:00:00+00:00"), trade("a", "2026-09-01T00:00:00+00:00"),
      ]},
      {key: "champeens", label: "Champeens", completed_weeks: [], trades: [trade("a", "2026-09-02T00:00:00+00:00")]},
    ],
  });
  assert.deepEqual(snapshot.trades.map((entry) => entry.id), ["champeens-a", "premier-a"]);
  assert.equal(snapshot.trades[0].league_label, "Champeens");
  assert.deepEqual(tradeContext(snapshot), [
    "trades from 2026-08-30", "Premier 1 trades · 1 completed weeks", "Champeens 1 trades · 0 completed weeks",
  ]);
  assert.equal(archiveHref("premier-a b"), "./archive.html?trade=premier-a%20b");
});

test("filters combine league, transaction week, and manager", () => {
  const trades = [
    {id: 1, league_key: "premier", transaction_week: 1, sides: [side(1, "A", {}), side(2, "B", {})]},
    {id: 2, league_key: "premier", transaction_week: 2, sides: [side(1, "A", {}), side(3, "C", {})]},
    {id: 3, league_key: "champeens", transaction_week: 2, sides: [side(1, "Z", {}), side(2, "Y", {})]},
  ];
  assert.equal(teamKey(trades[2], trades[2].sides[0]), "champeens:1");
  assert.deepEqual(filterTrades(trades).map((trade) => trade.id), [1, 2, 3]);
  assert.deepEqual(filterTrades(trades, {week: "2"}).map((trade) => trade.id), [2, 3]);
  assert.deepEqual(filterTrades(trades, {team: "premier:1"}).map((trade) => trade.id), [1, 2]);
  assert.deepEqual(filterTrades(trades, {league: "champeens", team: "premier:1"}), []);
});

test("lead story tracks cumulative leader changes and unknown weeks", () => {
  const trade = (a, b) => ({weeks: [1, 2, 3], sides: [side(1, "Alpha", a, 2), side(2, "Bravo", b)]});
  const flipped = leadStory(trade({1: 10, 2: 0, 3: 0}, {1: 5, 2: 3, 3: 5}));
  assert.deepEqual(flipped.flips.map(({week, to}) => [week, to.team]), [[3, "Bravo"]]);
  assert.equal(flipped.leader.team, "Bravo");
  assert.equal(leadStory(trade({1: 1, 2: 1, 3: 1}, {1: 1, 2: 1, 3: 1})).leader, null);
  assert.equal(leadStory(trade({1: 1, 2: null, 3: 1}, {1: 1, 2: 1, 3: 1})).incomplete, true);
  assert.equal(tradeTeams(trade({}, {})), "Alpha ↔ Bravo");
  assert.equal(playersExchanged(trade({}, {})), 3);
});

test("the published snapshot normalizes cleanly", () => {
  const snapshot = normalizeSnapshot(JSON.parse(fs.readFileSync(snapshotPath, "utf8")));
  assert.ok(snapshot.trades.length > 0);
  assert.equal(new Set(snapshot.trades.map((trade) => trade.id)).size, snapshot.trades.length);
});
