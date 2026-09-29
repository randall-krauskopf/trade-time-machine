// Archive page (archive.html): filterable trade list with a detail panel.
// `?trade=<league>-<id>` selects a trade and is kept in sync with the selection.

import {$, appendOptions, fillSelect, node} from "../lib/dom.js";
import {dateFormat, formatPoints, timeFormat} from "../lib/format.js";
import {addLeagueOptions, fetchSnapshot, showContext, showLoadError, showSelectedLeague, showSeasons} from "../lib/page.js";
import {normalizeSnapshot, tradeContext} from "../lib/snapshot.js";
import {swingChart} from "../lib/swing-chart.js";
import {filterTrades, playersExchanged, teamKey, tradeTeams} from "../lib/trades.js";

const RECONSTRUCTED_NOTE = "ESPN's activity feed is members-only for this league, so this trade was rebuilt from accepted-trade records and roster history. Players who were later dropped or traded again may be missing.";
const TRADE_WEEK_NOTE = "* Trade-week points may include games played before the deal. This is a hypothetical snapshot, not points the acquiring team necessarily earned.";
const TOO_RECENT = "This deal is too recent. No scoring week ending after this trade has finished yet; check back after the current week ends.";

let snapshot = null;
let selectedId = null;

function currentFilters() {
  return {league: $("league-filter").value, week: $("week-filter").value, team: $("team-filter").value};
}

/** Managers that appear in trades matching the league and week filters. */
function renderTeamOptions() {
  const {league, week} = currentFilters();
  const current = $("team-filter").value;
  const showLeague = !league && snapshot.leagues.length > 1;
  const teams = new Map(filterTrades(snapshot.trades, {league, week})
    .flatMap((trade) => trade.sides.map((side) => [teamKey(trade, side), showLeague ? `${side.team} (${trade.league_label})` : side.team])));
  fillSelect($("team-filter"), "All teams", [...teams].sort((a, b) => a[1].localeCompare(b[1])));
  $("team-filter").value = teams.has(current) ? current : "";
}

function selectTrade(id) {
  selectedId = id;
  window.history.replaceState(null, "", `?trade=${encodeURIComponent(id)}`);
  renderList();
}

function tradeListItem(trade) {
  const button = node("button", `trade-item${selectedId === trade.id ? " active" : ""}`);
  button.type = "button";
  button.setAttribute("aria-pressed", String(selectedId === trade.id));
  button.append(
    node("span", "trade-item-date", `${trade.league_label.toUpperCase()} · ${dateFormat.format(new Date(trade.traded_at)).toUpperCase()}`),
    node("span", "trade-item-teams", tradeTeams(trade)),
    node("span", "trade-item-count", `${playersExchanged(trade)} players exchanged`),
  );
  button.addEventListener("click", () => selectTrade(trade.id));
  return button;
}

function renderList() {
  const trades = filterTrades(snapshot.trades, currentFilters());
  $("trade-count").textContent = `${trades.length} DEAL${trades.length === 1 ? "" : "S"}`;
  $("trade-list").replaceChildren();
  if (!trades.length) {
    $("trade-list").append(node("p", "empty-state", "No trades match these filters."));
    $("detail-panel").classList.add("hidden");
    return;
  }
  if (!trades.some((trade) => trade.id === selectedId)) {
    // Prefer a trade with scored weeks so the detail panel has something to show.
    selectedId = (trades.find((trade) => trade.weeks.length) || trades[0]).id;
  }
  window.history.replaceState(null, "", `?trade=${encodeURIComponent(selectedId)}`);
  $("trade-list").append(...trades.map(tradeListItem));
  $("detail-panel").classList.remove("hidden");
  renderDetail(trades.find((trade) => trade.id === selectedId));
}

function receivedCard(side) {
  const card = node("div", "side-card");
  card.append(node("span", "side-label", "RECEIVED BY"), node("h3", "", side.team));
  const list = node("ul", "player-list");
  for (const player of side.received) {
    const item = node("li");
    item.append(node("span", "", player.name), node("span", "", "← IN"));
    list.append(item);
  }
  card.append(list);
  return card;
}

