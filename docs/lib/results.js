// Matchup results. Pure: safe to import in Node tests.

/** A tie counts as half a win (and half a loss). */
export const RESULT_WINS = {W: 1, T: 0.5, L: 0};

/**
 * Wins gained by the week's trades: actual result minus the no-trades result.
 * +1 means a loss became a win, −0.5 means a win became a tie, 0 means unchanged.
 */
export function winsGained(row) {
  const actual = RESULT_WINS[row.result];
  const alternate = RESULT_WINS[row.alternate_result];
  if (actual === undefined || alternate === undefined) {
    throw new Error(`Invalid weekly result for ${row.team}, Week ${row.week}.`);
  }
  return actual - alternate;
}

/** Badge for a weekly card: "clutch" when trades improved the result, "oof" when they hurt it. */
export function outcomeClass(row) {
  const change = winsGained(row);
  return change > 0 ? "clutch" : change < 0 ? "oof" : "";
}
