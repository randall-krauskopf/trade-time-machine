// Weekly Moves page (weekly.html): one card per manager-week trade bundle.
// URL params: league=<key>, team=<key>:<team_id>, week=<n> (all validated).

import {$, fillSelect, hasOption, appendOptions, node} from "../lib/dom.js";
import {formatPoints, formatSigned} from "../lib/format.js";
import {addLeagueOptions, fetchSnapshot, showContext, showLoadError, showSelectedLeague, showSeasons} from "../lib/page.js";
import {outcomeClass} from "../lib/results.js";
import {archiveHref, archiveTradeId} from "../lib/trades.js";
import {describeReplacements, sortWeeklyRows, weeklyRows} from "../lib/weekly-moves.js";

const OUTCOME_LABEL = {clutch: "Clutch", oof: "Oof"};
const STARTER_SLOT_ORDER = ["QB", "RB", "WR", "TE", "RB/WR/TE", "K"];

let leagues = [];

function visibleLeagues() {
  const filter = $("league-filter").value;
  return leagues.filter((league) => !filter || league.key === filter);
}

function renderTeamOptions() {
  const selected = $("team-filter").value;
  const showLeague = !$("league-filter").value;
  const teams = new Map();
  for (const league of visibleLeagues()) {
    for (const row of weeklyRows(league)) {
      teams.set(`${league.key}:${row.team_id}`, `${row.team}${showLeague ? ` (${league.label})` : ""}`);
    }
  }
  fillSelect($("team-filter"), "All managers", [...teams].sort((a, b) => a[1].localeCompare(b[1])));
  $("team-filter").value = teams.has(selected) ? selected : "";
}

function playerList(title, players, kind) {
  const section = node("div", `weekly-players ${kind}`);
  section.append(node("p", "weekly-list-label", title));
  if (!players.length) {
    section.append(node("p", "weekly-none", "No net change"));
    return section;
  }
  const list = node("ul");
  for (const player of players) list.append(node("li", "", player.name));
  section.append(list);
  return section;
}

function resultBadge(value) {
  return node("span", `result-badge ${value.toLowerCase()}`, value);
}

function scoreLine(label, score, opponentScore, result) {
  const line = node("div");
  line.append(node("span", "", label), node("strong", "", `${score.toFixed(2)}–${opponentScore.toFixed(2)}`), resultBadge(result));
  return line;
}

function finalLineup(row) {
  const details = node("details", "weekly-final-lineup");
  details.append(node("summary", "", "Final lineup"));
  if (!row.final_lineup) {
    details.append(node("p", "weekly-none", "Final lineup unavailable in this snapshot."));
    return details;
  }
  details.append(node("p", "leaderboard-caption", "Actual end-of-week roster and player points. Bench and IR points do not count toward the matchup score."));
  const slotOrder = (slot) => {
    const index = STARTER_SLOT_ORDER.indexOf(slot);
    return index === -1 ? STARTER_SLOT_ORDER.length : index;
  };
  const starters = row.final_lineup
    .filter((player) => !["BE", "IR"].includes(player.slot))
    .sort((a, b) => slotOrder(a.slot) - slotOrder(b.slot));
  for (const [label, players] of [
    ["Starters", starters],
    ["Bench", row.final_lineup.filter((player) => player.slot === "BE")],
    ["IR", row.final_lineup.filter((player) => player.slot === "IR")],
  ]) {
    if (!players.length) continue;
    const table = node("table", "weekly-lineup-table");
    table.append(node("caption", "", label));
    const head = node("thead");
    const headings = node("tr");
    for (const title of ["Slot", "Player", "Points"]) {
      const cell = node("th", "", title);
      cell.scope = "col";
      headings.append(cell);
    }
    head.append(headings);
    const body = node("tbody");
    for (const player of players) {
      const tr = node("tr");
      tr.append(node("td", "", player.slot), node("td", "", player.name), node("td", "", formatPoints(player.points)));
      body.append(tr);
    }
    table.append(head, body);
    details.append(table);
  }
  return details;
}

