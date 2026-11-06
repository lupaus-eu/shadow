import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";

test("Yearclock V2 display journey: start month, rings, Lane style, one month, preview", async ({ context, page }) => {
  const events = sampleEvents();
  events.push({ ...events[0], id: "e6666666-0000-4000-8000-000000000000", title: "Term planning", starts_on: "2026-09-15", ends_on: null });
  await plannerApi(context, { today: "2026-09-25", events });
  const clock = { id: yearclockId, name: "School year", version: 1, access_role: "editor", lanes: lanes.map((lane) => ({ ...lane, tint: null, height: "normal" })), start_month: 1, show_week_ring: false, show_quarter_ring: false };
  const workspace = () => ({ organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: [clock] });
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: workspace() }));
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/layout`, (route) => {
    Object.assign(clock, route.request().postDataJSON(), { version: clock.version + 1 });
    return route.fulfill({ status: 200, json: clock });
  });
  await context.route(new RegExp(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/lanes/[^/]+$`), (route) => {
    const body = route.request().postDataJSON();
    const lane = clock.lanes.find((item) => route.request().url().endsWith(item.id))!;
    Object.assign(lane, { name: body.name, tint: body.tint, height: body.height, version: lane.version + 1 });
    return route.fulfill({ status: 200, json: lane });
  });

  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const layout = page.getByRole("region", { name: "Layout" });
  await layout.getByLabel("Year starts in").selectOption({ label: "August" });
  await layout.getByLabel("Show week numbers").check();
  await layout.getByLabel("Show quarters").check();
  await layout.getByRole("button", { name: "Save layout" }).click();
  await expect(layout.getByRole("status")).toHaveText("Layout saved.");

  const lanesSection = page.getByRole("region", { name: "Lanes" });
  await lanesSection.getByLabel(`Tint: ${lanes[0].name}`).selectOption({ label: "Blue" });
  await lanesSection.getByLabel(`Height: ${lanes[0].name}`).selectOption("tall");
  await lanesSection.getByRole("listitem").first().getByRole("button", { name: "Save" }).click();
  await expect(lanesSection.getByLabel(`Height: ${lanes[0].name}`)).toHaveValue("tall");
  await page.getByRole("main").getByRole("link", { name: /^Back to / }).click();
  await expect(page.locator(".yc-quarter-label").first()).toBeVisible();
  await expect(page.locator(".yc-lane-tint")).toHaveCount(1);

  const toolbar = page.getByRole("group", { name: "Planning Window" });
  await toolbar.getByRole("button", { name: "Current period" }).click();
  await expect(page.getByText("Showing 1 Aug 2026 to 31 Jul 2027")).toBeVisible();
  await expect(page.locator(".yc-quarter-label")).toHaveText(["Q1", "Q2", "Q3", "Q4"]);

  await toolbar.getByRole("radio", { name: "1 month", exact: true }).click();
  await toolbar.getByRole("button", { name: "Current period" }).click();
  await expect(page.getByText(/Showing 1 Sept? 2026 to 30 Sept? 2026/)).toBeVisible();
  await expect(page.locator(".yc-day-tick")).toHaveCount(30);

  await page.getByRole("button", { name: /^Term planning,/ }).hover();
  await expect(page.locator(".yc-preview-title")).toHaveText("Term planning");
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
});
