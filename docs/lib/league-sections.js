import {node} from "./dom.js";

export function leagueGroups(snapshot) {
  return snapshot.leagues.length === 1
    ? [{label: null, league: snapshot.leagues[0], trades: snapshot.trades}]
    : snapshot.leagues.map((league) => ({
      label: league.label, league, trades: snapshot.trades.filter((trade) => trade.league_key === league.key),
    }));
}

export function omittedWeeks(snapshot) {
  return snapshot.leagues.reduce((total, league) => total + (league.weekly_roster_moves?.omitted?.length || 0), 0);
}

export function leagueRow(group, className, content) {
  if (!group.label) {
    const row = node("div", className);
    row.append(content);
    return row;
  }
  const row = node("details", `${className} collapsible`);
  row.open = true;
  row.append(node("summary", "leaderboard-league", `${group.label.toUpperCase()} LEAGUE`), content);
  return row;
}