function scoreCard(trade, side) {
  const card = node("div", "score-card");
  card.append(node("p", "score-team", side.team.toUpperCase()));
  const value = node("div", "score-value", formatPoints(side.total_points));
  value.append(node("small", "", " pts"));
  card.append(value, node("p", "score-caption", "from players received · selected weeks"));
  const breakdown = node("ul", "score-breakdown");
  for (const player of side.received) {
    const weekly = trade.weeks.map((week) => player.weeks[String(week)]);
    const total = weekly.every((points) => points !== null && points !== undefined)
      ? weekly.reduce((sum, points) => sum + points, 0)
      : null;
    const item = node("li");
    item.append(node("span", "", player.name), node("strong", "", formatPoints(total)));
    breakdown.append(item);
  }
  card.append(breakdown);
  return card;
}

function weekTable(trade) {
  const [a, b] = trade.sides;
  const table = node("table", "week-table");
  const head = node("thead");
  const headers = node("tr");
  for (const label of ["SCORING WEEK", `${a.team} RECEIVED`, `${b.team} RECEIVED`]) headers.append(node("th", "", label));
  head.append(headers);
  const body = node("tbody");
  for (const week of trade.weeks) {
    const row = node("tr");
    for (const label of [
      `Week ${week}${week === trade.trade_week ? " (trade week*)" : ""}`,
      formatPoints(a.weekly_points[String(week)]),
      formatPoints(b.weekly_points[String(week)]),
    ]) row.append(node("td", "", label));
    body.append(row);
  }
  table.append(head, body);
  return table;
}

function renderDetail(trade) {
  $("detail-heading").textContent = tradeTeams(trade);
  $("trade-date").textContent = timeFormat.format(new Date(trade.traded_at));
  $("detail-league").textContent = `${trade.league_label.toUpperCase()} LEAGUE`;
  $("source-note").classList.toggle("hidden", trade.league.source !== "reconstructed");
  $("source-note").textContent = RECONSTRUCTED_NOTE;
  $("trade-sides").replaceChildren(...trade.sides.map(receivedCard));

  const score = $("score-content");
  score.replaceChildren();
  $("scope-note").textContent = trade.weeks.length ? `WEEKS ${trade.weeks.join(", ")}` : "NO COMPLETED WEEKS YET";
  if (!trade.weeks.length) {
    score.append(node("p", "empty-state", TOO_RECENT));
    return;
  }
  const grid = node("div", "score-grid");
  grid.append(...trade.sides.map((side) => scoreCard(trade, side)));
  score.append(grid, swingChart(trade), weekTable(trade));
  if (trade.trade_week !== null && trade.trade_week !== undefined) {
    score.append(node("p", "method-note", TRADE_WEEK_NOTE));
  }
}

async function main() {
  try {
    snapshot = normalizeSnapshot(await fetchSnapshot());
    showSeasons(snapshot.leagues);
    showContext(tradeContext(snapshot), snapshot.generated_at);
    addLeagueOptions($("league-filter"), snapshot.leagues);
    $("league-filter").value = "";
    const weeks = [...new Set(snapshot.trades.map((trade) => trade.transaction_week))].sort((a, b) => a - b);
    appendOptions($("week-filter"), weeks.map((week) => [String(week), `Week ${week}`]));
    $("week-filter").value = "";
    renderTeamOptions();
    $("league-filter").addEventListener("change", () => {
      renderTeamOptions();
      showSelectedLeague($("league-filter"));
      renderList();
    });
    $("week-filter").addEventListener("change", () => {
      renderTeamOptions();
      renderList();
    });
    $("team-filter").addEventListener("change", renderList);
    const requested = new URLSearchParams(window.location.search).get("trade");
    if (requested && snapshot.trades.some((trade) => trade.id === requested)) selectedId = requested;
    $("workspace").classList.remove("hidden");
    renderList();
  } catch (error) {
    showLoadError(error);
  }
}

main();
