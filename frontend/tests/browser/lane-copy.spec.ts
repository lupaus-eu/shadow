import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";

const hr = { id: "7f000000-0000-4000-8000-000000000001", name: "HR year", version: 1, access_role: "viewer", lanes: [{ id: "7a000000-0000-4000-8000-000000000001", name: "Onboarding", display_order: 0, version: 1 }, { id: "7a000000-0000-4000-8000-000000000002", name: "Reviews", display_order: 1, version: 1 }] };

async function openWithSources(context: BrowserContext, reply: (body: Record<string, unknown>) => { status: number; json: unknown }) {
  await plannerApi(context, { today: "2026-09-25" });
  const workspace = { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: [{ id: yearclockId, name: "Northwind Yearclock", version: 1, access_role: "editor", lanes }, hr] };
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: workspace }));
  const bodies: Array<Record<string, unknown>> = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/lanes/copy`, (route) => {
    const body = route.request().postDataJSON();
    bodies.push(body);
    return route.fulfill(reply(body));
  });
  return bodies;
}

test("an Editor copies a Lane with its Events from another Yearclock", async ({ context, page }) => {
  const bodies = await openWithSources(context, (body) => ({ status: 201, json: { lane: { id: "n1", name: "Reviews", display_order: 2, version: 1 }, events: body.include_events ? 4 : 0, series: body.include_events ? 1 : 0, categories_created: 0 } }));
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const copier = page.getByRole("region", { name: "Copy from another Yearclock" });
  await expect(copier.getByLabel("Copy from Yearclock")).toHaveValue(hr.id);
  await expect(copier.getByLabel("Lane to copy").locator("option")).toHaveText(["Onboarding", "Reviews"]);
  await copier.getByLabel("Lane to copy").selectOption({ label: "Reviews" });
  expect(await new AxeBuilder({ page }).include(".yc-structure").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await copier.getByRole("button", { name: "Copy Lane" }).click();
  await expect(copier.getByRole("status")).toHaveText("Lane copied with 4 Events and 1 Series. The copy no longer follows the original.");
  expect(bodies[0]).toEqual({ source_lane_id: hr.lanes[1].id, include_events: true });

  await copier.getByLabel("Copy from Yearclock").selectOption({ label: "Northwind Yearclock" });
  await expect(copier.getByLabel("Lane to copy").locator("option")).toHaveText(lanes.map((lane) => lane.name));
  await copier.getByLabel("Include its Events and recurring Series").uncheck();
  await copier.getByRole("button", { name: "Copy Lane" }).click();
  await expect(copier.getByRole("status")).toHaveText("Lane copied with 0 Events and 0 Series. The copy no longer follows the original.");
  expect(bodies[1]).toEqual({ source_lane_id: lanes[0].id, include_events: false });
});

test("a copy that would exceed a limit names it and copies nothing", async ({ context, page }) => {
  await openWithSources(context, () => ({ status: 409, json: { detail: { reason: "limit_reached", limit: "categories_per_yearclock", maximum: 40 } } }));
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const copier = page.getByRole("region", { name: "Copy from another Yearclock" });
  await copier.getByRole("button", { name: "Copy Lane" }).click();
  await expect(copier.getByRole("alert")).toHaveText("Nothing was copied: this Yearclock would exceed its limit of 40 Categories.");
});
