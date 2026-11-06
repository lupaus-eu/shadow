import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext } from "@playwright/test";

import { apiBase, categories, lanes, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";

const team = { id: "7f000000-0000-4000-8000-000000000001", name: "Team year", version: 1, access_role: "viewer", lanes: [{ id: "7a000000-0000-4000-8000-000000000001", name: "Sprints", display_order: 0, version: 1 }, { id: "7a000000-0000-4000-8000-000000000002", name: "Backlog", display_order: 1, version: 1 }] };
const linked = { id: "1c000000-0000-4000-8000-000000000001", name: "Sprints", display_order: 1, version: 1, source_lane_id: team.lanes[0].id, source: { available: true, reason: null, yearclock_id: team.id, yearclock_name: "Team year", lane_name: "Sprints" } };
const hidden = { id: "1c000000-0000-4000-8000-000000000002", name: "Secret", display_order: 2, version: 1, source_lane_id: "7a000000-0000-4000-8000-000000000009", source: { available: false, reason: "no_access", yearclock_id: null, yearclock_name: null, lane_name: null } };
const sprintCategory = { id: "c9000000-0000-4000-8000-000000000009", name: "Sprint", color: "#2e7d32", display_order: 0, version: 1, scope: "linked", source_yearclock_id: team.id, source_yearclock_name: "Team year" };

async function openRollup(context: BrowserContext, { role = "owner", accessRole = "editor" }: { role?: "owner" | "member"; accessRole?: "editor" | "viewer" } = {}) {
  const events = sampleEvents();
  events.push({ id: "e7000000-0000-4000-8000-000000000001", lane_id: linked.id, category_id: sprintCategory.id, title: "Sprint review", description: null, location: null, links: [], starts_on: "2026-03-18", ends_on: null, version: 3, linked: true, source_yearclock_id: team.id } as never);
  await plannerApi(context, { today: "2026-09-25", events, role, accessRole });
  const workspace = { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: [{ id: yearclockId, name: "Company overview", version: 1, access_role: accessRole, lanes: [lanes[0], linked, hidden] }, team] };
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: workspace }));
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/categories`, (route) => route.fulfill({ status: 200, json: [...categories, sprintCategory] }));
  const bodies: unknown[] = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/lanes/link`, (route) => { bodies.push(route.request().postDataJSON()); return route.fulfill({ status: 201, json: { ...linked, id: "1c000000-0000-4000-8000-000000000003" } }); });
  return bodies;
}

test("a roll-up Yearclock shows a Linked Lane read only and an unavailable one empty", async ({ context, page }) => {
  await openRollup(context);
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  const summary = page.getByRole("region", { name: "Events in this window" });
  await expect(summary.getByRole("button", { name: /Sprint review.*Sprints \(from Team year\)/ })).toBeVisible();
  await expect(page.locator(".yc-lane-unavailable")).toHaveCount(1);
  await expect(page.locator(".yc-lane-hit")).toHaveCount(1);
  await showTab(page, "Filters");
  await expect(page.getByRole("region", { name: "Filters" }).getByRole("group", { name: "Lanes" }).getByLabel(/Lane not available \(0\)/)).toBeVisible();
  await showTab(page, "Events");

  await summary.getByRole("button", { name: /Sprint review/ }).click();
  const details = page.getByRole("complementary", { name: "Event details" });
  await expect(details.getByText("This Event belongs to Team year and is shown here through a Linked Lane. Change it there.")).toBeVisible();
  await expect(details.getByRole("link", { name: "Open in Team year" })).toHaveAttribute("href", `/organizations/${organizationId}/yearclocks/${team.id}`);
  await expect(details.getByText("Sprint", { exact: true })).toBeVisible();
  for (const name of ["Edit", "Delete", "Duplicate", "Plan again next year"]) await expect(details.getByRole("button", { name })).toHaveCount(0);
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);

  await showTab(page, "Events");
  await page.getByRole("button", { name: "Select Events" }).click();
  await expect(summary.getByRole("checkbox", { name: /^Select Sprint review,/ })).toBeDisabled();
  await page.getByRole("button", { name: "New Event" }).click();
  await expect(page.getByRole("form", { name: "New Event" }).getByRole("combobox", { name: "Lane" }).locator("option")).toHaveText(["Governance"]);
  await expect(page.getByRole("form", { name: "New Event" }).getByRole("combobox", { name: "Category" }).locator("option")).not.toContainText(["Sprint"]);
});

