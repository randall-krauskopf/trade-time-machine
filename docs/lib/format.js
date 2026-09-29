// Number, date, and wording helpers. Pure: safe to import in Node tests.

/** All dates are shown in league time. */
export const LEAGUE_TIME_ZONE = "America/Chicago";

export const dateFormat = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", year: "numeric", timeZone: LEAGUE_TIME_ZONE,
});

export const timeFormat = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  timeZone: LEAGUE_TIME_ZONE, timeZoneName: "short",
});

const dateKeyFormat = new Intl.DateTimeFormat("en-CA", {
  year: "numeric", month: "2-digit", day: "2-digit", timeZone: LEAGUE_TIME_ZONE,
});

/** "YYYY-MM-DD" in league time, comparable with first_trade_date. */
export function leagueDateKey(timestamp) {
  const parts = Object.fromEntries(dateKeyFormat.formatToParts(new Date(timestamp)).map(({type, value}) => [type, value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

/** Two decimals, or an em dash when the score is unknown. */
export function formatPoints(value) {
  return value === null || value === undefined ? "—" : Number(value).toFixed(2);
}

/** Signed number with a typographic minus, e.g. "+3.5" or "−12.00". */
export function formatSigned(value, digits = 1) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  return `${number > 0 ? "+" : number < 0 ? "−" : ""}${Math.abs(number).toFixed(digits)}`;
}

/** "1 trade", "2 trades"; pass the plural for irregular words ("loss" -> "losses"). */
export function countOf(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}
