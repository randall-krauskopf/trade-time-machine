import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  LEADERBOARDS, competitionRanks, rankFewestTrades, rankMostActiveTraders, rankMostPlayersExchanged, rankWeeklyOutcomes, rankWeeklySwings,
  lineupGaps, rankMostTradedPlayers, rankPointsLeftOnBench, rankBiggestMarginOfVictory,
} from "../../docs/lib/rankings.js";
import {normalizeSnapshot} from "../../docs/lib/snapshot.js";

const snapshotPath = new URL("../../docs/data.json", import.meta.url);

test("activity leaderboards occupy the final row", () => {
  assert.deepEqual(LEADERBOARDS.map((board) => board.title), [
    "Wins Traded For", "Wins Traded Away", "Biggest Roster Swings",
    "Most Traded Player", "Left on the Bench", "Biggest Margin of Victory",
    "Most active traders", "Holding Steady", "Most players exchanged",
  ]);
});

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
  const {leagues} = JSON.parse(fs.readFileSync(snapshotPath, "utf8"));
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

test("most active traders count each side of a deal once per team", () => {
  const trades = [
    {sides: [{team: "Beta"}, {team: "Alpha"}]},
    {sides: [{team: "Alpha"}, {team: "Charlie"}]},
  ];
  assert.deepEqual(rankMostActiveTraders(trades).map(({team, value}) => [team, value]), [
    ["Alpha", "2 trades"], ["Beta", "1 trade"], ["Charlie", "1 trade"],
  ]);
});

test("blockbusters rank by players exchanged, newest first on ties", () => {
  const trade = (id, tradedAt, counts) => ({
    id, traded_at: tradedAt,
    sides: counts.map((count, index) => ({team: `T${index}`, received: Array(count).fill({})})),
  });
  const ranked = rankMostPlayersExchanged([
    trade("old", "2026-09-01T00:00:00Z", [1, 1]),
    trade("big", "2026-09-02T00:00:00Z", [2, 1]),
    trade("new", "2026-09-03T00:00:00Z", [1, 1]),
  ]);
  assert.deepEqual(ranked.map(({trade, value, detail}) => [trade.id, value, detail]), [
    ["big", "3 players", "2 to T0 · 1 to T1"],
    ["new", "2 players", "1 to T0 · 1 to T1"],
    ["old", "2 players", "1 to T0 · 1 to T1"],
  ]);
});

test("every board ranks the real snapshot without errors and has an empty-state message", () => {
  const snapshot = normalizeSnapshot(JSON.parse(fs.readFileSync(snapshotPath, "utf8")));
  for (const league of snapshot.leagues) {
    const trades = snapshot.trades.filter((trade) => trade.league_key === league.key);
    for (const board of LEADERBOARDS) {
      assert.ok(board.empty, `${board.title} needs an empty message`);
      const ranks = competitionRanks(board.rank(trades, league)).map((entry) => entry.rank);
      assert.deepEqual(ranks, [...ranks].sort((a, b) => a - b), `${board.title} ranks are ordered`);
    }
  }
});

test("Holding Steady ranks the fewest trades, counting managers who never traded", () => {
  const league = {alternate_standings: {teams: [
    {team_id: 1, team: "Alpha"}, {team_id: 2, team: "Bravo"}, {team_id: 3, team: "Charlie"},
    {team_id: 4, team: "Delta"}, {team_id: 5, team: "Echo"},
  ]}};
  const trades = [
    {sides: [{team_id: 1, team: "Alpha"}, {team_id: 2, team: "Bravo"}]},
    {sides: [{team_id: 1, team: "Alpha"}, {team_id: 3, team: "Charlie"}]},
  ];
  const ranked = competitionRanks(rankFewestTrades(trades, league));
  assert.deepEqual(ranked.map(({rank, team, value, detail}) => [rank, team, value, detail]), [
    [1, "Delta · Echo", "0 trades", "2 managers tied"],
    [2, "Bravo · Charlie", "1 trade", "2 managers tied"],
    [3, "Alpha", "2 trades", undefined],
  ]);
});