test("Editors link a Lane and style Linked Lanes without renaming them", async ({ context, page }) => {
  const bodies = await openRollup(context);
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const linker = page.getByRole("region", { name: "Link from another Yearclock" });
  await expect(linker.getByLabel("Link from Yearclock").locator("option")).toHaveText(["Team year"]);
  await expect(linker.getByLabel("Lane to link").locator("option")).toHaveText(["Backlog"]);
  expect(await new AxeBuilder({ page }).include(".yc-structure").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await linker.getByRole("button", { name: "Link Lane" }).click();
  await expect(linker.getByRole("status")).toHaveText("Lane linked. It shows its source live and read only.");
  expect(bodies).toEqual([{ source_lane_id: team.lanes[1].id }]);

  const row = page.getByRole("region", { name: "Lanes" }).getByRole("listitem").nth(1);
  await expect(row.getByText("Linked: Sprints (from Team year)")).toBeVisible();
  await expect(row.getByRole("textbox")).toHaveCount(0);
  await expect(row.getByLabel("Tint: Sprints")).toBeVisible();
});

test("Viewers see Linked Lanes but no link controls", async ({ context, page }) => {
  await openRollup(context, { role: "member", accessRole: "viewer" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await expect(page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Sprint review/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Yearclock settings" })).toHaveCount(0);
});

test("Filters group source Categories and search finds linked Events", async ({ context, page }) => {
  await openRollup(context);
  const result = { id: "e7000000-0000-4000-8000-000000000001", lane_id: linked.id, category_id: sprintCategory.id, title: "Sprint review", description: null, location: null, links: [], starts_on: "2026-03-18", ends_on: null, version: 3, linked: true, source_yearclock_id: team.id, label_ids: [] };
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/search**`, (route) => route.fulfill({ status: 200, json: { items: [result], next_offset: null, total: 1, includes_recurring: false } }));
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await showTab(page, "Filters");
  const filters = page.getByRole("region", { name: "Filters" });
  const fromTeam = filters.getByRole("group", { name: "Categories from Team year" });
  await expect(fromTeam.getByLabel(/Sprint \(1\)/)).toBeVisible();
  await expect(filters.getByRole("group", { name: "Categories", exact: true }).getByLabel(/Sprint/)).toHaveCount(0);
  await fromTeam.getByLabel(/Sprint \(1\)/).check();
  expect(await new AxeBuilder({ page }).include(".yc-filters").withTags(["wcag2a", "wcag2aa"]).analyze().then((scan) => scan.violations.map((violation) => violation.id))).toEqual([]);
  await showTab(page, "Events");
  const summary = page.getByRole("region", { name: "Events in this window" });
  await expect(summary.getByRole("button", { name: /Sprint review/ })).toBeVisible();
  await expect(summary.getByRole("button", { name: /Board meeting/ })).toHaveCount(0);
  await showTab(page, "Filters");
  await filters.getByRole("button", { name: "Show all" }).click();

  const search = page.getByRole("search", { name: "Search this Yearclock" });
  await search.getByLabel("Search text").fill("sprint");
  await search.getByLabel("Search text").press("Enter");
  await page.locator(".yc-search").getByRole("button", { name: /18 Mar 2026 Sprint review/ }).click();
  const details = page.getByRole("complementary", { name: "Event details" });
  await expect(details.getByRole("heading", { name: "Sprint review" })).toBeVisible();
  await expect(details.getByRole("link", { name: "Open in Team year" })).toBeVisible();
  await expect(details.getByRole("button", { name: "Edit" })).toHaveCount(0);
});

test("the timeline shows a Linked Lane read only and an unavailable one empty", async ({ context, page }) => {
  await openRollup(context);
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("radio", { name: "Timeline" }).click();
  const timeline = page.getByRole("region", { name: "Events in this window" });
  const linkedLane = timeline.getByRole("group", { name: "Sprints (from Team year)" });
  await expect(linkedLane.getByRole("button", { name: /^Sprint review.*Sprints \(from Team year\)/ })).toBeVisible();
  await expect(timeline.getByRole("group", { name: "Lane not available" }).getByRole("button")).toHaveCount(0);
  const track = linkedLane.locator("> div").nth(1);
  const box = (await track.boundingBox())!;
  await track.click({ position: { x: box.width * 0.8, y: 6 } });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await linkedLane.getByRole("button", { name: /^Sprint review/ }).click();
  await expect(page.getByRole("complementary", { name: "Event details" }).getByRole("link", { name: "Open in Team year" })).toBeVisible();
});
