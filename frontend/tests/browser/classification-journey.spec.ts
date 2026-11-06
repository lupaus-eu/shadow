import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, categories as ownCategories, organizationId, plannerApi, yearclockId } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";

type Row = Record<string, unknown> & { id: string };

test("Yearclock V2 classification journey: define, label, filter, and search", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-24", events: [] });
  const org = `${apiBase}/api/v1/organizations/${organizationId}`;
  const labels: Row[] = [];
  const shared: Row[] = [];
  const events: Row[] = [];
  let sequence = 0;
  const nextId = (prefix: string) => `${prefix}000000-0000-4000-8000-${String(++sequence).padStart(12, "0")}`;

  await context.route(`${org}/labels`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ status: 200, json: labels });
    const body = route.request().postDataJSON();
    const label = { id: nextId("1abe"), name: body.name, color: body.color, version: 1, usage: 0 };
    labels.push(label);
    return route.fulfill({ status: 201, json: label });
  });
  await context.route(`${org}/categories`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ status: 200, json: shared });
    const body = route.request().postDataJSON();
    const category = { id: nextId("ca7e"), name: body.name, color: body.color, display_order: shared.length, version: 1, scope: "organization", usage: 0 };
    shared.push(category);
    return route.fulfill({ status: 201, json: category });
  });
  await context.route(`${org}/yearclocks/${yearclockId}/categories`, (route) => route.fulfill({ status: 200, json: [...shared, ...ownCategories.map((category) => ({ ...category, scope: "yearclock" }))] }));
  await context.route(new RegExp(`${org}/yearclocks/${yearclockId}/events(\\?.*)?$`), async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ status: 200, json: events });
    const body = route.request().postDataJSON();
    const event = { id: nextId("e0"), version: 1, ends_on: null, description: null, location: null, links: [], ...body };
    events.push(event);
    return route.fulfill({ status: 201, json: event });
  });
  await context.route(`${org}/yearclocks/${yearclockId}/search**`, (route) => {
    const q = new URL(route.request().url()).searchParams.get("q")!.toLowerCase();
    const items = events.filter((event) => String(event.title).toLowerCase().includes(q));
    return route.fulfill({ status: 200, json: { items, next_offset: null, total: items.length, includes_recurring: false } });
  });

  // 1. An Owner defines the shared vocabulary.
  await page.goto(`/organizations/${organizationId}/admin/classification`);
  const panel = page.locator(".classification");
  await panel.getByLabel("Organization Categories: Name").fill("Board");
  await panel.getByRole("button", { name: "Add Category" }).click();
  await expect(panel.locator(".label-list strong", { hasText: "Board" })).toBeVisible();
  await panel.getByLabel("Name", { exact: true }).fill("Decision needed");
  await panel.getByRole("button", { name: "Add Label" }).click();
  await expect(panel.locator(".label-list strong", { hasText: "Decision needed" })).toBeVisible();

  // 2. The Yearclock opens on its own page.
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Northwind Yearclock" }).click();

  // 3. An Event gets the shared Category, an existing Label, and a new one.
  await page.getByRole("button", { name: "New Event" }).click();
  const form = page.getByRole("form", { name: "New Event" });
  await form.getByLabel("Title").fill("Budget approval");
  await form.getByLabel("Start date").fill("2026-10-01");
  await form.getByRole("combobox", { name: /^Category/ }).selectOption({ label: "Board" });
  const picker = form.getByRole("group", { name: /Labels/ });
  await picker.getByLabel("Decision needed").check();
  await picker.getByLabel("Find or create a Label").fill("Finance");
  await picker.getByRole("button", { name: "Create Label “Finance”" }).click();
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
  const clock = page.getByRole("group", { name: /Northwind Yearclock/ });
  await expect(clock.getByRole("button", { name: /^Budget approval, .*Board, Labels: Decision needed, Finance/ })).toBeVisible();
  expect(events[0]).toMatchObject({ title: "Budget approval", category_id: shared[0].id, label_ids: [labels[0].id, labels[1].id] });

  // 4. Filters narrow the view and say what is hidden.
  await showTab(page, "Filters");
  const filters = page.getByRole("region", { name: "Filters" });
  await filters.getByRole("group", { name: "Labels" }).getByLabel("Finance (1)").check();
  await expect(clock.getByRole("button", { name: /^Budget approval,/ })).toBeVisible();
  await filters.getByRole("group", { name: "Categories" }).getByLabel("Audit (0)").check();
  await expect(clock.getByRole("button", { name: /^Budget approval,/ })).toHaveCount(0);
  await expect(filters.getByRole("status")).toHaveText(/1 Event hidden by filters\./);
  await filters.getByRole("button", { name: "Show all" }).click();

  // 5. Search finds it and opens it.
  const search = page.getByRole("search", { name: "Search this Yearclock" });
  await search.getByLabel("Search text").fill("budget");
  await search.getByRole("button", { name: "Search" }).click();
  await page.locator(".yc-search-results").getByRole("button", { name: /Budget approval/ }).click();
  const details = page.getByRole("complementary", { name: "Event details" });
  await expect(details.getByRole("heading", { name: "Budget approval" })).toBeVisible();
  await expect(details.getByRole("listitem")).toHaveText(["Decision needed", "Finance"]);
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
});
