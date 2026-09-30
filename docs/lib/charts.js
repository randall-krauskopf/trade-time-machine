// Data for the leaderboard page's charts. Pure: safe to import in Node tests.
//
// Every function takes one league's trades (after normalizeSnapshot) and/or the
// league record, so team IDs are unambiguous.

import {weeklyRows} from "./weekly-moves.js";

const round2 = (value) => Math.round(value * 100) / 100;

/**
 * Trades per game week, from week 1 through the latest completed or traded week.
 * Weeks with no trades count as zero; `complete` is false for the week in progress.
 */
export function tradesPerWeek(trades, league) {
  const counts = new Map();
  for (const trade of trades) {
    if (!Number.isInteger(trade.transaction_week) || trade.transaction_week < 1) {
      throw new Error(`Invalid transaction week for trade ${trade.id}.`);
    }
    counts.set(trade.transaction_week, (counts.get(trade.transaction_week) || 0) + 1);
  }
  const completed = new Set(league?.completed_weeks || []);
  const last = Math.max(0, ...completed, ...counts.keys());
  return Array.from({length: last}, (_, index) => ({
    week: index + 1,
    count: counts.get(index + 1) || 0,
    complete: completed.has(index + 1),
  }));
}

/** Every manager in the league: the full team list when present, plus anyone seen in a trade. */
export function leagueTeams(trades, league) {
  const teams = new Map((league?.teams || league?.alternate_standings?.teams || [])
    .map((team) => [team.team_id, {team_id: team.team_id, team: team.team}]));
  for (const trade of trades) {
    for (const side of trade.sides) {
      if (!teams.has(side.team_id)) teams.set(side.team_id, {team_id: side.team_id, team: side.team});
    }
  }
  return [...teams.values()].sort((a, b) => a.team.localeCompare(b.team) || a.team_id - b.team_id);
}

/**
 * Trade partner heatmap: a symmetric team-by-team matrix of completed deals.
 * `topPairs` lists every pair tied for the most deals.
 */
export function tradePartners(trades, league) {
  const teams = leagueTeams(trades, league);
  const index = new Map(teams.map((team, position) => [team.team_id, position]));
  const counts = teams.map(() => teams.map(() => 0));
  for (const trade of trades) {
    const ids = [...new Set(trade.sides.map((side) => side.team_id))];
    for (let a = 0; a < ids.length; a += 1) {
      for (let b = a + 1; b < ids.length; b += 1) {
        counts[index.get(ids[a])][index.get(ids[b])] += 1;
        counts[index.get(ids[b])][index.get(ids[a])] += 1;
      }
    }
  }
  let max = 0;
  let topPairs = [];
  counts.forEach((row, a) => row.forEach((count, b) => {
    if (b <= a || count === 0 || count < max) return;
    if (count > max) {
      max = count;
      topPairs = [];
    }
    topPairs.push({teams: [teams[a], teams[b]], count});
  }));
  return {teams, counts, max, topPairs};
}

/**
 * Per manager: total Weekly Moves point swing (actual minus no-weekly-trades
 * lineup) across their verified manager-weeks, best first.
 */
export function netWeeklySwing(league) {
  const managers = new Map();
  for (const row of weeklyRows(league)) {
    if (!Number.isFinite(row.net_points)) throw new Error(`Invalid weekly point swing for ${row.team}, Week ${row.week}.`);
    const manager = managers.get(row.team_id) || {team_id: row.team_id, team: row.team, net: 0, weeks: 0};
    manager.net += row.net_points;
    manager.weeks += 1;
    managers.set(row.team_id, manager);
  }
  return [...managers.values()]
    .map((manager) => ({...manager, net: round2(manager.net)}))
    .sort((a, b) => b.net - a.net || a.team.localeCompare(b.team));
}
