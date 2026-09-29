// Leaderboard rankings. Pure: every board turns data into ranked entries,
// and pages/leaderboards.js renders them.
//
// Entry shape: {team?, trade?, rankScore, value, detail?, href?}. `rankScore`
// decides ties, `value` is the display text. Entries with `trade` open the
// archive; entries with `href` link elsewhere.

import {countOf, formatSigned} from "./format.js";
import {winsGained} from "./results.js";
import {playersExchanged} from "./trades.js";
import {weeklyHref, weeklyRows} from "./weekly-moves.js";

/** Standard competition ranking ("1224"): tied scores share a rank and the next rank is skipped. */
export function competitionRanks(entries) {
  let previousScore;
  let rank = 0;
  return entries.map((entry, index) => {
    if (!Number.isFinite(entry.rankScore)) throw new Error(`Invalid leaderboard score for ${entry.team || "an entry"}.`);
    if (index === 0 || entry.rankScore !== previousScore) rank = index + 1;
    previousScore = entry.rankScore;
    return {...entry, rank};
  });
}

export function rankMostActiveTraders(trades) {
  const counts = new Map();
  for (const trade of trades) {
    for (const side of trade.sides) counts.set(side.team, (counts.get(side.team) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([team, count]) => ({team, rankScore: count, value: countOf(count, "trade")}));
}

export function rankMostPlayersExchanged(trades) {
  return trades
    .map((trade) => ({trade, count: playersExchanged(trade)}))
    .sort((a, b) => b.count - a.count || Date.parse(b.trade.traded_at) - Date.parse(a.trade.traded_at))
    .map(({trade, count}) => ({
      trade,
      rankScore: count,
      value: `${count} players`,
      detail: trade.sides.map((side) => `${side.received.length} to ${side.team}`).join(" · "),
    }));
}

/**
 * Wins Traded For (direction 1) or Away (direction −1): per manager, the total
 * result change across weeks where their trades changed the matchup that way.
 */
export function rankWeeklyOutcomes(league, direction) {
  const managers = new Map();
  for (const row of weeklyRows(league)) {
    const change = winsGained(row);
    if (direction * change <= 0) continue;
    const manager = managers.get(row.team_id) || {team: row.team, team_id: row.team_id, wins: 0, weeks: []};
    manager.wins += Math.abs(change);
    manager.weeks.push(row.week);
    managers.set(row.team_id, manager);
  }
  return [...managers.values()]
    .sort((a, b) => b.wins - a.wins || a.team.localeCompare(b.team))
    .map((manager) => ({
      team: manager.team,
      rankScore: manager.wins,
      value: direction > 0 ? countOf(manager.wins, "win") : countOf(manager.wins, "loss", "losses"),
      detail: `Week${manager.weeks.length === 1 ? "" : "s"} ${manager.weeks.sort((a, b) => a - b).join(", ")}`,
      href: weeklyHref(league, manager),
    }));
}

/** Biggest Roster Swings: largest absolute manager-week point swings, whether or not the result changed. */
export function rankWeeklySwings(league) {
  return weeklyRows(league)
    .filter((row) => {
      if (!Number.isFinite(row.net_points)) throw new Error(`Invalid weekly point swing for ${row.team}, Week ${row.week}.`);
      return row.net_points !== 0;
    })
    .sort((a, b) => Math.abs(b.net_points) - Math.abs(a.net_points)
      || a.week - b.week || a.team.localeCompare(b.team) || String(a.team_id).localeCompare(String(b.team_id)))
    .map((row) => ({
      team: row.team,
      rankScore: Math.abs(row.net_points),
      value: `${formatSigned(row.net_points, 2)} pts`,
      detail: `Week ${row.week} · ${row.alternate_result === row.result ? "Result unchanged" : `${row.alternate_result} → ${row.result}`}`,
      href: weeklyHref(league, row, true),
    }));
}

/** Board definitions in display order. `rank(trades, league)` gets one league's trades. */
export const LEADERBOARDS = [
  {
    title: "Most active traders",
    caption: "Managers with the most completed deals.",
    empty: "No eligible trades yet.",
    rank: (trades) => rankMostActiveTraders(trades),
  },
  {
    title: "Wins Traded For",
    caption: "Weekly trade bundles that improved matchup results.",
    empty: "No results changed yet.",
    rank: (trades, league) => rankWeeklyOutcomes(league, 1),
  },
  {
    title: "Wins Traded Away",
    caption: "Weekly trade bundles that worsened matchup results.",
    empty: "No results changed yet.",
    rank: (trades, league) => rankWeeklyOutcomes(league, -1),
  },
  {
    title: "Most players exchanged",
    caption: "Blockbusters by total players changing hands.",
    empty: "No eligible trades yet.",
    rank: (trades) => rankMostPlayersExchanged(trades),
  },
  {
    title: "Biggest Roster Swings",
    caption: "Biggest weekly matchup point swings, for better or worse.",
    empty: "No weekly point swings yet.",
    rank: (trades, league) => rankWeeklySwings(league),
  },
];

export const LEADERBOARD_TOP_N = 3;
