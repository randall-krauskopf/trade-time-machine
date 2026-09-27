"use strict";

const $ = (id) => document.getElementById(id);
const timeFormat = new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago", timeZoneName: "short"});
let leagues = [];

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

function signed(value) {
  const number = Number(value);
  return `${number > 0 ? "+" : number < 0 ? "−" : ""}${Math.abs(number).toFixed(2)}`;
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

function render() {
  const leagueFilter = $("league-filter").value;
  const weekFilter = $("week-filter").value;
  const option = $("league-filter").selectedOptions[0];
  $("brand-league").textContent = `/ ${(leagueFilter ? option.textContent : "All leagues").toUpperCase()}`;
  const content = $("weekly-content");
  content.replaceChildren();
  let rendered = 0;
  for (const league of leagues.filter((entry) => !leagueFilter || entry.key === leagueFilter)) {
    const rows = (league.weekly_roster_moves?.rows || [])
      .filter((row) => !weekFilter || String(row.week) === weekFilter)
      .sort((a, b) => a.week - b.week || b.trade_count - a.trade_count || a.team.localeCompare(b.team));
    if (!rows.length) continue;
    rendered += rows.length;
    const section = node("section", "weekly-league");
    section.append(node("h3", "", `${league.label} · ${league.season}`));
    const grid = node("div", "weekly-grid");
    for (const row of rows) {
      const card = node("article", `weekly-card${row.flipped ? " flipped" : ""}`);
      const top = node("div", "weekly-card-top");
      const identity = node("div");
      identity.append(node("p", "eyebrow", `WEEK ${row.week} · ${row.trade_count} TRADE${row.trade_count === 1 ? "" : "S"}`), node("h4", "", row.team));
      const impact = node("div", `weekly-impact ${row.net_points > 0 ? "positive" : row.net_points < 0 ? "negative" : ""}`);
      impact.append(node("strong", "", `${signed(row.net_points)} pts`), node("span", "", row.flipped ? `${row.alternate_result} → ${row.result}` : "Result unchanged"));
      top.append(identity, impact);
      const changes = node("div", "weekly-changes");
      changes.append(playerList("NET TRADED IN", row.received, "in"), playerList("NET TRADED OUT", row.sent, "out"));
      const matchup = node("div", "weekly-matchup");
      const actual = node("div");
      actual.append(node("span", "", "ACTUAL"), node("strong", "", `${row.actual_score.toFixed(2)}–${row.opponent_score.toFixed(2)}`), resultBadge(row.result));
      const alternate = node("div");
      alternate.append(node("span", "", "NO WEEKLY TRADES"), node("strong", "", `${row.alternate_score.toFixed(2)}–${row.opponent_alternate_score.toFixed(2)}`), resultBadge(row.alternate_result));
      matchup.append(actual, alternate);
      card.append(top, changes, node("p", "weekly-opponent", `vs ${row.opponent}`), matchup);
      if (row.replacements.length) {
        card.append(node("p", "weekly-replacements", `Alternate lineup · ${row.replacements.map((change) => change.name ? `${change.slot}: ${change.name}${change.replaced ? ` over ${change.replaced}` : ""}` : `${change.slot}: no eligible player`).join(" · ")}`));
      }
      const links = node("div", "weekly-links");
      row.trade_ids.forEach((id, index) => {
        const link = node("a", "", `Open trade ${index + 1}`);
        link.href = `./archive.html?trade=${encodeURIComponent(`${league.key}-${id}`)}`;
        links.append(link);
      });
      card.append(links);
      grid.append(card);
    }
    section.append(grid);
    content.append(section);
  }
  if (!rendered) content.append(node("p", "empty-state", "No completed manager-week trade bundles match these filters."));
}

async function load() {
  try {
    const response = await fetch("./data.json", {cache: "no-store"});
    if (!response.ok) throw new Error(`Could not load data.json (HTTP ${response.status}).`);
    const data = await response.json();
    leagues = data.leagues || [];
    const seasons = [...new Set(leagues.map((league) => league.season))];
    $("season-badge").textContent = `${seasons.join(" / ")} SEASON`;
    const rowCount = leagues.reduce((sum, league) => sum + (league.weekly_roster_moves?.rows.length || 0), 0);
    $("context-bar").textContent = `Lana Straw · ${rowCount} manager-week trade bundles · refreshed ${timeFormat.format(new Date(data.generated_at))}`;
    for (const league of leagues) {
      const option = node("option", "", league.label);
      option.value = league.key;
      $("league-filter").append(option);
    }
    const weeks = [...new Set(leagues.flatMap((league) => (league.weekly_roster_moves?.rows || []).map((row) => row.week)))].sort((a, b) => a - b);
    for (const week of weeks) {
      const option = node("option", "", `Week ${week}`);
      option.value = String(week);
      $("week-filter").append(option);
    }
    $("league-filter").addEventListener("change", render);
    $("week-filter").addEventListener("change", render);
    $("weekly-moves").classList.remove("hidden");
    render();
  } catch (error) {
    $("context-bar").textContent = "Snapshot unavailable";
    $("error").textContent = `${error.message} Run generate.py, then serve this folder using python3 -m http.server.`;
    $("error").classList.remove("hidden");
  }
}

load();
