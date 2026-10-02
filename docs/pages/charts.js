// Trade charts page (charts.html).

import {$} from "../lib/dom.js";
import {leagueCharts} from "../lib/leaderboard-charts.js";
import {leagueGroups, leagueRow, omittedWeeks} from "../lib/league-sections.js";
import {fetchSnapshot, showContext, showLoadError, showSeasons} from "../lib/page.js";
import {normalizeSnapshot, tradeContext} from "../lib/snapshot.js";

const CHART_NOTE = "Trades per week counts completed deals by game week. Trade partners counts deals between each pair of managers. Net roster swing sums each manager's weekly point swing (actual minus the no-weekly-trades lineup) across verified manager-weeks.";

function renderCharts(snapshot) {
  const content = $("chart-content");
  content.replaceChildren();
  for (const group of leagueGroups(snapshot)) {
    content.append(leagueRow(group, "leaderboard-row chart-row", leagueCharts(group.trades, group.league)));
  }
  const notes = [CHART_NOTE];
  const omitted = omittedWeeks(snapshot);
  if (omitted) notes.push(`${omitted} manager-week outcomes with unverifiable lineup inputs are excluded from net roster swing.`);
  $("chart-note").textContent = notes.join(" ");
}

async function main() {
  try {
    const snapshot = normalizeSnapshot(await fetchSnapshot());
    showSeasons(snapshot.leagues);
    showContext(tradeContext(snapshot), snapshot.generated_at);
    renderCharts(snapshot);
    $("trade-charts").classList.remove("hidden");
  } catch (error) {
    showLoadError(error);
  }
}

main();
