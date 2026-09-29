// Archive detail chart: weekly points each side received, with lead changes marked.

import {node, svg} from "./dom.js";
import {formatPoints} from "./format.js";
import {leadStory} from "./trades.js";

const WIDTH = 640;
const HEIGHT = 260;
const MARGIN = {left: 46, right: 12, top: 26, bottom: 44};
const TICK_STEP = 10;

function chartSummary(story, weeks) {
  if (story.incomplete) return "Some weekly scores are unavailable, so the lead can't be tracked.";
  if (story.flips.length) {
    return `${story.flips.map((flip) => `Lead flipped to ${flip.to.team} in Week ${flip.week}.`).join(" ")} ${story.leader.team} leads now.`;
  }
  if (story.leader) return weeks.length === 1 ? `${story.leader.team} leads after one week.` : `${story.leader.team} has led every week.`;
  return "Dead even so far.";
}

export function swingChart(trade) {
  const [a, b] = trade.sides;
  const weeks = trade.weeks;
  const values = weeks.flatMap((week) => [a, b].map((side) => side.weekly_points[String(week)] ?? 0));
  const max = Math.max(TICK_STEP, Math.ceil(Math.max(...values) / TICK_STEP) * TICK_STEP + TICK_STEP);
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right;
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const y = (value) => MARGIN.top + plotHeight - (value / max) * plotHeight;
  const story = leadStory(trade);

  const figure = node("figure", "swing-chart");
  const legend = node("div", "chart-legend");
  for (const [index, side] of [a, b].entries()) {
    const key = node("span", `chart-key side-${index}`);
    key.append(node("i"), node("span", "", side.team));
    legend.append(key);
  }
  const label = `Weekly points received: ${weeks.map((week) => `Week ${week}, ${a.team} ${formatPoints(a.weekly_points[String(week)])}, ${b.team} ${formatPoints(b.weekly_points[String(week)])}`).join("; ")}.`;
  const chart = svg("svg", {viewBox: `0 0 ${WIDTH} ${HEIGHT}`, role: "img", "aria-label": label, class: "chart-svg"});
  for (let tick = 0; tick <= max; tick += max / 4) {
    chart.append(
      svg("line", {x1: MARGIN.left, x2: WIDTH - MARGIN.right, y1: y(tick), y2: y(tick), class: "chart-grid"}),
      svg("text", {x: MARGIN.left - 8, y: y(tick) + 5, class: "chart-axis", "text-anchor": "end"}, Math.round(tick)),
    );
  }
  const group = plotWidth / weeks.length;
  const barWidth = Math.min(56, group * 0.3);
  const flipWeeks = new Set(story.flips.map((flip) => flip.week));
  weeks.forEach((week, index) => {
    const center = MARGIN.left + group * index + group / 2;
    if (week === trade.trade_week) {
      chart.append(svg("rect", {x: MARGIN.left + group * index + 4, y: MARGIN.top, width: group - 8, height: plotHeight, class: "chart-trade-week"}));
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
    chart.append(svg("text", {x: center, y: HEIGHT - 16, class: `chart-axis chart-week${flipWeeks.has(week) ? " chart-flip" : ""}`, "text-anchor": "middle"}, weekLabel));
  });
  chart.append(svg("line", {x1: MARGIN.left, x2: WIDTH - MARGIN.right, y1: y(0), y2: y(0), class: "chart-baseline"}));

  const markers = [
    story.flips.length ? "⇄ = cumulative lead changed" : null,
    trade.trade_week !== null && trade.trade_week !== undefined ? "* = trade week (shaded)" : null,
  ].filter(Boolean);
  const caption = node("figcaption", "chart-caption", chartSummary(story, weeks));
  if (markers.length) caption.append(node("span", "chart-markers", markers.join(" · ")));
  figure.append(legend, chart, caption);
  return figure;
}
