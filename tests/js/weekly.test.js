import assert from "node:assert/strict";
import test from "node:test";

import {RESULT_WINS, outcomeClass, winsGained} from "../../docs/lib/results.js";
import {describeReplacements, sortWeeklyRows, weeklyHref, weeklyRows} from "../../docs/lib/weekly-moves.js";

test("badges follow matchup results, including ties, rather than point swing", () => {
  const row = {team: "Manager", week: 1, net_points: -10};
  assert.equal(outcomeClass({...row, result: "W", alternate_result: "L"}), "clutch");
  assert.equal(outcomeClass({...row, result: "T", alternate_result: "L"}), "clutch");
  assert.equal(outcomeClass({...row, result: "L", alternate_result: "W"}), "oof");
  assert.equal(outcomeClass({...row, result: "T", alternate_result: "W"}), "oof");
  assert.equal(outcomeClass({...row, result: "L", alternate_result: "L"}), "");
  assert.throws(() => outcomeClass({...row, result: "?", alternate_result: "W"}), /Invalid weekly result/);
});

test("weekly cards default to newest first and can be reversed", () => {
  const rows = [
    {week: 1, trade_count: 1, team: "Zulu"},
    {week: 3, trade_count: 1, team: "Charlie"},
    {week: 2, trade_count: 1, team: "Beta"},
    {week: 3, trade_count: 2, team: "Alpha"},
    {week: 3, trade_count: 2, team: "Bravo"},
  ];
  assert.deepEqual(Array.from(sortWeeklyRows(rows), ({week, team}) => [week, team]), [
    [3, "Alpha"], [3, "Bravo"], [3, "Charlie"], [2, "Beta"], [1, "Zulu"],
  ]);
  assert.deepEqual(Array.from(sortWeeklyRows(rows, "asc"), ({week, team}) => [week, team]), [
    [1, "Zulu"], [2, "Beta"], [3, "Alpha"], [3, "Bravo"], [3, "Charlie"],
  ]);
  assert.deepEqual(Array.from(rows, ({week, team}) => [week, team]), [
    [1, "Zulu"], [3, "Charlie"], [2, "Beta"], [3, "Alpha"], [3, "Bravo"],
  ]);
  assert.throws(() => sortWeeklyRows(rows, "sideways"), /Invalid week order/);
});

test("wins gained treats a tie as half a win", () => {
  assert.equal(RESULT_WINS.T, 0.5);
  assert.equal(winsGained({result: "W", alternate_result: "T"}), 0.5);
  assert.equal(winsGained({result: "L", alternate_result: "W"}), -1);
});

test("weekly links carry league, manager, and optional week", () => {
  const league = {key: "premier"};
  assert.equal(weeklyHref(league, {team_id: 4, week: 2}), "./weekly.html?league=premier&team=premier%3A4");
  assert.equal(weeklyHref(league, {team_id: 4, week: 2}, true), "./weekly.html?league=premier&team=premier%3A4&week=2");
  assert.deepEqual(weeklyRows({}), []);
});

test("replacement summaries name the slot, the player, and who they displaced", () => {
  assert.equal(describeReplacements([
    {slot: "RB", name: "Bench Back", replaced: null},
    {slot: "WR", name: "Old Friend", replaced: "Rookie"},
    {slot: "TE", name: null, replaced: null},
  ]), "RB: Bench Back · WR: Old Friend over Rookie · TE: no eligible player");
});
