import fs from "node:fs";

import {expect, test} from "@playwright/test";

const snapshot = JSON.parse(fs.readFileSync(new URL("../../docs/data.json", import.meta.url), "utf8"));
const firstLeague = snapshot.leagues.find((league) => league.trades.length);
const deepLinkedTradeId = `${firstLeague.key}-${firstLeague.trades[0].id}`;

const PAGES = {
  "/index.html": "#leaderboards",
  "/archive.html": "#workspace",
  "/weekly.html": "#weekly-moves",
  "/alternate.html": "#alternate-standings",
};

function collectErrors(page) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

for (const [path, section] of Object.entries(PAGES)) {
  test(`${path} renders the snapshot without console errors`, async ({page}) => {
    const errors = collectErrors(page);
    await page.goto(path);
    await expect(page.locator(section)).toBeVisible();
    await expect(page.locator("#error")).toBeHidden();
    await expect(page.locator("#context-bar")).toContainText("refreshed");
    expect(errors).toEqual([]);
  });

  test(`${path} explains an unsupported snapshot version`, async ({page}) => {
    await page.route("**/data.json", (route) => route.fulfill({json: {...snapshot, schema_version: 999}}));
    await page.goto(path);
    await expect(page.locator("#error")).toBeVisible();
    await expect(page.locator("#error")).toContainText("schema version 999");
    await expect(page.locator(section)).toBeHidden();
  });
}

test("archive deep link selects the requested trade", async ({page}) => {
  await page.goto(`/archive.html?trade=${encodeURIComponent(deepLinkedTradeId)}`);
  await expect(page.locator(".trade-item.active")).toHaveCount(1);
  await expect(page.locator(".trade-item.active")).toHaveAttribute("aria-pressed", "true");
  expect(new URL(page.url()).searchParams.get("trade")).toBe(deepLinkedTradeId);
});

test("archive keeps the URL in sync with the selected trade", async ({page}) => {
  await page.goto("/archive.html");
  const second = page.locator(".trade-item").nth(1);
  await second.click();
  await expect(second).toHaveClass(/active/);
  expect(new URL(page.url()).searchParams.get("trade")).toBeTruthy();
});

test("leaderboard charts render for every league", async ({page}) => {
  const errors = collectErrors(page);
  await page.goto("/index.html");
  await expect(page.locator("#trade-charts")).toBeVisible();
  await expect(page.locator("#trade-charts .chart-card")).toHaveCount(3 * snapshot.leagues.length);
  await expect(page.locator(".chart-trades-per-week svg").first()).toBeVisible();
  await expect(page.locator("#chart-note")).toContainText("Trade partners");
  expect(errors).toEqual([]);
});

test("leaderboard charts stay hidden for an unsupported snapshot", async ({page}) => {
  await page.route("**/data.json", (route) => route.fulfill({json: {...snapshot, schema_version: 999}}));
  await page.goto("/index.html");
  await expect(page.locator("#error")).toBeVisible();
  await expect(page.locator("#trade-charts")).toBeHidden();
});

test("leaderboard entries open the archive", async ({page}) => {
  await page.goto("/index.html");
  await page.locator("button.leaderboard-entry").first().click();
  await page.waitForURL(/archive\.html\?trade=/);
  await expect(page.locator(".trade-item.active")).toHaveCount(1);
});

test("weekly deep link filters to one manager-week and order can be reversed", async ({page}) => {
  const moves = snapshot.leagues.flatMap((league) => (league.weekly_roster_moves?.rows || []).map((move) => ({league, move})));
  test.skip(!moves.length, "snapshot has no weekly roster moves");
  const {league, move} = moves[0];
  const team = `${league.key}:${move.team_id}`;
  await page.goto(`/weekly.html?league=${league.key}&team=${encodeURIComponent(team)}&week=${move.week}`);
  await expect(page.locator("#league-filter")).toHaveValue(league.key);
  await expect(page.locator("#team-filter")).toHaveValue(team);
  await expect(page.locator("#week-filter")).toHaveValue(String(move.week));

  await page.goto("/weekly.html");
  await expect(page.locator("#week-order")).toHaveValue("desc");
  await page.selectOption("#week-order", "asc");
  await expect(page.locator("#week-order")).toHaveValue("asc");
});

test("alternate standings follow the league filter", async ({page}) => {
  await page.goto("/alternate.html");
  await page.selectOption("#league-filter", firstLeague.key);
  await expect(page.locator("#alternate-content")).toContainText(firstLeague.label);
});
