import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";
import { answerConfirm } from "./support/confirm";

const team = { id: "7f000000-0000-4000-8000-000000000001", name: "Team year", version: 1, access_role: "viewer", lanes: [{ id: "7a000000-0000-4000-8000-000000000001", name: "Sprints", display_order: 0, version: 1 }] };

test("Yearclock V2 planning journey: duplicate, bulk edit, plan again, copy and link a Lane", async ({ context, page }) => {
  const events = sampleEvents();
  const requests = await plannerApi(context, { today: "2026-09-25", events });
  const clock = { id: yearclockId, name: "Company overview", version: 1, access_role: "editor", lanes: [...lanes] as Array<Record<string, unknown>> };
  const workspace = () => ({ organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: [clock, team] });
  const yearclockApi = `${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}`;
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: workspace() }));
  await context.route(`${yearclockApi}/events/bulk`, (route) => {
    const body = route.request().postDataJSON();
    for (const item of body.items) { const event = events.find((row) => row.id === item.id)!; event.lane_id = body.lane_id; event.version += 1; }
    return route.fulfill({ status: 200, json: { bulk_id: "b", changed: body.items.length, items: [] } });
  });
  await context.route(`${yearclockApi}/plan-again`, (route) => route.fulfill({ status: 200, json: route.request().postDataJSON().dry_run ? { to_create: 3, skipped_existing: 0, limit_exceeded: false, maximum: 3000, created_ids: [] } : { to_create: 3, skipped_existing: 0, limit_exceeded: false, maximum: 3000, created_ids: ["x", "y", "z"] } }));
  await context.route(`${yearclockApi}/lanes/copy`, (route) => route.fulfill({ status: 201, json: { lane: { id: "c0000000-0000-4000-8000-000000000001", name: "Sprints", display_order: 2, version: 1 }, events: 5, series: 0, categories_created: 1 } }));
  await context.route(`${yearclockApi}/lanes/link`, (route) => {
    const lane = { id: "1c000000-0000-4000-8000-000000000001", name: "Sprints", display_order: 2, version: 1, source_lane_id: team.lanes[0].id, source: { available: true, reason: null, yearclock_id: team.id, yearclock_name: "Team year", lane_name: "Sprints" } };
    clock.lanes.push(lane);
    events.push({ id: "e7000000-0000-4000-8000-000000000001", lane_id: lane.id, category_id: null, title: "Sprint review", description: null, location: null, links: [], starts_on: "2026-10-14", ends_on: null, version: 1, linked: true, source_yearclock_id: team.id } as never);
    return route.fulfill({ status: 201, json: lane });
  });
  await page.goto(yearclockPath);

  await page.getByRole("button", { name: /^Year-end close,/ }).click();
  await page.getByRole("button", { name: "Duplicate" }).click();
  const form = page.getByRole("form", { name: "New Event" });
  await form.getByLabel("Title").fill("Year-end close rehearsal");
  await form.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => requests.filter((item) => item.method === "POST" && item.path === "/events").length).toBe(1);

  await showTab(page, "Events");
  const bulk = page.getByRole("region", { name: "Select Events" });
  await bulk.getByRole("button", { name: "Select Events" }).click();
  await page.getByRole("region", { name: "Events in this window" }).getByRole("checkbox", { name: /^Select Year-end close,/ }).check();
  await bulk.getByLabel("Move to Lane").selectOption({ label: "Governance" });
  await bulk.getByRole("button", { name: "Move", exact: true }).click();
  await answerConfirm(page);
  await expect(page.getByRole("status").filter({ hasText: "1 Event changed." })).toBeVisible();
  await bulk.getByRole("button", { name: "Select Events" }).click();

  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const planAgain = page.getByRole("region", { name: "Plan a season again" });
  await planAgain.getByRole("button", { name: "Preview" }).click();
  await planAgain.getByRole("button", { name: "Create 3 Events" }).click();
  await expect(planAgain.getByRole("status")).toHaveText("3 Events created.");

  const copier = page.getByRole("region", { name: "Copy from another Yearclock" });
  await copier.getByRole("button", { name: "Copy Lane" }).click();
  await expect(copier.getByRole("status")).toContainText("Lane copied with 5 Events and 0 Series.");

  const linker = page.getByRole("region", { name: "Link from another Yearclock" });
  await linker.getByRole("button", { name: "Link Lane" }).click();
  await expect(linker.getByRole("status")).toHaveText("Lane linked. It shows its source live and read only.");
  await expect(linker.getByText("No other Yearclock you can open has a Lane to link.")).toBeVisible();
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await page.getByRole("main").getByRole("link", { name: /^Back to / }).click();
  const summary = page.getByRole("region", { name: "Events in this window" });
  await expect(summary.getByRole("button", { name: /Sprint review.*Sprints \(from Team year\)/ })).toBeVisible();
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
});
