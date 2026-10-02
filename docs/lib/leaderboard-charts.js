// Leaderboard page charts. Builds DOM from the pure data in charts.js.

import {netWeeklySwing, tradePartners, tradesPerWeek} from "./charts.js";
import {node, svg} from "./dom.js";
import {countOf, formatSigned} from "./format.js";
import {weeklyHref} from "./weekly-moves.js";

const LINE = {width: 640, height: 250, left: 42, right: 16, top: 30, bottom: 42};

function chartCard(title, caption, className = "") {
  const card = node("article", `chart-card ${className}`.trim());
  card.append(node("h3", "", title), node("p", "leaderboard-caption", caption));
  return card;
}

function summary(text) {
  return node("p", "chart-summary", text);
}

function joinNames(names) {
  return names.length <= 2 ? names.join(" and ") : `${names.slice(0, -1).join(", ")}, and ${names.at(-1)}`;
}

export function tradesPerWeekChart(trades, league) {
  const card = chartCard("Trades per week", "Completed deals in each Tuesday-to-Tuesday game week.", "chart-trades-per-week");
  const weeks = tradesPerWeek(trades, league);
  if (!trades.length) {
    card.append(node("p", "leaderboard-empty", "No eligible trades yet."));
    return card;
  }
  const max = Math.max(...weeks.map((week) => week.count));
  const step = Math.max(1, Math.ceil(max / 4));
  const top = step * Math.ceil(max / step);
  const plotWidth = LINE.width - LINE.left - LINE.right;
  const plotHeight = LINE.height - LINE.top - LINE.bottom;
  const x = (index) => LINE.left + (weeks.length === 1 ? plotWidth / 2 : (plotWidth * index) / (weeks.length - 1));
  const y = (count) => LINE.top + plotHeight - (count / top) * plotHeight;
  const label = `Trades per week: ${weeks.map((week) => `Week ${week.week}${week.complete ? "" : " (in progress)"}, ${countOf(week.count, "trade")}`).join("; ")}.`;
  const chart = svg("svg", {viewBox: `0 0 ${LINE.width} ${LINE.height}`, role: "img", "aria-label": label, class: "chart-svg"});
  for (let tick = 0; tick <= top; tick += step) {
    chart.append(
      svg("line", {x1: LINE.left, x2: LINE.width - LINE.right, y1: y(tick), y2: y(tick), class: tick ? "chart-grid" : "chart-baseline"}),
      svg("text", {x: LINE.left - 10, y: y(tick) + 5, class: "chart-axis", "text-anchor": "end"}, tick),
    );
  }
  const points = weeks.map((week, index) => `${x(index)},${y(week.count)}`);
  chart.append(
    svg("path", {d: `M${x(0)},${y(0)} L${points.join(" L")} L${x(weeks.length - 1)},${y(0)} Z`, class: "chart-area"}),
    svg("polyline", {points: points.join(" "), class: "chart-line"}),
  );
  const labelEvery = Math.ceil(weeks.length / 12);
  weeks.forEach((week, index) => {
    const point = svg("circle", {cx: x(index), cy: y(week.count), r: 5, class: `chart-point${week.complete ? "" : " pending"}`});
    point.append(svg("title", {}, `Week ${week.week}${week.complete ? "" : " (in progress)"}: ${countOf(week.count, "trade")}`));
    chart.append(point);
    if (week.count) chart.append(svg("text", {x: x(index), y: y(week.count) - 11, class: "chart-value", "text-anchor": "middle"}, week.count));
    if (index % labelEvery === 0 || index === weeks.length - 1) {
      chart.append(svg("text", {x: x(index), y: LINE.height - 14, class: "chart-axis chart-week", "text-anchor": "middle"}, `W${week.week}${week.complete ? "" : "*"}`));
    }
  });
  const busiest = weeks.filter((week) => week.count === max).map((week) => `Week ${week.week}`);
  const text = `Busiest: ${joinNames(busiest)} · ${countOf(max, "trade")}.`;
  const figure = node("figure", "chart-figure");
  const caption = node("figcaption", "chart-summary", text);
  if (weeks.some((week) => !week.complete)) caption.append(node("span", "chart-markers", "* = week in progress"));
  figure.append(chart, caption);
  card.append(figure);
  return card;
}