test("Holding Steady matches managers by team ID, not name, and needs a team list", () => {
  const league = {alternate_standings: {teams: [{team_id: 1, team: "Renamed"}, {team_id: 2, team: "Bravo"}]}};
  const trades = [{sides: [{team_id: 1, team: "Old Name"}, {team_id: 9, team: "Other league"}]}];
  assert.deepEqual(rankFewestTrades(trades, league).map(({team, rankScore}) => [team, rankScore]), [["Bravo", 0], ["Renamed", 1]]);
  assert.deepEqual(rankFewestTrades(trades, {}), []);
});

test("Holding Steady on the real snapshot accounts for every manager", () => {
  const snapshot = normalizeSnapshot(JSON.parse(fs.readFileSync(snapshotPath, "utf8")));
  for (const league of snapshot.leagues) {
    const trades = snapshot.trades.filter((trade) => trade.league_key === league.key);
    const entries = rankFewestTrades(trades, league);
    assert.equal(entries.reduce((total, entry) => total + entry.managerCount, 0), league.alternate_standings.teams.length);
    const sideCount = trades.reduce((total, trade) => total + trade.sides.length, 0);
    assert.equal(entries.reduce((total, entry) => total + entry.managerCount * entry.rankScore, 0), sideCount);
  }
});

test("Holding Steady works without alternate standings for historical seasons", () => {
  const league = {teams: [{team_id: 1, team: "No Deals"}, {team_id: 2, team: "Trader"}], alternate_standings: null};
  const trades = [{sides: [{team_id: 2, team: "Trader"}, {team_id: 3, team: "Other"}]}];
  assert.deepEqual(rankFewestTrades(trades, league).map(({team, rankScore}) => [team, rankScore]),
    [["No Deals", 0], ["Trader", 1]]);
});

test("Most Traded Player follows each player's path and skips one-time moves", () => {
  const deal = (id, tradedAt, [a, sentA], [b, sentB]) => ({
    id, traded_at: tradedAt,
    sides: [{team_id: a, team: `T${a}`, sent: sentA}, {team_id: b, team: `T${b}`, sent: sentB}],
  });
  const star = {id: 10, name: "Star"};
  const trades = [
    deal("third", "2026-09-20T00:00:00Z", [3, [star]], [4, [{id: 30, name: "Other"}]]),
    deal("first", "2026-09-01T00:00:00Z", [1, [star]], [2, [{id: 20, name: "Once"}]]),
    deal("second", "2026-09-10T00:00:00Z", [2, [star, {id: 21, name: "Twice"}]], [3, []]),
    deal("fourth", "2026-09-21T00:00:00Z", [3, [{id: 21, name: "Twice"}]], [1, []]),
  ];
  assert.deepEqual(rankMostTradedPlayers(trades).map(({team, value, detail, href}) => [team, value, detail, href]), [
    ["Star", "3 trades", "T1 → T2 → T3 → T4", "./archive.html?trade=third"],
    ["Twice", "2 trades", "T2 → T3 → T1", "./archive.html?trade=fourth"],
  ]);
  assert.deepEqual(rankMostTradedPlayers(trades.slice(1, 2)), []);
});

