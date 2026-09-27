const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "docs/weekly.js"), "utf8").replace(/\nload\(\);\s*$/, "");
const outcomeClass = vm.runInNewContext(`${script}\noutcomeClass`, {Intl});

test("badges follow matchup results, including ties, rather than point swing", () => {
  const row = {team: "Manager", week: 1, net_points: -10};
  assert.equal(outcomeClass({...row, result: "W", alternate_result: "L"}), "clutch");
  assert.equal(outcomeClass({...row, result: "T", alternate_result: "L"}), "clutch");
  assert.equal(outcomeClass({...row, result: "L", alternate_result: "W"}), "oof");
  assert.equal(outcomeClass({...row, result: "T", alternate_result: "W"}), "oof");
  assert.equal(outcomeClass({...row, result: "L", alternate_result: "L"}), "");
  assert.throws(() => outcomeClass({...row, result: "?", alternate_result: "W"}), /Invalid weekly result/);
});