function barRow({label, detail, value, size, negative = false, href}) {
  const row = node(href ? "a" : "div", `bar-row${negative ? " negative" : ""}`);
  if (href) row.href = href;
  const text = node("span", "bar-label");
  text.append(node("span", "leaderboard-teams", label));
  if (detail) text.append(node("span", "leaderboard-detail", detail));
  const track = node("span", "bar-track");
  const fill = node("span", "bar-fill");
  fill.style.setProperty("--size", `${Math.max(0, Math.min(100, size))}%`);
  track.append(fill);
  row.append(text, track, node("strong", "bar-value", value));
  return row;
}

export function tradePartnersChart(trades, league) {
  const card = chartCard("Trade partners", "How often each pair of managers has dealt with each other.", "chart-partners");
  const {teams, counts, max, topPairs} = tradePartners(trades, league);
  if (!max) {
    card.append(node("p", "leaderboard-empty", "No eligible trades yet."));
    return card;
  }
  const scroll = node("div", "heatmap-scroll");
  const table = node("table", "heatmap");
  table.append(node("caption", "", "Trades between each pair of managers. Rows and columns list the same managers."));
  const head = node("tr");
  head.append(node("td", "heatmap-corner"));
  teams.forEach((team, index) => {
    const header = node("th", "", index + 1);
    header.scope = "col";
    header.title = team.team;
    header.setAttribute("aria-label", team.team);
    head.append(header);
  });
  const thead = node("thead");
  thead.append(head);
  const tbody = node("tbody");
  teams.forEach((team, a) => {
    const row = node("tr");
    const header = node("th", "heatmap-team");
    header.scope = "row";
    header.append(node("span", "heatmap-index", a + 1), node("span", "", team.team));
    row.append(header);
    teams.forEach((partner, b) => {
      const count = counts[a][b];
      const cell = node("td", a === b ? "heatmap-self" : count ? "heatmap-hit" : "", a === b ? "·" : count || "");
      if (a !== b) {
        cell.style.setProperty("--heat", String(count / max));
        cell.title = `${team.team} ↔ ${partner.team}: ${countOf(count, "trade")}`;
        if (!count) cell.setAttribute("aria-label", "0");
      }
      row.append(cell);
    });
    tbody.append(row);
  });
  table.append(thead, tbody);
  scroll.append(table);
  const shown = topPairs.slice(0, 3).map((pair) => pair.teams.map((team) => team.team).join(" ↔ "));
  const more = topPairs.length > shown.length ? ` (+${topPairs.length - shown.length} more)` : "";
  const label = topPairs.length === 1 ? "Most frequent partners" : "Most frequent pairs";
  card.append(scroll, summary(`${label}: ${shown.join("; ")}${more} · ${countOf(max, "trade")}.`));
  return card;
}

export function netWeeklySwingChart(league) {
  const card = chartCard("Net roster swing", "Total weekly points gained or lost versus the no-weekly-trades lineup.", "chart-net-swing");
  const managers = netWeeklySwing(league);
  if (!managers.length) {
    card.append(node("p", "leaderboard-empty", "No weekly outcomes yet."));
    return card;
  }
  const max = Math.max(...managers.map((manager) => Math.abs(manager.net)), 1);
  const list = node("div", "bar-chart diverging");
  for (const manager of managers) {
    list.append(barRow({
      label: manager.team,
      detail: countOf(manager.weeks, "manager-week"),
      value: `${formatSigned(manager.net, 1)} pts`,
      size: (Math.abs(manager.net) / max) * 100,
      negative: manager.net < 0,
      href: weeklyHref(league, manager),
    }));
  }
  const best = managers[0];
  const worst = managers.at(-1);
  const parts = [best.net > 0 ? `Biggest boost: ${best.team} (${formatSigned(best.net, 1)})` : null,
    worst.net < 0 ? `Biggest drag: ${worst.team} (${formatSigned(worst.net, 1)})` : null].filter(Boolean);
  card.append(list, summary(parts.length ? `${parts.join(" · ")}.` : "No net point swing yet."));
  return card;
}

/** All three charts for one league, in display order. */
export function leagueCharts(trades, league) {
  const grid = node("div", "chart-grid-layout");
  grid.append(
    tradesPerWeekChart(trades, league),
    tradePartnersChart(trades, league),
    netWeeklySwingChart(league),
  );
  return grid;
}
