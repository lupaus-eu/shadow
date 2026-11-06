import { expect, test } from "@playwright/test";

import { lanes, plannerApi, yearclockPath } from "./support/yearclock-fixture";

// The Event ceiling of a Yearclock is 3000 (LIMIT_EVENTS_PER_YEARCLOCK). This measures the three displays
// that list or draw every Event at that size; the budget is generous and only catches a collapse.
test("a Yearclock with 3000 Events stays usable in the timeline, the list, and the agenda", async ({ context, page }) => {
  const events = Array.from({ length: 3000 }, (_, index) => {
    const date = new Date(Date.UTC(2026, 0, 1 + (index % 365))).toISOString().slice(0, 10);
    return { id: `e${String(index).padStart(7, "0")}-0000-4000-8000-000000000000`, lane_id: lanes[index % 2].id, category_id: null, title: `Event ${index}`, description: null, location: null, links: [], starts_on: date, ends_on: index % 5 === 0 ? new Date(Date.UTC(2026, 0, 3 + (index % 365))).toISOString().slice(0, 10) : null, version: 1 };
  });
  await plannerApi(context, { today: "2026-09-23", events });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await expect(page.getByRole("heading", { name: "Events in this window" })).toBeVisible();
  const timings: Record<string, number> = {};
  for (const [name, check] of [["Timeline", ".yc-timeline-item"], ["List", ".yc-list-row"], ["Agenda", ".yc-agenda-item"]] as const) {
    const started = Date.now();
    await page.getByRole("radio", { name, exact: true }).click();
    await expect(page.locator(check).first()).toBeVisible({ timeout: 15_000 });
    timings[name] = Date.now() - started;
  }
  const counts = { timeline: 0 };
  await page.getByRole("radio", { name: "Timeline", exact: true }).click();
  counts.timeline = await page.locator(".yc-timeline-item").count();
  console.log(`3000 Events: ${JSON.stringify(timings)} ms, ${counts.timeline} timeline items`);
  expect(counts.timeline).toBeGreaterThan(2500);
  for (const [name, ms] of Object.entries(timings)) expect(ms, `${name} took ${ms} ms`).toBeLessThan(6000);
});
