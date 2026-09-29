// Questions about trade records (after normalizeSnapshot). Pure.

export function archiveTradeId(league, rawId) {
  return `${league.key}-${rawId}`;
}

export function archiveHref(tradeId) {
  return `./archive.html?trade=${encodeURIComponent(tradeId)}`;
}

/** Manager identity across leagues: team IDs repeat between leagues. */
export function teamKey(trade, side) {
  return `${trade.league_key}:${side.team_id}`;
}

export function tradeTeams(trade, separator = " ↔ ") {
  return trade.sides.map((side) => side.team).join(separator);
}

export function playersExchanged(trade) {
  return trade.sides.reduce((sum, side) => sum + side.received.length, 0);
}

/** Filter by league key, transaction week, and manager (teamKey); empty strings mean "any". */
export function filterTrades(trades, {league = "", week = "", team = ""} = {}) {
  return trades.filter((trade) =>
    (!league || trade.league_key === league)
    && (!week || String(trade.transaction_week) === week)
    && (!team || trade.sides.some((side) => teamKey(trade, side) === team)));
}

/**
 * Track the cumulative points leader week by week to find where the lead changed hands.
 * Returns {flips: [{week, to: side}], leader: side | null, incomplete}.
 */
export function leadStory(trade) {
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