function weeklyCard(league, row) {
  const outcome = outcomeClass(row);
  const card = node("article", `weekly-card${outcome ? ` ${outcome}` : ""}`);

  const top = node("div", "weekly-card-top");
  const identity = node("div");
  identity.append(node("p", "eyebrow", `WEEK ${row.week} · ${row.trade_count} TRADE${row.trade_count === 1 ? "" : "S"}`), node("h4", "", row.team));
  if (outcome) identity.append(node("span", `weekly-outcome ${outcome}`, OUTCOME_LABEL[outcome]));
  const impact = node("div", "weekly-impact");
  impact.append(
    node("strong", "", `${formatSigned(row.net_points, 2)} pts`),
    node("span", "", outcome ? `${row.alternate_result} → ${row.result}` : "Result unchanged"),
  );
  top.append(identity, impact);

  const changes = node("div", "weekly-changes");
  changes.append(playerList("NET TRADED IN", row.received, "in"), playerList("NET TRADED OUT", row.sent, "out"));

  const matchup = node("div", "weekly-matchup");
  matchup.append(
    scoreLine("ACTUAL", row.actual_score, row.opponent_score, row.result),
    scoreLine("NO WEEKLY TRADES", row.alternate_score, row.opponent_alternate_score, row.alternate_result),
  );
  card.append(top, changes, node("p", "weekly-opponent", `vs ${row.opponent}`), matchup);
  if (row.replacements.length) {
    card.append(node("p", "weekly-replacements", `Alternate lineup · ${describeReplacements(row.replacements)}`));
  }

  const links = node("div", "weekly-links");
  row.trade_ids.forEach((id, index) => {
    const link = node("a", "", `Open trade ${index + 1}`);
    link.href = archiveHref(archiveTradeId(league, id));
    links.append(link);
  });
  card.append(finalLineup(row), links);
  return card;
}

function render() {
  const week = $("week-filter").value;
  const team = $("team-filter").value;
  showSelectedLeague($("league-filter"));
  const content = $("weekly-content");
  content.replaceChildren();
  let rendered = 0;
  for (const league of visibleLeagues()) {
    const rows = sortWeeklyRows(
      weeklyRows(league).filter((row) =>
        (!week || String(row.week) === week)
        && (!team || `${league.key}:${row.team_id}` === team)),
      $("week-order").value,
    );
    if (!rows.length) continue;
    rendered += rows.length;
    const section = node("section", "weekly-league");
    section.append(node("h3", "", `${league.label} · ${league.season}`));
    const grid = node("div", "weekly-grid");
    grid.append(...rows.map((row) => weeklyCard(league, row)));
    section.append(grid);
    content.append(section);
  }
  if (!rendered) content.append(node("p", "empty-state", "No completed manager-week trade bundles match these filters."));
}

/** Apply ?league, ?team, and ?week, failing loudly on values not in the snapshot. */
function applyUrlFilters() {
  const params = new URLSearchParams(window.location.search);
  if (params.has("league") && !leagues.some((league) => league.key === params.get("league"))) {
    throw new Error("The requested league is not in this snapshot.");
  }
  $("league-filter").value = params.get("league") || "";
  renderTeamOptions();
  if (params.has("team") && !hasOption($("team-filter"), params.get("team"))) {
    throw new Error("The requested manager is not in this snapshot.");
  }
  $("team-filter").value = params.get("team") || "";
  if (params.has("week")) {
    if (!hasOption($("week-filter"), params.get("week"))) throw new Error("The requested game week is not in this snapshot.");
    $("week-filter").value = params.get("week");
  }
}

async function main() {
  try {
    const data = await fetchSnapshot();
    leagues = data.leagues || [];
    showSeasons(leagues);
    const bundleCount = leagues.reduce((sum, league) => sum + weeklyRows(league).length, 0);
    const omitted = leagues.reduce((total, league) => total + (league.weekly_roster_moves?.omitted?.length || 0), 0);
    showContext([`${bundleCount} manager-week trade bundles${omitted ? ` · ${omitted} excluded (incomplete historical inputs)` : ""}`], data.generated_at);
    addLeagueOptions($("league-filter"), leagues);
    const weeks = [...new Set(leagues.flatMap((league) => weeklyRows(league).map((row) => row.week)))].sort((a, b) => b - a);
    appendOptions($("week-filter"), weeks.map((week) => [String(week), `Week ${week}`]));
    applyUrlFilters();
    $("league-filter").addEventListener("change", () => {
      renderTeamOptions();
      render();
    });
    $("week-filter").addEventListener("change", render);
    $("team-filter").addEventListener("change", render);
    $("week-order").addEventListener("change", render);
    $("weekly-moves").classList.remove("hidden");
    render();
  } catch (error) {
    showLoadError(error);
  }
}

main();
