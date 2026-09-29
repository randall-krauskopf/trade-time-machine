const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "docs/weekly.js"), "utf8").replace(/\nload\(\);\s*$/, "");
const {outcomeClass, sortWeeklyRows} = vm.runInNewContext(`${script}\n({outcomeClass, sortWeeklyRows})`, {Intl});

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
