const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = __dirname;
const script = fs.readFileSync(path.join(root, "docs/app.js"), "utf8").replace(/\nload\(\);\s*$/, "");
const rankWeeklyOutcomes = vm.runInNewContext(`${script}\nrankWeeklyOutcomes`, {Intl});

test("sums gains and losses separately, counts ties as half a win, and ignores unchanged results", () => {
  const rows = [
    {team_id: 1, team: "Alpha", week: 1, result: "W", alternate_result: "L"},
    {team_id: 1, team: "Alpha", week: 2, result: "L", alternate_result: "T"},
    {team_id: 1, team: "Alpha", week: 3, result: "T", alternate_result: "L"},
    {team_id: 1, team: "Alpha", week: 4, result: "L", alternate_result: "L"},
    {team_id: 2, team: "Alpha", week: 1, result: "L", alternate_result: "W"},
    {team_id: 3, team: "Beta", week: 1, result: "T", alternate_result: "W"},
    {team_id: 4, team: "Charlie", week: 1, result: "W", alternate_result: "L"},
  ];
  const league = {key: "premier", weekly_roster_moves: {rows}};
  const gains = rankWeeklyOutcomes(league, 1);
  const losses = rankWeeklyOutcomes(league, -1);
  assert.deepEqual(Array.from(gains, (entry) => [entry.team, entry.value, entry.detail]), [
    ["Alpha", "1.5 wins", "Weeks 1, 3"],
    ["Charlie", "1 win", "Week 1"],
  ]);
  assert.deepEqual(Array.from(losses, (entry) => [entry.value, entry.href]), [
    ["1 win", "./weekly.html?league=premier&team=premier%3A2"],
    ["0.5 wins", "./weekly.html?league=premier&team=premier%3A1"],
    ["0.5 wins", "./weekly.html?league=premier&team=premier%3A3"],
  ]);
});

test("rejects unknown matchup results instead of misranking a manager", () => {
  assert.throws(() => rankWeeklyOutcomes({
    key: "premier",
    weekly_roster_moves: {rows: [{team_id: 1, team: "Alpha", week: 1, result: "?", alternate_result: "L"}]},
  }, 1), /Invalid weekly result/);
});

test("same team ID in another league ranks separately and links to its own manager", () => {
  const row = {team_id: 9, team: "Manager", week: 1, result: "W", alternate_result: "L"};
  const premier = {key: "premier", weekly_roster_moves: {rows: [row]}};
  const champeens = {key: "champeens", weekly_roster_moves: {rows: [row, {...row, week: 2}]}};
  assert.equal(rankWeeklyOutcomes(premier, 1)[0].value, "1 win");
  assert.equal(rankWeeklyOutcomes(champeens, 1)[0].value, "2 wins");
  assert.equal(rankWeeklyOutcomes(champeens, 1)[0].href, "./weekly.html?league=champeens&team=champeens%3A9");
});
