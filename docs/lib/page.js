// Page chrome shared by every page: loading data.json, header badges, errors.

import {$, appendOptions} from "./dom.js";
import {timeFormat} from "./format.js";
import {assertSupportedSnapshot} from "./snapshot.js";

export async function fetchSnapshot() {
  const response = await fetch("./data.json", {cache: "no-store"});
  if (!response.ok) throw new Error(`Could not load data.json (HTTP ${response.status}).`);
  return assertSupportedSnapshot(await response.json());
}

/** "2026 SEASON" (or "2025 / 2026 SEASON" if leagues ever differ). */
export function showSeasons(leagues) {
  const seasons = [...new Set(leagues.map((league) => league.season))];
  $("season-badge").textContent = `${seasons.join(" / ")} SEASON`;
}

/** Context bar: "Lana Straw · <parts> · refreshed <time>". */
export function showContext(parts, generatedAt) {
  $("context-bar").textContent = ["Lana Straw", ...parts, `refreshed ${timeFormat.format(new Date(generatedAt))}`].join(" · ");
}

export function addLeagueOptions(select, leagues) {
  appendOptions(select, leagues.map((league) => [league.key, league.label]));
}

/** Mirror the league filter in the masthead ("/ PREMIER" or "/ ALL LEAGUES"). */
export function showSelectedLeague(select) {
  const option = select.selectedOptions[0];
  $("brand-league").textContent = `/ ${(select.value ? option.textContent : "All leagues").toUpperCase()}`;
}

export function showLoadError(error) {
  $("context-bar").textContent = "Snapshot unavailable";
  $("error").textContent = `${error.message} Run generate.py, then serve this folder using python3 -m http.server (opening the file directly cannot fetch JSON).`;
  $("error").classList.remove("hidden");
}
