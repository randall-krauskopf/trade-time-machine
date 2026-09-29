"use strict";

const $ = (id) => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", year: "numeric", timeZone: "America/Chicago"});
const timeFormat = new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago", timeZoneName: "short"});
const dateKeyFormat = new Intl.DateTimeFormat("en-CA", {year: "numeric", month: "2-digit", day: "2-digit", timeZone: "America/Chicago"});
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

function formatSigned(value, digits = 1) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  return `${number > 0 ? "+" : number < 0 ? "−" : ""}${Math.abs(number).toFixed(digits)}`;
}

function teamKey(trade, side) {
  return `${trade.league_key}:${side.team_id}`;
}

function centralDateKey(timestamp) {
  const parts = Object.fromEntries(dateKeyFormat.formatToParts(new Date(timestamp)).map(({type, value}) => [type, value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function normalize(data) {
  const leagues = Array.isArray(data.leagues)
    ? data.leagues
    : [{...data, key: "premier", label: "Premier", receipts_enabled: true}];
  const firstTradeDate = data.first_trade_date || "2026-08-30";
  for (const league of leagues) {
    if (!Array.isArray(league.trades)) throw new Error(`data.json is missing trades for ${league.label || "a league"}.`);
    league.trades = league.trades.filter((trade) => centralDateKey(trade.traded_at) >= firstTradeDate);
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

function updateBrand() {
  const option = $("league-filter").selectedOptions[0];
  $("brand-league").textContent = `/ ${(option.value ? option.textContent : "All leagues").toUpperCase()}`;
}

function renderTeamOptions() {
  const league = $("league-filter").value;
  const week = $("week-filter").value;
  const current = $("team-filter").value;
  const showLeague = !league && archive.leagues.length > 1;
  const teams = new Map(archive.trades
    .filter((trade) => (!league || trade.league_key === league) && (!week || String(trade.transaction_week) === week))
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

function filteredTrades() {
  const league = $("league-filter").value;
  const week = $("week-filter").value;
  const team = $("team-filter").value;
  return archive.trades.filter((trade) =>
    (!league || trade.league_key === league)
    && (!week || String(trade.transaction_week) === week)
    && (!team || trade.sides.some((side) => teamKey(trade, side) === team)));
}

function selectTrade(id) {
  if (!$("workspace")) {
    window.location.href = `./archive.html?trade=${encodeURIComponent(id)}`;
    return;
  }
  selectedId = id;
  if (!filteredTrades().some((trade) => trade.id === id)) {
    // Leaderboards ignore filters, so clear them when the chosen trade is hidden.
    $("league-filter").value = "";
    $("week-filter").value = "";
    $("team-filter").value = "";
    renderTeamOptions();
    updateBrand();
  }
  renderList();
  $("detail-panel").scrollIntoView({behavior: "smooth", block: "start"});
}

function weeklyHref(league, row, includeWeek = false) {
  const params = new URLSearchParams({
    league: league.key,
    team: `${league.key}:${row.team_id}`,
  });
  if (includeWeek) params.set("week", row.week);
  return `./weekly.html?${params}`;
}

const RESULT_WINS = {W: 1, T: 0.5, L: 0};

function rankWeeklySwings(league) {
  return (league.weekly_roster_moves?.rows || [])
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

function rankWeeklyOutcomes(league, direction) {
  const managers = new Map();
  for (const row of league.weekly_roster_moves?.rows || []) {
    const change = RESULT_WINS[row.result] - RESULT_WINS[row.alternate_result];
    if (!Number.isFinite(change)) throw new Error(`Invalid weekly result for ${row.team}, Week ${row.week}.`);
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
      value: direction > 0
        ? `${manager.wins} ${manager.wins === 1 ? "win" : "wins"}`
        : `${manager.wins} ${manager.wins === 1 ? "loss" : "losses"}`,
      detail: `Week${manager.weeks.length === 1 ? "" : "s"} ${manager.weeks.sort((a, b) => a - b).join(", ")}`,
      href: weeklyHref(league, manager),
    }));
}

function competitionRanks(entries) {
  let previousScore;
  let rank = 0;
  return entries.map((entry, index) => {
    if (!Number.isFinite(entry.rankScore)) throw new Error(`Invalid leaderboard score for ${entry.team || "an entry"}.`);
    if (index === 0 || entry.rankScore !== previousScore) rank = index + 1;
    previousScore = entry.rankScore;
    return {...entry, rank};
  });
}

const LEADERBOARDS = [
  {
    title: "Most active traders",
    caption: "Managers with the most completed deals.",
    rank(trades) {
      const counts = new Map();
      for (const trade of trades) {
        for (const side of trade.sides) counts.set(side.team, (counts.get(side.team) || 0) + 1);
      }
      return [...counts.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([team, count]) => ({
          team,
          rankScore: count,
          value: `${count} trade${count === 1 ? "" : "s"}`,
        }));
    },
  },
  {
    title: "Wins Traded For",
    caption: "Weekly trade bundles that improved matchup results.",
    rank(trades, league) {
      return rankWeeklyOutcomes(league, 1);
    },
  },
  {
    title: "Wins Traded Away",
    caption: "Weekly trade bundles that worsened matchup results.",
    rank(trades, league) {
      return rankWeeklyOutcomes(league, -1);
    },
  },
  {
    title: "Most players exchanged",
    caption: "Blockbusters by total players changing hands.",
    rank(trades) {
      return trades
        .map((trade) => ({trade, count: trade.sides.reduce((sum, side) => sum + side.received.length, 0)}))
        .sort((a, b) => b.count - a.count || Date.parse(b.trade.traded_at) - Date.parse(a.trade.traded_at))
        .map(({trade, count}) => ({
          trade,
          rankScore: count,
          value: `${count} players`,
          detail: trade.sides.map((side) => `${side.received.length} to ${side.team}`).join(" · "),
        }));
    },
  },
  {
    title: "Biggest Roster Swings",
    caption: "Biggest weekly matchup point swings, for better or worse.",
    rank(trades, league) {
      return rankWeeklySwings(league);
    },
  },
];

function renderLeaderboards() {
  const trades = archive.trades;
  const content = $("leaderboard-content");
  content.replaceChildren();
  const groups = archive.leagues.length === 1
    ? [{label: null, league: archive.leagues[0], trades}]
    : archive.leagues.map((league) => ({label: league.label, league, trades: trades.filter((trade) => trade.league_key === league.key)}));
  for (const group of groups) {
    const row = node("div", "leaderboard-row");
    if (group.label) row.append(node("p", "leaderboard-league", `${group.label.toUpperCase()} LEAGUE`));
    const grid = node("div", "leaderboard-grid");
    for (const board of LEADERBOARDS) {
      const card = node("article", "leaderboard-card");
      card.append(node("h3", "", board.title), node("p", "leaderboard-caption", board.caption));
      const entries = competitionRanks(board.rank(group.trades, group.league)).slice(0, 3);
      if (!entries.length) {
        card.append(node("p", "leaderboard-empty", board.title.startsWith("Wins Traded") ? "No results changed yet." : board.title === "Biggest Roster Swings" ? "No weekly point swings yet." : "No eligible trades yet."));
      } else {
        const list = node("ol", "leaderboard-list");
        for (const entry of entries) {
          const item = node("li");
          const button = node(entry.href ? "a" : entry.trade ? "button" : "div", `leaderboard-entry${entry.trade && entry.trade.id === selectedId ? " active" : ""}${entry.trade || entry.href ? "" : " static"}`);
          button.dataset.rank = entry.rank;
          if (entry.rank === 1) button.classList.add("rank-first");
          if (entry.href) button.href = entry.href;
          if (entry.trade) {
            button.type = "button";
            button.setAttribute("aria-label", `${entry.trade.sides.map((side) => side.team).join(" and ")}, ${entry.value}. Open trade.`);
          }
          const text = node("span", "leaderboard-text");
          text.append(node("span", "leaderboard-teams", entry.trade ? entry.trade.sides.map((side) => side.team).join(" ↔ ") : entry.team));
          const detail = entry.trade ? `${dateFormat.format(new Date(entry.trade.traded_at))} · ${entry.detail}` : entry.detail;
          if (detail) text.append(node("span", "leaderboard-detail", detail));
          button.append(text, node("strong", "leaderboard-value", entry.value));
          if (entry.trade) button.addEventListener("click", () => selectTrade(entry.trade.id));
          item.append(button);
          list.append(item);
        }
        card.append(list);
      }
      grid.append(card);
    }
    row.append(grid);
    content.append(row);
  }
  const notes = ["Wins Traded For/Away compare actual matchup results with the no-weekly-trades scenario, bundled by manager and week (ties count as half a win or loss). Unchanged results do not count. Biggest Roster Swings ranks the largest absolute manager-week point swings (actual minus no-weekly-trades), including swings that did not change the result. Not verdicts."];
  if (trades.some((trade) => trade.league.source === "reconstructed")) {
    notes.push("Champeens trades are reconstructed from roster history and may omit players who were later dropped or re-traded.");
  }
  $("leaderboard-note").textContent = notes.join(" ");
}

function renderList() {
  const trades = filteredTrades();
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
  window.history.replaceState(null, "", `?trade=${encodeURIComponent(selectedId)}`);
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
      window.history.replaceState(null, "", `?trade=${encodeURIComponent(trade.id)}`);
      renderList();
    });
    $("trade-list").append(button);
  }
  $("detail-panel").classList.remove("hidden");
  renderDetail(trades.find((trade) => trade.id === selectedId));
}

const SVG_NS = "http://www.w3.org/2000/svg";

function svg(tag, attributes = {}, text) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  if (text !== undefined) element.textContent = String(text);
  return element;
}

function leadStory(trade) {
  // Track the cumulative leader to find weeks where the lead changed hands.
  const [a, b] = trade.sides;
  let totals = [0, 0];
  let leader = null;
  const flips = [];
  for (const week of trade.weeks) {
    const points = [a, b].map((side) => side.weekly_points[String(week)]);
    if (points.some((value) => value === null || value === undefined)) return {flips, leader: null, incomplete: true};
    totals = totals.map((total, index) => total + points[index]);
    const current = totals[0] === totals[1] ? null : totals[0] > totals[1] ? 0 : 1;
    if (current !== null && leader !== null && current !== leader) flips.push({week, to: trade.sides[current]});
    if (current !== null) leader = current;
  }
  return {flips, leader: leader === null ? null : trade.sides[leader], incomplete: false};
}

function swingChart(trade) {
  const [a, b] = trade.sides;
  const weeks = trade.weeks;
  const values = weeks.flatMap((week) => [a, b].map((side) => side.weekly_points[String(week)] ?? 0));
  const step = 10;
  const max = Math.max(step, Math.ceil(Math.max(...values) / step) * step + step);
  const width = 640, height = 260, left = 46, right = 12, top = 26, bottom = 44;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const y = (value) => top + plotHeight - (value / max) * plotHeight;
  const story = leadStory(trade);

  const figure = node("figure", "swing-chart");
  const legend = node("div", "chart-legend");
  for (const [index, side] of [a, b].entries()) {
    const key = node("span", `chart-key side-${index}`);
    key.append(node("i"), node("span", "", side.team));
    legend.append(key);
  }
  const label = `Weekly points received: ${weeks.map((week) => `Week ${week}, ${a.team} ${formatPoints(a.weekly_points[String(week)])}, ${b.team} ${formatPoints(b.weekly_points[String(week)])}`).join("; ")}.`;
  const chart = svg("svg", {viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": label, class: "chart-svg"});
  for (let tick = 0; tick <= max; tick += max / 4) {
    chart.append(
      svg("line", {x1: left, x2: width - right, y1: y(tick), y2: y(tick), class: "chart-grid"}),
      svg("text", {x: left - 8, y: y(tick) + 5, class: "chart-axis", "text-anchor": "end"}, Math.round(tick))
    );
  }
  const group = plotWidth / weeks.length;
  const barWidth = Math.min(56, group * 0.3);
  const flipWeeks = new Set(story.flips.map((flip) => flip.week));
  weeks.forEach((week, index) => {
    const center = left + group * index + group / 2;
    if (week === trade.trade_week) {
      chart.append(svg("rect", {x: left + group * index + 4, y: top, width: group - 8, height: plotHeight, class: "chart-trade-week"}));
    }
    [a, b].forEach((side, sideIndex) => {
      const value = side.weekly_points[String(week)];
      const x = center + (sideIndex === 0 ? -barWidth - 3 : 3);
      if (value === null || value === undefined) {
        chart.append(svg("text", {x: x + barWidth / 2, y: y(0) - 6, class: "chart-value", "text-anchor": "middle"}, "—"));
        return;
      }
      const bar = svg("rect", {x, y: y(value), width: barWidth, height: Math.max(y(0) - y(value), 1), rx: 3, class: `chart-bar side-${sideIndex}`});
      bar.append(svg("title", {}, `${side.team}, Week ${week}: ${formatPoints(value)} pts`));
      chart.append(bar, svg("text", {x: x + barWidth / 2, y: y(value) - 6, class: "chart-value", "text-anchor": "middle"}, formatPoints(value)));
    });
    const weekLabel = `Week ${week}${week === trade.trade_week ? "*" : ""}${flipWeeks.has(week) ? " ⇄" : ""}`;
    chart.append(svg("text", {x: center, y: height - 16, class: `chart-axis chart-week${flipWeeks.has(week) ? " chart-flip" : ""}`, "text-anchor": "middle"}, weekLabel));
  });
  chart.append(svg("line", {x1: left, x2: width - right, y1: y(0), y2: y(0), class: "chart-baseline"}));

  let summary;
  if (story.incomplete) summary = "Some weekly scores are unavailable, so the lead can't be tracked.";
  else if (story.flips.length) summary = story.flips.map((flip) => `Lead flipped to ${flip.to.team} in Week ${flip.week}.`).join(" ") + ` ${story.leader.team} leads now.`;
  else if (story.leader) summary = weeks.length === 1 ? `${story.leader.team} leads after one week.` : `${story.leader.team} has led every week.`;
  else summary = "Dead even so far.";
  const markers = [
    story.flips.length ? "⇄ = cumulative lead changed" : null,
    trade.trade_week !== null && trade.trade_week !== undefined ? "* = trade week (shaded)" : null,
  ].filter(Boolean);
  const caption = node("figcaption", "chart-caption", summary);
  if (markers.length) caption.append(node("span", "chart-markers", markers.join(" · ")));
  figure.append(legend, chart, caption);
  return figure;
}

function renderDetail(trade) {
  const [a, b] = trade.sides;
  $("detail-heading").textContent = `${a.team} ↔ ${b.team}`;
  $("trade-date").textContent = timeFormat.format(new Date(trade.traded_at));
  $("detail-league").textContent = `${trade.league_label.toUpperCase()} LEAGUE`;
  $("source-note").classList.toggle("hidden", trade.league.source !== "reconstructed");
  $("source-note").textContent = "ESPN's activity feed is members-only for this league, so this trade was rebuilt from accepted-trade records and roster history. Players who were later dropped or traded again may be missing.";
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
    score.append(grid, swingChart(trade));
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
    if ($("workspace")) {
      for (const league of archive.leagues) {
        const option = node("option", "", league.label);
        option.value = league.key;
        $("league-filter").append(option);
      }
      $("league-filter").value = "";
      const weeks = [...new Set(archive.trades.map((trade) => trade.transaction_week))].sort((a, b) => a - b);
      for (const week of weeks) {
        const option = node("option", "", `Week ${week}`);
        option.value = String(week);
        $("week-filter").append(option);
      }
      $("week-filter").value = "";
      renderTeamOptions();
      $("league-filter").addEventListener("change", () => {
        renderTeamOptions();
        updateBrand();
        renderList();
      });
      $("week-filter").addEventListener("change", () => {
        renderTeamOptions();
        renderList();
      });
      $("team-filter").addEventListener("change", renderList);
      const requestedTrade = new URLSearchParams(window.location.search).get("trade");
      if (requestedTrade && archive.trades.some((trade) => trade.id === requestedTrade)) selectedId = requestedTrade;
      $("workspace").classList.remove("hidden");
      renderList();
    }
    if ($("leaderboards")) {
      $("leaderboards").classList.remove("hidden");
      renderLeaderboards();
    }
  } catch (error) {
    $("context-bar").textContent = "Snapshot unavailable";
    $("error").textContent = `${error.message} Run generate.py, then serve this folder using python3 -m http.server (opening the file directly cannot fetch JSON).`;
    $("error").classList.remove("hidden");
  }
}

load();
