// Alternate Universe page (alternate.html): standings with every trade rewound.

import {$, node} from "../lib/dom.js";
import {formatPoints, formatSigned} from "../lib/format.js";
import {addLeagueOptions, fetchSnapshot, showContext, showLoadError, showSelectedLeague, showSeasons} from "../lib/page.js";

const COLUMNS = ["TEAM", "REAL W-L-T", "REAL PF", "CURRENT OPTIMAL W-L-T", "OPTIMAL PF", "NO TRADES W-L-T", "NO TRADES PF", "Δ WINS"];

let leagues = [];

/** "W-L-T" for one world: "actual", "optimal_actual", or "alternate". */
function record(team, world) {
  return `${team[`${world}_wins`]}-${team[`${world}_losses`]}-${team[`${world}_ties`]}`;
}

/** No-trades standings order: wins (ties as half), then points, then name. */
function byAlternateStanding(a, b) {
  return (b.alternate_wins + b.alternate_ties / 2) - (a.alternate_wins + a.alternate_ties / 2)
    || b.alternate_points - a.alternate_points || a.team.localeCompare(b.team);
}

function standingsTable(league, weeks) {
  const table = node("table", "alternate-table");
  const head = node("thead");
  const heading = node("tr");
  for (const label of COLUMNS) heading.append(node("th", "", label));
  head.append(heading);
  const body = node("tbody");
  for (const team of [...league.alternate_standings.teams].sort(byAlternateStanding)) {
    const row = node("tr");
    row.append(node("th", "", team.team));
    for (const value of [
      record(team, "actual"), formatPoints(team.actual_points),
      record(team, "optimal_actual"), formatPoints(team.optimal_actual_points),
      record(team, "alternate"), formatPoints(team.alternate_points),
      formatSigned(team.wins_change, Number.isInteger(team.wins_change) ? 0 : 1),
    ]) row.append(node("td", "", value));
    body.append(row);
  }
  table.append(node("caption", "", `${league.label} alternate universe standings after ${weeks.length} completed weeks`), head, body);
  return table;
}

function leagueBlock(league) {
  const block = node("div", "alternate-league");
  const standings = league.alternate_standings;
  block.append(node("h3", "", `${league.label} · ${league.season}`));
  if (!standings) {
    block.append(node("p", "empty-state", "Alternate standings are not available for this snapshot."));
    return block;
  }
  const weeks = standings.weeks.map((entry) => entry.week);
  const rewound = standings.weeks.reduce((sum, entry) => sum + entry.rewound_players, 0);
  const reconstructed = league.source === "reconstructed" ? " · trade records reconstructed; may be incomplete" : "";
  block.append(node("p", "alternate-summary", `${weeks.length ? `Weeks ${weeks.join(", ")}` : "No completed weeks"} · ${rewound} player-week trade transfers rewound${reconstructed}`));
  if (!weeks.length) {
    block.append(node("p", "empty-state", "No completed matchups yet."));
    return block;
  }
  const scroll = node("div", "alternate-scroll");
  scroll.append(standingsTable(league, weeks));
  block.append(scroll);
  return block;
}

function render() {
  const filter = $("league-filter").value;
  showSelectedLeague($("league-filter"));
  $("alternate-content").replaceChildren(...leagues.filter((league) => !filter || league.key === filter).map(leagueBlock));
}

async function main() {
  try {
    const data = await fetchSnapshot();
    leagues = data.leagues;
    showSeasons(leagues);
    showContext(leagues.map((league) => `${league.label} ${(league.completed_weeks || []).length} completed weeks`), data.generated_at);
    addLeagueOptions($("league-filter"), leagues);
    $("league-filter").value = "";
    $("league-filter").addEventListener("change", render);
    $("alternate-standings").classList.remove("hidden");
    render();
  } catch (error) {
    showLoadError(error);
  }
}

main();
