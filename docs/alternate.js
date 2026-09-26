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

function formatPoints(value) {
  return value === null || value === undefined ? "—" : Number(value).toFixed(2);
}

function formatSigned(value, digits = 1) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  return `${number > 0 ? "+" : number < 0 ? "−" : ""}${Math.abs(number).toFixed(digits)}`;
}

function record(team, prefix) {
  return `${team[`${prefix}_wins`]}-${team[`${prefix}_losses`]}-${team[`${prefix}_ties`]}`;
}

function renderAlternateStandings() {
  const content = $("alternate-content");
  content.replaceChildren();
  const filter = $("league-filter").value;
  const option = $("league-filter").selectedOptions[0];
  $("brand-league").textContent = `/ ${(filter ? option.textContent : "All leagues").toUpperCase()}`;
  for (const league of leagues.filter((entry) => !filter || entry.key === filter)) {
    const block = node("div", "alternate-league");
    const snapshot = league.alternate_standings;
    block.append(node("h3", "", `${league.label} · ${league.season}`));
    if (!snapshot) {
      block.append(node("p", "empty-state", "Alternate standings are not available for this snapshot."));
      content.append(block);
      continue;
    }
    const weeks = snapshot.weeks.map((entry) => entry.week);
    const rewound = snapshot.weeks.reduce((sum, entry) => sum + entry.rewound_players, 0);
    block.append(node("p", "alternate-summary", `${weeks.length ? `Weeks ${weeks.join(", ")}` : "No completed weeks"} · ${rewound} player-week trade transfers rewound${league.source === "reconstructed" ? " · trade records reconstructed; may be incomplete" : ""}`));
    if (!weeks.length) {
      block.append(node("p", "empty-state", "No completed matchups yet."));
      content.append(block);
      continue;
    }
    const scroll = node("div", "alternate-scroll");
    const table = node("table", "alternate-table");
    const head = node("thead");
    const heading = node("tr");
    for (const label of ["TEAM", "REAL W-L-T", "REAL PF", "CURRENT OPTIMAL W-L-T", "OPTIMAL PF", "NO TRADES W-L-T", "NO TRADES PF", "Δ WINS"]) {
      heading.append(node("th", "", label));
    }
    head.append(heading);
    const body = node("tbody");
    const rows = [...snapshot.teams].sort((a, b) =>
      (b.alternate_wins + b.alternate_ties / 2) - (a.alternate_wins + a.alternate_ties / 2)
      || b.alternate_points - a.alternate_points || a.team.localeCompare(b.team));
    for (const team of rows) {
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
    scroll.append(table);
    block.append(scroll);
    content.append(block);
  }
}

async function load() {
  try {
    const response = await fetch("./data.json", {cache: "no-store"});
    if (!response.ok) throw new Error(`Could not load data.json (HTTP ${response.status}).`);
    const data = await response.json();
    leagues = Array.isArray(data.leagues) ? data.leagues : [{...data, key: "premier", label: "Premier"}];
    const seasons = [...new Set(leagues.map((league) => league.season))];
    $("season-badge").textContent = `${seasons.join(" / ")} SEASON`;
    const summaries = leagues.map((league) => `${league.label} ${(league.completed_weeks || []).length} completed weeks`);
    $("context-bar").textContent = `Lana Straw · ${summaries.join(" · ")} · refreshed ${timeFormat.format(new Date(data.generated_at))}`;
    for (const league of leagues) {
      const option = node("option", "", league.label);
      option.value = league.key;
      $("league-filter").append(option);
    }
    $("league-filter").value = "";
    $("league-filter").addEventListener("change", renderAlternateStandings);
    $("alternate-standings").classList.remove("hidden");
    renderAlternateStandings();
  } catch (error) {
    $("context-bar").textContent = "Snapshot unavailable";
    $("error").textContent = `${error.message} Run generate.py, then serve this folder using python3 -m http.server (opening the file directly cannot fetch JSON).`;
    $("error").classList.remove("hidden");
  }
}

load();
