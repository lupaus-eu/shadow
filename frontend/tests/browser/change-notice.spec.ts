import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, organizationId, plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";

const changesUrl = `${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/changes**`;

test("a change by others raises a notice about a minute later, and Refresh reloads", async ({ context, page }) => {
  await plannerApi(context);
  await page.clock.install({ time: new Date("2026-09-25T09:00:00Z") });
  let total = 0;
  const polls: string[] = [];
  await context.route(changesUrl, (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("limit") === "1") polls.push(url.searchParams.get("since") ?? "");
    return route.fulfill({ status: 200, json: { items: [], total: url.searchParams.get("limit") === "1" ? total : 0, more: false, latest_at: null } });
  });
  const eventLoads: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/events?")) eventLoads.push(request.url()); });
  await page.goto(yearclockPath);
  await expect(page.getByRole("heading", { name: "Events in this window" })).toBeVisible();
  await page.clock.fastForward(61_000);
  await expect.poll(() => polls.length).toBe(1);
  await expect(page.getByText("This Yearclock has been changed by others since you opened it.")).toHaveCount(0);

  total = 1;
  await page.clock.fastForward(61_000);
  const notice = page.getByRole("status").filter({ hasText: "This Yearclock has been changed by others since you opened it." });
  await expect(notice).toBeVisible();
  expect(await new AxeBuilder({ page }).include(".yc-change-notice").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await page.clock.fastForward(61_000);
  expect(polls).toHaveLength(2);
  const before = eventLoads.length;
  total = 0;
  await notice.getByRole("button", { name: "Refresh" }).click();
  await expect(notice).toHaveCount(0);
  await expect.poll(() => eventLoads.length).toBeGreaterThan(before);
  await page.clock.fastForward(61_000);
  await expect.poll(() => polls.length).toBe(3);
  expect(polls[2] > polls[0]).toBe(true);
});

test("a hidden page does not poll", async ({ context, page }) => {
  await plannerApi(context);
  await page.clock.install({ time: new Date("2026-09-25T09:00:00Z") });
  let polls = 0;
  await context.route(changesUrl, (route) => { polls += 1; return route.fulfill({ status: 200, json: { items: [], total: 0, more: false, latest_at: null } }); });
  await page.goto(yearclockPath);
  await expect(page.getByRole("heading", { name: "Events in this window" })).toBeVisible();
  await page.evaluate(() => { Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true }); document.dispatchEvent(new Event("visibilitychange")); });
  await page.clock.fastForward(180_000);
  expect(polls).toBe(0);
  await page.evaluate(() => { Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true }); document.dispatchEvent(new Event("visibilitychange")); });
  await page.clock.fastForward(61_000);
  await expect.poll(() => polls).toBe(1);
});
