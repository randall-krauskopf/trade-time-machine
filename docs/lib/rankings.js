// Leaderboard rankings. Pure: every board turns data into ranked entries,
// and pages/leaderboards.js renders them.
//
// Entry shape: {team?, trade?, rankScore, value, detail?, href?}. `rankScore`
// decides ties, `value` is the display text. Entries with `trade` open the
// archive; entries with `href` link elsewhere.

import {countOf, formatPoints, formatSigned} from "./format.js";
import {winsGained} from "./results.js";
import {archiveHref, playersExchanged} from "./trades.js";
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

/**
 * Holding Steady: managers with the fewest completed deals, including those
 * with none. The full team list comes from the historical team-season list
 * or the current league's standings. Managers tied on a
 * count share one entry (zero-trade ties are common), so entries rank 1, 2, 3
 * by distinct trade count and the detail line says how many are tied.
 */
export function rankFewestTrades(trades, league) {
  const teams = league?.teams || league?.alternate_standings?.teams || [];
  const counts = new Map(teams.map((team) => [team.team_id, 0]));
  for (const trade of trades) {
    for (const side of trade.sides) {
      if (counts.has(side.team_id)) counts.set(side.team_id, counts.get(side.team_id) + 1);
    }
  }
  const groups = new Map();
  for (const team of teams) {
    const count = counts.get(team.team_id);
    groups.set(count, [...(groups.get(count) || []), team.team]);
  }
  return [...groups.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([count, names]) => ({
      team: names.sort((a, b) => a.localeCompare(b)).join(" · "),
      rankScore: count,
      value: countOf(count, "trade"),
      detail: names.length > 1 ? `${names.length} managers tied` : undefined,
      managerCount: names.length,
    }));
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

/**
 * Most Traded Player: players moved in at least two completed deals, with the
 * path between managers. Entries open the player's most recent trade.
 */
export function rankMostTradedPlayers(trades) {
  const players = new Map();
  const ordered = [...trades].sort((a, b) => Date.parse(a.traded_at) - Date.parse(b.traded_at) || a.id.localeCompare(b.id));
  for (const trade of ordered) {
    for (const side of trade.sides) {
      const receiver = trade.sides.find((other) => other !== side);
      for (const player of side.sent) {
        const entry = players.get(player.id) || {name: player.name, path: [side.team], trades: []};
        if (entry.path.at(-1) !== side.team) entry.path.push(side.team);
        entry.path.push(receiver.team);
        entry.trades.push(trade);
        players.set(player.id, entry);
      }
    }
  }
  return [...players.values()]
    .filter((player) => player.trades.length > 1)
    .sort((a, b) => b.trades.length - a.trades.length
      || Date.parse(b.trades.at(-1).traded_at) - Date.parse(a.trades.at(-1).traded_at) || a.name.localeCompare(b.name))
    .map((player) => ({
      team: player.name,
      rankScore: player.trades.length,
      value: countOf(player.trades.length, "trade"),
      detail: player.path.join(" → "),
      href: archiveHref(player.trades.at(-1).id),
    }));
}

/** All manager-week lineup gaps (best possible lineup minus actual starters). */
export function lineupGaps(league) {
  return (league?.alternate_standings?.weeks || [])
    .flatMap((week) => (week.lineups || []).map((lineup) => ({...lineup, week: week.week})));
}

/** Left on the Bench: manager-weeks with the most points stranded on the bench. */
export function rankPointsLeftOnBench(league) {
  return lineupGaps(league)
    .filter((row) => {
      if (!Number.isFinite(row.points_left)) throw new Error(`Invalid bench points for ${row.team}, Week ${row.week}.`);
      return row.points_left > 0;
    })
    .sort((a, b) => b.points_left - a.points_left || a.week - b.week || a.team.localeCompare(b.team))
    .map((row) => ({
      team: row.team,
      rankScore: row.points_left,
      value: `${formatPoints(row.points_left)} pts`,
      detail: `Week ${row.week} · ${formatPoints(row.actual_points)} of ${formatPoints(row.optimal_points)} possible`
        + (row.top_bench ? ` · ${row.top_bench.name} sat with ${formatPoints(row.top_bench.points)}` : ""),
    }));
}

/** Biggest Margin of Victory: actual completed matchups, including managers who never traded. */
export function rankBiggestMarginOfVictory(league) {
  const teams = new Map((league?.alternate_standings?.teams || []).map((team) => [team.team_id, team.team]));
  const entries = [];
  for (const week of league?.alternate_standings?.weeks || []) {
    for (const matchup of week.matchups || []) {
      const {home_team_id: home, away_team_id: away, home_score: homeScore, away_score: awayScore} = matchup;
      if (!Number.isFinite(homeScore) || !Number.isFinite(awayScore)) {
        throw new Error(`Invalid matchup score for Week ${week.week}.`);
      }
      if (!teams.has(home) || !teams.has(away)) throw new Error(`Unknown matchup team for Week ${week.week}.`);
      if (homeScore === awayScore) continue;
      const homeWon = homeScore > awayScore;
      const winner = homeWon ? home : away;
      const loser = homeWon ? away : home;
      const score = homeWon ? homeScore : awayScore;
      const opponentScore = homeWon ? awayScore : homeScore;
      const margin = Math.round((score - opponentScore) * 100) / 100;
      entries.push({
        team: teams.get(winner),
        rankScore: margin,
        value: `${formatPoints(margin)} pts`,
        detail: `Week ${week.week} · vs ${teams.get(loser)} · ${formatPoints(score)}–${formatPoints(opponentScore)}`,
        week: week.week,
        team_id: winner,
      });
    }
  }
  return entries.sort((a, b) => b.rankScore - a.rankScore || a.week - b.week
    || a.team.localeCompare(b.team) || a.team_id - b.team_id);
}

/** Board definitions in display order. `rank(trades, league)` gets one league's trades. */
export const LEADERBOARDS = [
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
    title: "Biggest Roster Swings",
    caption: "Biggest weekly matchup point swings, for better or worse.",
    empty: "No weekly point swings yet.",
    rank: (trades, league) => rankWeeklySwings(league),
  },
  {
    title: "Most Traded Player",
    caption: "Players moved in two or more deals, and the path they took.",
    empty: "No player has been traded twice yet.",
    rank: (trades) => rankMostTradedPlayers(trades),
  },
  {
    title: "Left on the Bench",
    caption: "Most points a manager's best possible lineup beat their actual starters in one week.",
    empty: "No weekly lineup data available.",
    rank: (trades, league) => rankPointsLeftOnBench(league),
  },
  {
    title: "Biggest Margin of Victory",
    caption: "Largest actual winning margins in completed weekly matchups, trades or no trades.",
    empty: "No completed wins with matchup data available.",
    rank: (trades, league) => rankBiggestMarginOfVictory(league),
  },
  {
    title: "Most active traders",
    caption: "Managers with the most completed deals.",
    empty: "No eligible trades yet.",
    rank: (trades) => rankMostActiveTraders(trades),
  },
  {
    title: "Holding Steady",
    caption: "Managers with the fewest completed deals, zero included.",
    empty: "No team list available.",
    rank: (trades, league) => rankFewestTrades(trades, league),
  },
  {
    title: "Most players exchanged",
    caption: "Blockbusters by total players changing hands.",
    empty: "No eligible trades yet.",
    rank: (trades) => rankMostPlayersExchanged(trades),
  },
];

export const LEADERBOARD_TOP_N = 3;
