import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {leagueTeams, netWeeklySwing, tradePartners, tradesPerWeek} from "../../docs/lib/charts.js";
import {normalizeSnapshot} from "../../docs/lib/snapshot.js";

const snapshotPath = new URL("../../docs/data.json", import.meta.url);

function side(team_id, team, total_points) {
  return {team_id, team, sent: [], received: [], weekly_points: {}, total_points};
}

function trade(id, transaction_week, sides, weeks = [transaction_week]) {
  return {id, transaction_week, weeks, trade_week: weeks[0] ?? null, sides};
}

test("trades per week fills quiet weeks with zero and marks the week in progress", () => {
  const trades = [
    trade("a", 1, [side(1, "Alpha", 10), side(2, "Bravo", 5)]),
    trade("b", 3, [side(1, "Alpha", 1), side(3, "Charlie", 2)]),
    trade("c", 4, [side(2, "Bravo", null), side(3, "Charlie", null)], []),
    trade("d", 4, [side(1, "Alpha", null), side(2, "Bravo", null)], []),
  ];
  assert.deepEqual(tradesPerWeek(trades, {completed_weeks: [1, 2, 3]}), [
    {week: 1, count: 1, complete: true},
    {week: 2, count: 0, complete: true},
    {week: 3, count: 1, complete: true},
    {week: 4, count: 2, complete: false},
  ]);
  assert.deepEqual(tradesPerWeek([], {completed_weeks: [1, 2]}).map((week) => week.count), [0, 0]);
  assert.throws(() => tradesPerWeek([trade("x", 0, [])], {}), /Invalid transaction week/);
});

test("trade partner matrix is symmetric, includes quiet managers, and reports tied top pairs", () => {
  const league = {teams: [{team_id: 4, team: "Delta"}, {team_id: 1, team: "Alpha"}]};
  const trades = [
    trade("a", 1, [side(1, "Alpha", 1), side(2, "Bravo", 1)]),
    trade("b", 2, [side(2, "Bravo", 1), side(1, "Alpha", 1)]),
    trade("c", 2, [side(3, "Charlie", 1), side(2, "Bravo", 1)]),
    trade("d", 3, [side(3, "Charlie", 1), side(2, "Bravo", 1)]),
  ];
  const {teams, counts, max, topPairs} = tradePartners(trades, league);
  assert.deepEqual(teams.map((team) => team.team), ["Alpha", "Bravo", "Charlie", "Delta"]);
  assert.deepEqual(counts, [
    [0, 2, 0, 0],
    [2, 0, 2, 0],
    [0, 2, 0, 0],
    [0, 0, 0, 0],
  ]);
  assert.equal(max, 2);
  assert.deepEqual(topPairs.map((pair) => pair.teams.map((team) => team.team)), [["Alpha", "Bravo"], ["Bravo", "Charlie"]]);
  assert.deepEqual(tradePartners([], {}).topPairs, []);
});

test("league teams fall back to alternate standings", () => {
  const league = {alternate_standings: {teams: [{team_id: 2, team: "Bravo", wins: 1}]}};
  assert.deepEqual(leagueTeams([], league), [{team_id: 2, team: "Bravo"}]);
});

test("net weekly swing sums verified manager-weeks only", () => {
  const league = {weekly_roster_moves: {
    rows: [
      {team_id: 1, team: "Alpha", week: 1, net_points: 4.5},
      {team_id: 1, team: "Alpha", week: 2, net_points: -1.25},
      {team_id: 2, team: "Bravo", week: 1, net_points: -6},
    ],
    omitted: [{team_id: 3, week: 1}],
  }};
  assert.deepEqual(netWeeklySwing(league), [
    {team_id: 1, team: "Alpha", net: 3.25, weeks: 2},
    {team_id: 2, team: "Bravo", net: -6, weeks: 1},
  ]);
  assert.deepEqual(netWeeklySwing({}), []);
  assert.throws(() => netWeeklySwing({weekly_roster_moves: {rows: [{team_id: 1, team: "A", week: 1, net_points: null}]}}), /Invalid weekly point swing/);
});

test("every chart builds from the published snapshot", () => {
  const snapshot = normalizeSnapshot(JSON.parse(fs.readFileSync(snapshotPath, "utf8")));
  for (const league of snapshot.leagues) {
    const trades = snapshot.trades.filter((item) => item.league_key === league.key);
    assert.equal(tradesPerWeek(trades, league).reduce((total, week) => total + week.count, 0), trades.length);
    const {counts} = tradePartners(trades, league);
    assert.equal(counts.flat().reduce((total, count) => total + count, 0), trades.length * 2);
    assert.ok(Array.isArray(netWeeklySwing(league)));
  }
});
