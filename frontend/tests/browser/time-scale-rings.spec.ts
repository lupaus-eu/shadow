import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";

async function workspace(context: BrowserContext, layout: Record<string, unknown>) {
  await plannerApi(context, { today: "2026-09-25" });
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: [{ id: yearclockId, name: "Finance year", version: 2, access_role: "editor", lanes, ...layout }] } }));
}

test("quarters follow the start month and week numbers stay legible at every length", async ({ context, page }) => {
  await workspace(context, { start_month: 8, show_week_ring: true, show_quarter_ring: true });
  await page.goto(yearclockPath);
  await expect(page.getByText("Showing 1 Aug 2026 to 31 Jul 2027")).toBeVisible();
  await expect(page.locator(".yc-quarter-label")).toHaveText(["Q1", "Q2", "Q3", "Q4"]);
  const weekLabels = await page.locator(".yc-week-label").allTextContents();
  expect(weekLabels.length).toBeGreaterThan(20);
  expect(weekLabels.every((label) => Number(label) % 2 === 0)).toBe(true);
  await expect(page.getByRole("button", { name: /^Year-end close,/ })).toBeVisible();
  expect(await new AxeBuilder({ page }).include(".yc-planner").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);

  await page.getByRole("group", { name: "Planning Window" }).getByRole("radio", { name: "3 months", exact: true }).click();
  await expect(page.locator(".yc-quarter-label")).toHaveText(["Q1"]);
  await page.getByRole("group", { name: "Planning Window" }).getByRole("radio", { name: "24 months", exact: true }).click();
  expect((await page.locator(".yc-week-label").allTextContents()).every((label) => Number(label) % 4 === 0)).toBe(true);
});

test("rings fit a small screen and Editors turn them on", async ({ context, page }) => {
  await workspace(context, { start_month: 1, show_week_ring: false, show_quarter_ring: false });
  const bodies: unknown[] = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/layout`, (route) => { bodies.push(route.request().postDataJSON()); return route.fulfill({ status: 200, json: { id: yearclockId, version: 3, start_month: 1, show_week_ring: true, show_quarter_ring: true } }); });
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto(yearclockPath);
  await expect(page.locator(".yc-quarter-label")).toHaveCount(0);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const layout = page.getByRole("region", { name: "Layout" });
  await layout.getByLabel("Show week numbers").check();
  await layout.getByLabel("Show quarters").check();
  await layout.getByRole("button", { name: "Save layout" }).click();
  await expect(layout.getByRole("status")).toHaveText("Layout saved.");
  expect(bodies).toEqual([{ start_month: 1, show_week_ring: true, show_quarter_ring: true, expected_version: 2 }]);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
