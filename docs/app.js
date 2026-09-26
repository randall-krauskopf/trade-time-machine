"use strict";

const $ = (id) => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", year: "numeric", timeZone: "America/Chicago"});
const timeFormat = new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago", timeZoneName: "short"});
let archive = null;
let selectedId = null;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

function formatPoints(value) {
  return value === null || value === undefined ? "—" : Number(value).toFixed(2);
}

function teamKey(trade, side) {
  return `${trade.league_key}:${side.team_id}`;
}

function normalize(data) {
  const leagues = Array.isArray(data.leagues)
    ? data.leagues
    : [{...data, key: "premier", label: "Premier", receipts_enabled: true}];
  for (const league of leagues) {
    if (!Array.isArray(league.trades)) throw new Error(`data.json is missing trades for ${league.label || "a league"}.`);
  }
  const trades = leagues.flatMap((league) => league.trades.map((trade) => ({
    ...trade,
    id: `${league.key}-${trade.id}`,
    league,
    league_key: league.key,
    league_label: league.label,
  })));
  return {...data, leagues, trades};
}

function renderTeamOptions() {
  const league = $("league-filter").value;
  const current = $("team-filter").value;
  const showLeague = !league && archive.leagues.length > 1;
  const teams = new Map(archive.trades
    .filter((trade) => !league || trade.league_key === league)
    .flatMap((trade) => trade.sides.map((side) => [teamKey(trade, side), showLeague ? `${side.team} (${trade.league_label})` : side.team])));
  const all = node("option", "", "All teams");
  all.value = "";
  $("team-filter").replaceChildren(all);
  for (const [key, name] of [...teams].sort((a, b) => a[1].localeCompare(b[1]))) {
    const option = node("option", "", name);
    option.value = key;
    $("team-filter").append(option);
  }
  $("team-filter").value = teams.has(current) ? current : "";
}

function renderList() {
  const league = $("league-filter").value;
  const team = $("team-filter").value;
  const trades = archive.trades.filter((trade) =>
    (!league || trade.league_key === league)
    && (!team || trade.sides.some((side) => teamKey(trade, side) === team)));
  $("trade-count").textContent = `${trades.length} DEAL${trades.length === 1 ? "" : "S"}`;
  $("trade-list").replaceChildren();
  if (!trades.length) {
    $("trade-list").append(node("p", "empty-state", "No trades match these filters."));
    $("detail-panel").classList.add("hidden");
    return;
  }
  if (!trades.some((trade) => trade.id === selectedId)) {
    selectedId = (trades.find((trade) => trade.weeks.length) || trades[0]).id;
  }
  for (const trade of trades) {
    const button = node("button", `trade-item${selectedId === trade.id ? " active" : ""}`);
    button.type = "button";
    button.setAttribute("aria-pressed", String(selectedId === trade.id));
    button.append(
      node("span", "trade-item-date", `${trade.league_label.toUpperCase()} · ${dateFormat.format(new Date(trade.traded_at)).toUpperCase()}`),
      node("span", "trade-item-teams", trade.sides.map((side) => side.team).join(" ↔ ")),
      node("span", "trade-item-count", `${trade.sides.reduce((sum, side) => sum + side.received.length, 0)} players exchanged`)
    );
    button.addEventListener("click", () => {
      selectedId = trade.id;
      renderList();
    });
    $("trade-list").append(button);
  }
  $("detail-panel").classList.remove("hidden");
  renderDetail(trades.find((trade) => trade.id === selectedId));
}

