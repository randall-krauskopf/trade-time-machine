// Leaderboards page (index.html).

import {$, node} from "../lib/dom.js";
import {dateFormat} from "../lib/format.js";
import {leagueGroups, leagueRow, omittedWeeks} from "../lib/league-sections.js";
import {fetchSnapshot, showContext, showLoadError, showSeasons} from "../lib/page.js";
import {normalizeSnapshot, tradeContext} from "../lib/snapshot.js";
import {LEADERBOARD_TOP_N, LEADERBOARDS, competitionRanks} from "../lib/rankings.js";
import {archiveHref, tradeTeams} from "../lib/trades.js";

const METHOD_NOTE = "Wins Traded For/Away compare actual matchup results with the no-weekly-trades scenario, bundled by manager and week (ties count as half a win or loss). Unchanged results do not count. Biggest Roster Swings ranks the largest absolute manager-week point swings (actual minus no-weekly-trades), including swings that did not change the result. Most Traded Player counts players moved in two or more deals. Left on the Bench is the best possible lineup from that week's roster (IR excluded) minus the starters' actual points. Not verdicts.";
const RECONSTRUCTED_NOTE = "Champeens trades are reconstructed from roster history and may omit players who were later dropped or re-traded.";

function leaderboardEntry(entry) {
  const linked = entry.trade || entry.href;
  const element = node(entry.href ? "a" : entry.trade ? "button" : "div", `leaderboard-entry${linked ? "" : " static"}`);
  element.dataset.rank = entry.rank;
  if (entry.rank === 1) element.classList.add("rank-first");
  if (entry.href) element.href = entry.href;
  if (entry.trade) {
    element.type = "button";
    element.setAttribute("aria-label", `${tradeTeams(entry.trade, " and ")}, ${entry.value}. Open trade.`);
    element.addEventListener("click", () => {
      window.location.href = archiveHref(entry.trade.id);
    });
  }
  const text = node("span", "leaderboard-text");
  text.append(node("span", "leaderboard-teams", entry.trade ? tradeTeams(entry.trade) : entry.team));
  const detail = entry.trade ? `${dateFormat.format(new Date(entry.trade.traded_at))} · ${entry.detail}` : entry.detail;
  if (detail) text.append(node("span", "leaderboard-detail", detail));
  element.append(text, node("strong", "leaderboard-value", entry.value));
  return element;
}

function leaderboardCard(board, trades, league) {
  const card = node("article", "leaderboard-card");
  card.append(node("h3", "", board.title), node("p", "leaderboard-caption", board.caption));
  const entries = competitionRanks(board.rank(trades, league)).slice(0, LEADERBOARD_TOP_N);
  if (!entries.length) {
    card.append(node("p", "leaderboard-empty", board.empty));
    return card;
  }
  const list = node("ol", "leaderboard-list");
  for (const entry of entries) {
    const item = node("li");
    item.append(leaderboardEntry(entry));
    list.append(item);
  }
  card.append(list);
  return card;
}

function renderLeaderboards(snapshot) {
  const content = $("leaderboard-content");
  content.replaceChildren();
  for (const group of leagueGroups(snapshot)) {
    const grid = node("div", "leaderboard-grid");
    for (const board of LEADERBOARDS) grid.append(leaderboardCard(board, group.trades, group.league));
    content.append(leagueRow(group, "leaderboard-row", grid));
  }
  const notes = [METHOD_NOTE];
  const omitted = omittedWeeks(snapshot);
  if (omitted) notes.push(`${omitted} manager-week outcomes were excluded because historical lineup inputs could not be verified; weekly outcome rankings use only the remaining rows.`);
  if (snapshot.trades.some((trade) => trade.league.source === "reconstructed")) notes.push(RECONSTRUCTED_NOTE);
  $("leaderboard-note").textContent = notes.join(" ");
}

async function main() {
  try {
    const snapshot = normalizeSnapshot(await fetchSnapshot());
    showSeasons(snapshot.leagues);
    showContext(tradeContext(snapshot), snapshot.generated_at);
    $("leaderboards").classList.remove("hidden");
    renderLeaderboards(snapshot);
  } catch (error) {
    showLoadError(error);
  }
}

main();
