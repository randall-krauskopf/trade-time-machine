const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = __dirname;
const script = fs.readFileSync(path.join(root, "docs/app.js"), "utf8").replace(/\nload\(\);\s*$/, "");
const {competitionRanks, rankWeeklyOutcomes, rankWeeklySwings} = vm.runInNewContext(`${script}\n({competitionRanks, rankWeeklyOutcomes, rankWeeklySwings})`, {Intl, URLSearchParams});

test("ties share competition ranks without implying an arbitrary order", () => {
  const entries = competitionRanks([
    {team: "Alpha", rankScore: 2},
    {team: "Bravo", rankScore: 1},
    {team: "Charlie", rankScore: 1},
    {team: "Delta", rankScore: 0.5},
  ]);
  assert.deepEqual(Array.from(entries, ({team, rank}) => [team, rank]), [
    ["Alpha", 1], ["Bravo", 2], ["Charlie", 2], ["Delta", 4],
  ]);
  assert.throws(() => competitionRanks([{team: "Bad", rankScore: NaN}]), /Invalid leaderboard score/);
});

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
    ["1 loss", "./weekly.html?league=premier&team=premier%3A2"],
    ["0.5 losses", "./weekly.html?league=premier&team=premier%3A1"],
    ["0.5 losses", "./weekly.html?league=premier&team=premier%3A3"],
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

test("ranks absolute weekly point swings regardless of result change or trade count", () => {
  const league = {key: "premier", weekly_roster_moves: {rows: [
    {team_id: 4, team: "Delta", week: 3, net_points: 30, result: "L", alternate_result: "L", trade_count: 2},
    {team_id: 2, team: "Beta", week: 1, net_points: -50, result: "L", alternate_result: "W", trade_count: 3},
    {team_id: 3, team: "Charlie", week: 2, net_points: 50, result: "W", alternate_result: "L", trade_count: 1},
    {team_id: 1, team: "Alpha", week: 2, net_points: 50, result: "W", alternate_result: "L", trade_count: 1},
    {team_id: 5, team: "Echo", week: 1, net_points: 0, result: "L", alternate_result: "L", trade_count: 1},
  ]}};
  const ranked = rankWeeklySwings(league);
  assert.deepEqual(Array.from(ranked, ({team, value, detail, href}) => [team, value, detail, href]), [
    ["Beta", "−50.00 pts", "Week 1 · W → L", "./weekly.html?league=premier&team=premier%3A2&week=1"],
    ["Alpha", "+50.00 pts", "Week 2 · L → W", "./weekly.html?league=premier&team=premier%3A1&week=2"],
    ["Charlie", "+50.00 pts", "Week 2 · L → W", "./weekly.html?league=premier&team=premier%3A3&week=2"],
    ["Delta", "+30.00 pts", "Week 3 · Result unchanged", "./weekly.html?league=premier&team=premier%3A4&week=3"],
  ]);
  assert.deepEqual(Array.from(league.weekly_roster_moves.rows, (row) => row.team), ["Delta", "Beta", "Charlie", "Alpha", "Echo"]);
  assert.equal(rankWeeklySwings({key: "champeens", weekly_roster_moves: {rows: []}}).length, 0);
  assert.throws(() => rankWeeklySwings({key: "premier", weekly_roster_moves: {rows: [{team: "Bad", week: 1, net_points: null}]}}), /Invalid weekly point swing/);
});

test("snapshot's largest swings come from weekly bundles in each league", () => {
  const {leagues} = JSON.parse(fs.readFileSync(path.join(root, "docs/data.json"), "utf8"));
  for (const league of leagues) {
    const ranked = rankWeeklySwings(league);
    const rows = league.weekly_roster_moves.rows.filter((row) => row.net_points !== 0);
    assert.equal(ranked.length, rows.length);
    assert.equal(ranked[0].value.replace(/^[+−]/, ""), `${rows.reduce((max, row) => Math.max(max, Math.abs(row.net_points)), 0).toFixed(2)} pts`);
    const href = new URL(ranked[0].href, "https://example.test/");
    assert.equal(href.searchParams.get("league"), league.key);
    assert.ok(rows.some((row) => href.searchParams.get("team") === `${league.key}:${row.team_id}` && href.searchParams.get("week") === String(row.week)));
  }
});