test("Biggest Margin of Victory ranks actual wins, once per matchup, without requiring trades", () => {
  const league = {alternate_standings: {
    teams: [{team_id: 1, team: "Alpha"}, {team_id: 2, team: "Beta"}, {team_id: 3, team: "Charlie"}],
    weeks: [
      {week: 1, matchups: [
        {home_team_id: 1, away_team_id: 2, home_score: 120.2, away_score: 90.1},
        {home_team_id: 3, away_team_id: 2, home_score: 70, away_score: 110},
      ]},
      {week: 2, matchups: [
        {home_team_id: 1, away_team_id: 3, home_score: 130.3, away_score: 100.2},
        {home_team_id: 2, away_team_id: 3, home_score: 100, away_score: 100},
      ]},
      {week: 3},
    ],
  }};
  const before = structuredClone(league);
  const entries = competitionRanks(rankBiggestMarginOfVictory(league));
  assert.deepEqual(entries.map(({rank, team, value, detail}) => [rank, team, value, detail]), [
    [1, "Beta", "40.00 pts", "Week 1 · vs Charlie · 110.00–70.00"],
    [2, "Alpha", "30.10 pts", "Week 1 · vs Beta · 120.20–90.10"],
    [2, "Alpha", "30.10 pts", "Week 2 · vs Charlie · 130.30–100.20"],
  ]);
  assert.deepEqual(league, before);
  assert.deepEqual(rankBiggestMarginOfVictory({alternate_standings: null}), []);
  assert.deepEqual(rankBiggestMarginOfVictory({}), []);
});

test("Biggest Margin of Victory rejects unknown scores and teams", () => {
  const league = {alternate_standings: {
    teams: [{team_id: 1, team: "Alpha"}, {team_id: 2, team: "Beta"}],
    weeks: [{week: 1, matchups: [{home_team_id: 1, away_team_id: 2, home_score: null, away_score: 90}]}],
  }};
  assert.throws(() => rankBiggestMarginOfVictory(league), /Invalid matchup score/);
  league.alternate_standings.weeks[0].matchups[0] = {home_team_id: 1, away_team_id: 9, home_score: 100, away_score: 90};
  assert.throws(() => rankBiggestMarginOfVictory(league), /Unknown matchup team/);
});

test("Biggest Margin of Victory uses every completed matchup in the published snapshot", () => {
  const snapshot = normalizeSnapshot(JSON.parse(fs.readFileSync(snapshotPath, "utf8")));
  for (const league of snapshot.leagues) {
    const weeks = league.alternate_standings.weeks;
    const matchups = weeks.flatMap((week) => week.matchups);
    assert.equal(matchups.length, weeks.length * league.alternate_standings.teams.length / 2);
    assert.ok(weeks.every((week) => league.completed_weeks.includes(week.week)));
    const ranked = rankBiggestMarginOfVictory(league);
    assert.equal(ranked.length, matchups.filter((matchup) => matchup.home_score !== matchup.away_score).length);
    const maximum = Math.max(...matchups.map((matchup) => Math.round(Math.abs(matchup.home_score - matchup.away_score) * 100) / 100));
    assert.equal(ranked[0].rankScore, maximum);
  }
});

test("Left on the Bench ranks manager-weeks by points stranded on the bench", () => {
  const lineup = (team_id, points_left, top_bench = null) => ({
    team_id, team: `T${team_id}`, actual_points: 100, optimal_points: 100 + points_left, points_left, top_bench,
  });
  const league = {alternate_standings: {weeks: [
    {week: 1, rewound_players: 0, lineups: [lineup(1, 12.5, {id: 9, name: "Sleeper", points: 20}), lineup(2, 0)]},
    {week: 2, rewound_players: 0, lineups: [lineup(2, 30)]},
    {week: 3, rewound_players: 0},
  ]}};
  assert.equal(lineupGaps(league).length, 3);
  assert.deepEqual(rankPointsLeftOnBench(league).map(({team, value, detail}) => [team, value, detail]), [
    ["T2", "30.00 pts", "Week 2 · 100.00 of 130.00 possible"],
    ["T1", "12.50 pts", "Week 1 · 100.00 of 112.50 possible · Sleeper sat with 20.00"],
  ]);
  assert.deepEqual(rankPointsLeftOnBench({alternate_standings: null}), []);
  assert.throws(() => rankPointsLeftOnBench({alternate_standings: {weeks: [{week: 1, lineups: [lineup(1, NaN)]}]}}), /Invalid bench points/);
});
