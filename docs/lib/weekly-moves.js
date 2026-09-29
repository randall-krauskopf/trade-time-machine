// Weekly Moves rows (one manager's bundled trades in one game week). Pure.

export function weeklyRows(league) {
  return league.weekly_roster_moves?.rows || [];
}

/** Newest week first by default; within a week, busiest traders first, then by name. */
export function sortWeeklyRows(rows, direction = "desc") {
  if (!["asc", "desc"].includes(direction)) throw new Error(`Invalid week order: ${direction}.`);
  const weekDirection = direction === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => weekDirection * (a.week - b.week)
    || b.trade_count - a.trade_count || a.team.localeCompare(b.team));
}

/** Link to the Weekly Moves page filtered to a manager (and optionally one week). */
export function weeklyHref(league, row, includeWeek = false) {
  const params = new URLSearchParams({
    league: league.key,
    team: `${league.key}:${row.team_id}`,
  });
  if (includeWeek) params.set("week", row.week);
  return `./weekly.html?${params}`;
}

/** "SLOT: Player over Benched" summary of the no-trades lineup changes. */
export function describeReplacements(replacements) {
  return replacements.map((change) => change.name
    ? `${change.slot}: ${change.name}${change.replaced ? ` over ${change.replaced}` : ""}`
    : `${change.slot}: no eligible player`).join(" · ");
}
