import fs from "node:fs";

import {expect, test} from "@playwright/test";

const snapshot = JSON.parse(fs.readFileSync(new URL("../../docs/data.json", import.meta.url), "utf8"));
const firstLeague = snapshot.leagues.find((league) => league.trades.length);
const deepLinkedTradeId = `${firstLeague.key}-${firstLeague.trades[0].id}`;

const PAGES = {
  "/index.html": "#leaderboards",
  "/charts.html": "#trade-charts",
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
    const nav = page.locator(".site-nav a");
    await expect(nav).toHaveText(["Leaderboards", "Trade Charts", "Weekly Moves", "Archive", "Alternate Universe"]);
    await expect(nav.nth(1)).toHaveAttribute("href", "./charts.html");
    const current = page.locator('.site-nav a[aria-current="page"]');
    await expect(current).toHaveCount(1);
    await expect(current).toHaveAttribute("href", path === "/index.html" ? "./" : `.${path}`);
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

test("trade charts render for every league on their own page", async ({page}) => {
  const errors = collectErrors(page);
  await page.goto("/charts.html");
  await expect(page.locator("#trade-charts")).toBeVisible();
  await expect(page.locator("#trade-charts .chart-card")).toHaveCount(3 * snapshot.leagues.length);
  await expect(page.locator(".chart-trades-per-week svg").first()).toBeVisible();
  await expect(page.locator("#chart-note")).toContainText("Trade partners");
  expect(errors).toEqual([]);
});

test("trade partners shares the top row and net roster swing spans the row below", async ({page}) => {
  await page.setViewportSize({width: 1400, height: 1000});
  await page.goto("/charts.html");
  await expect(page.locator("#trade-charts")).toBeVisible();
  for (const grid of await page.locator(".chart-grid-layout").all()) {
    await expect(grid.locator(".chart-card h3")).toHaveText(["Trades per week", "Trade partners", "Net roster swing"]);
    const trades = await grid.locator(".chart-trades-per-week").boundingBox();
    const partners = await grid.locator(".chart-partners").boundingBox();
    const swing = await grid.locator(".chart-net-swing").boundingBox();
    expect(partners.y).toBe(trades.y);
    expect(partners.x).toBeGreaterThan(trades.x);
    expect(swing.y).toBeGreaterThan(trades.y + trades.height);
    expect(swing.x).toBe(trades.x);
    expect(swing.width).toBeCloseTo(partners.x + partners.width - trades.x, 0);
  }
  await page.setViewportSize({width: 375, height: 900});
  const grid = page.locator(".chart-grid-layout").first();
  const trades = await grid.locator(".chart-trades-per-week").boundingBox();
  const partners = await grid.locator(".chart-partners").boundingBox();
  const swing = await grid.locator(".chart-net-swing").boundingBox();
  expect(partners.y).toBeGreaterThan(trades.y + trades.height);
  expect(swing.y).toBeGreaterThan(partners.y + partners.height);
});

test("leaderboards link to charts without rendering them", async ({page}) => {
  await page.goto("/index.html");
  await expect(page.locator("#leaderboards")).toBeVisible();
  await expect(page.locator("#trade-charts")).toHaveCount(0);
  await page.getByRole("link", {name: "Trade Charts", exact: true}).click();
  await page.waitForURL("**/charts.html");
  await expect(page.locator("#trade-charts")).toBeVisible();
});

test("leaderboard league sections collapse and expand", async ({page}) => {
  test.skip(snapshot.leagues.length < 2, "Collapsible sections appear only with multiple leagues.");
  await page.goto("/index.html");
  const section = page.locator("#leaderboard-content details.collapsible").first();
  const grid = section.locator(".leaderboard-grid");
  await expect(page.locator("#leaderboard-content details.collapsible")).toHaveCount(snapshot.leagues.length);
  await expect(grid).toBeVisible();
  await section.locator("summary").click();
  await expect(grid).toBeHidden();
  await section.locator("summary").click();
  await expect(grid).toBeVisible();
});

test("chart league sections collapse with the keyboard and expand independently", async ({page}) => {
  test.skip(snapshot.leagues.length < 2, "Collapsible sections appear only with multiple leagues.");
  await page.goto("/charts.html");
  const sections = page.locator("#chart-content details.collapsible");
  await expect(sections).toHaveCount(snapshot.leagues.length);
  const cards = sections.first().locator(".chart-card");
  await expect(cards.first()).toBeVisible();
  await sections.first().locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(cards.first()).toBeHidden();
  await expect(sections.nth(1).locator(".chart-card").first()).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(cards.first()).toBeVisible();
});

test("charts render a single league without a collapsible heading", async ({page}) => {
  await page.route("**/data.json", (route) => route.fulfill({json: {...snapshot, leagues: [firstLeague]}}));
  await page.goto("/charts.html");
  await expect(page.locator("#trade-charts")).toBeVisible();
  await expect(page.locator(".chart-card")).toHaveCount(3);
  await expect(page.locator("#chart-content details")).toHaveCount(0);
});

test("charts navigation fits narrow screens", async ({page}) => {
  for (const width of [320, 768, 900, 901, 1024, 1400]) {
    await page.setViewportSize({width, height: 900});
    await page.goto("/charts.html");
    await expect(page.locator("#trade-charts")).toBeVisible();
    for (const link of await page.locator(".site-nav a").all()) {
      const bounds = await link.boundingBox();
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    }
  }
});

test("biggest winning margins render for each league", async ({page}) => {
  await page.goto("/index.html");
  const cards = page.locator(".leaderboard-card").filter({has: page.getByRole("heading", {name: "Biggest Margin of Victory", exact: true})});
  await expect(cards).toHaveCount(snapshot.leagues.length);
  for (let index = 0; index < snapshot.leagues.length; index++) {
    const league = snapshot.leagues[index];
    const margins = league.alternate_standings.weeks.flatMap((week) => week.matchups
      .filter((matchup) => matchup.home_score !== matchup.away_score)
      .map((matchup) => Math.round(Math.abs(matchup.home_score - matchup.away_score) * 100) / 100));
    await expect(cards.nth(index).locator(".leaderboard-entry")).toHaveCount(Math.min(3, margins.length));
    await expect(cards.nth(index).locator(".leaderboard-value").first()).toHaveText(`${Math.max(...margins).toFixed(2)} pts`);
    await expect(cards.nth(index).locator(".leaderboard-detail").first()).toContainText("vs");
  }
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