function renderDetail(trade) {
  const [a, b] = trade.sides;
  $("detail-heading").textContent = `${a.team} ↔ ${b.team}`;
  $("trade-date").textContent = timeFormat.format(new Date(trade.traded_at));
  $("detail-league").textContent = `${trade.league_label.toUpperCase()} LEAGUE`;
  $("source-note").classList.toggle("hidden", trade.league.source !== "reconstructed");
  $("source-note").textContent = "ESPN's activity feed is members-only for this league, so this trade was rebuilt from accepted-trade records and roster history. Players who were later dropped or traded again may be missing.";
  $("receipts-scope").textContent = trade.league.receipts_enabled ? "PREMIER CHANNELS ONLY" : "NOT IMPORTED";
  $("trade-sides").replaceChildren();
  for (const side of trade.sides) {
    const card = node("div", "side-card");
    card.append(node("span", "side-label", "RECEIVED BY"), node("h3", "", side.team));
    const list = node("ul", "player-list");
    for (const player of side.received) {
      const item = node("li");
      item.append(node("span", "", player.name), node("span", "", "← IN"));
      list.append(item);
    }
    card.append(list);
    $("trade-sides").append(card);
  }

  const score = $("score-content");
  score.replaceChildren();
  $("scope-note").textContent = trade.weeks.length ? `WEEKS ${trade.weeks.join(", ")}` : "NO COMPLETED WEEKS YET";
  if (!trade.weeks.length) {
    score.append(node("p", "empty-state", "This deal is too recent. No scoring week ending after this trade has finished yet; check back after the current week ends."));
  } else {
    const grid = node("div", "score-grid");
    for (const side of trade.sides) {
      const card = node("div", "score-card");
      card.append(node("p", "score-team", side.team.toUpperCase()));
      const value = node("div", "score-value", formatPoints(side.total_points));
      value.append(node("small", "", " pts"));
      card.append(value, node("p", "score-caption", "from players received · selected weeks"));
      const breakdown = node("ul", "score-breakdown");
      for (const player of side.received) {
        const totals = trade.weeks.map((week) => player.weeks[String(week)]);
        const total = totals.every((points) => points !== null && points !== undefined)
          ? totals.reduce((sum, points) => sum + points, 0)
          : null;
        const item = node("li");
        item.append(node("span", "", player.name), node("strong", "", formatPoints(total)));
        breakdown.append(item);
      }
      card.append(breakdown);
      grid.append(card);
    }
    score.append(grid);
    const table = node("table", "week-table");
    const head = node("thead");
    const headers = node("tr");
    for (const label of ["SCORING WEEK", `${a.team} RECEIVED`, `${b.team} RECEIVED`]) {
      headers.append(node("th", "", label));
    }
    head.append(headers);
    const body = node("tbody");
    for (const week of trade.weeks) {
      const row = node("tr");
      for (const label of [`Week ${week}${week === trade.trade_week ? " (trade week*)" : ""}`, formatPoints(a.weekly_points[String(week)]), formatPoints(b.weekly_points[String(week)])]) {
        row.append(node("td", "", label));
      }
      body.append(row);
    }
    table.append(head, body);
    score.append(table);
    if (trade.trade_week !== null && trade.trade_week !== undefined) {
      score.append(node("p", "method-note", "* Trade-week points may include games played before the deal. This is a hypothetical snapshot, not points the acquiring team necessarily earned."));
    }
  }

  const receipts = $("receipts");
  receipts.replaceChildren();
  if (!trade.league.receipts_enabled) {
    receipts.append(node("p", "empty-state", `Discord receipts are limited to Premier channels. ${trade.league_label} chat is excluded by the project's data scope.`));
  } else if (!trade.receipts.length) {
    receipts.append(node("p", "empty-state", archive.discord_imported
      ? "No Premier-channel messages mentioned these players within 48 hours of this trade."
      : "No Discord messages imported. To add dated Premier League receipts, pass a local JSON export to the refresh script."));
  }
  for (const receipt of trade.receipts) {
    const box = node("div", "receipt");
    const meta = node("div", "receipt-meta");
    meta.append(node("span", "", `${receipt.author} · #${receipt.channel}`), node("span", "", timeFormat.format(new Date(receipt.sent_at))));
    const link = node("a", "", "View message ↗");
    link.href = receipt.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    meta.append(link);
    box.append(node("p", "", receipt.content), meta);
    receipts.append(box);
  }
}

async function load() {
  try {
    const response = await fetch("./data.json", {cache: "no-store"});
    if (!response.ok) throw new Error(`Could not load data.json (HTTP ${response.status}).`);
    archive = normalize(await response.json());
    archive.trades.sort((a, b) => Date.parse(b.traded_at) - Date.parse(a.traded_at));
    const seasons = [...new Set(archive.leagues.map((league) => league.season))];
    $("season-badge").textContent = `${seasons.join(" / ")} SEASON`;
    const summaries = archive.leagues.map((league) => `${league.label} ${league.trades.length} trades · ${league.completed_weeks.length} completed weeks`);
    $("context-bar").textContent = `Lana Straw · trades from ${archive.first_trade_date || "2026-08-30"} · ${summaries.join(" · ")} · refreshed ${timeFormat.format(new Date(archive.generated_at))}`;
    for (const league of archive.leagues) {
      const option = node("option", "", league.label);
      option.value = league.key;
      $("league-filter").append(option);
    }
    $("league-filter").value = "";
    renderTeamOptions();
    $("league-filter").addEventListener("change", () => {
      renderTeamOptions();
      $("brand-league").textContent = `/ ${($("league-filter").selectedOptions[0].value ? $("league-filter").selectedOptions[0].textContent : "All leagues").toUpperCase()}`;
      renderList();
    });
    $("team-filter").addEventListener("change", renderList);
    $("workspace").classList.remove("hidden");
    renderList();
  } catch (error) {
    $("context-bar").textContent = "Snapshot unavailable";
    $("error").textContent = `${error.message} Run generate.py, then serve this folder using python3 -m http.server (opening the file directly cannot fetch JSON).`;
    $("error").classList.remove("hidden");
  }
}

load();
