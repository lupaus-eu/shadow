import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";
import { answerConfirm } from "./support/confirm";
import { showTab } from "./support/panel";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const open = async (page: Page) => {
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("radiogroup", { name: "Display" }).getByRole("radio", { name: "List" }).click();
  return page.getByRole("region", { name: "Events in this window" });
};

test("the Display choice switches to a table of the window's Events and is remembered", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const list = await open(page);
  await expect(page.getByRole("radiogroup", { name: "Display" }).getByRole("radio")).toHaveText(["Circle", "Timeline", "List", "Agenda"]);
  await expect(list.getByRole("columnheader")).toHaveText(["Date▲", "Title", "Lane", "Category", "Labels"]);
  await expect(list.getByRole("button", { name: /^Board meeting,/ })).toBeVisible();
  await expect(list.getByRole("button", { name: /^Audit period,/ })).toBeVisible();
  await expect(list.getByRole("cell", { name: "Governance" }).first()).toBeVisible();
  expect(await axe(page)).toEqual([]);
  await page.reload();
  await expect(page.getByRole("radiogroup", { name: "Display" }).getByRole("radio", { name: "List" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("region", { name: "Events in this window" }).getByRole("table")).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Yearclock panel" }).getByRole("tab")).toHaveText(["Filters"]);
});

test("rows sort by the chosen column and a Series is one expandable row", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const list = await open(page);
  const names = () => list.getByRole("row").evaluateAll((rows) => rows.slice(1).map((row) => (row.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 80)));
  expect((await names())[0]).toMatch(/Weekly finance check — recurring, 20 occurrences/);
  await list.getByRole("columnheader", { name: /^Title/ }).getByRole("button").click();
  await expect(list.getByRole("columnheader", { name: /^Title/ })).toHaveAttribute("aria-sort", "ascending");
  expect((await names())[0]).toMatch(/1 Apr 2026 – 15 May 2026.*Audit period/);
  await list.getByRole("columnheader", { name: /^Title/ }).getByRole("button").click();
  await expect(list.getByRole("columnheader", { name: /^Title/ })).toHaveAttribute("aria-sort", "descending");
  await list.getByRole("columnheader", { name: /^Date/ }).getByRole("button").click();
  const series = list.getByRole("button", { name: /Weekly finance check — recurring/ });
  await expect(series).toHaveAttribute("aria-expanded", "false");
  await series.click();
  await expect(series).toHaveAttribute("aria-expanded", "true");
  await expect(list.getByRole("button", { name: /^Weekly finance check, 5 Jan 2026/ })).toBeVisible();
});

test("choosing a row opens Details, and the selection survives switching displays", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const list = await open(page);
  await list.getByRole("button", { name: /^Board meeting,/ }).click();
  const details = page.getByRole("complementary", { name: "Event details" });
  await expect(details.getByRole("heading", { name: "Board meeting" })).toBeVisible();
  await expect(list.getByRole("button", { name: /^Board meeting,/ })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("radiogroup", { name: "Display" }).getByRole("radio", { name: "Circle" }).click();
  await expect(details.getByRole("heading", { name: "Board meeting" })).toBeVisible();
  await expect(page.getByRole("group", { name: /Northwind Yearclock/ }).getByRole("button", { name: /^Board meeting,/ })).toHaveAttribute("aria-pressed", "true");
});

test("Filters apply to the list, and a Viewer sees no selection mode or New Event", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const list = await open(page);
  await showTab(page, "Filters");
  await page.getByRole("region", { name: "Filters" }).getByRole("group", { name: "Lanes" }).getByLabel(/Finance \(/).check();
  await expect(list.getByRole("button", { name: /^Board meeting,/ })).toHaveCount(0);
  await expect(list.getByRole("button", { name: /^Year-end close,/ })).toBeVisible();
});

test("a Viewer's list has no selection controls", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-23" });
  const list = await open(page);
  await expect(list.getByRole("button", { name: /^Board meeting,/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Select Events" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "New Event" })).toHaveCount(0);
});

test("Editors tick rows and move them with one confirmed bulk change; occurrences cannot be ticked", async ({ context, page }) => {
  const events = sampleEvents();
  await plannerApi(context, { today: "2026-09-23", events });
  const bodies: Array<Record<string, unknown>> = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/bulk`, (route) => {
    bodies.push(route.request().postDataJSON());
    return route.fulfill({ status: 200, json: { bulk_id: "b1", changed: 2, items: [] } });
  });
  const list = await open(page);
  const bulk = page.getByRole("region", { name: "Select Events" });
  await bulk.getByRole("button", { name: "Select Events" }).click();
  await expect(list.getByRole("checkbox", { name: /^Select Board meeting,/ })).toBeEnabled();
  await list.getByRole("button", { name: /Weekly finance check — recurring/ }).click();
  await expect(list.getByRole("checkbox", { name: /^Select Weekly finance check,/ }).first()).toBeDisabled();
  await list.getByRole("checkbox", { name: /^Select Board meeting,/ }).check();
  await list.getByRole("checkbox", { name: /^Select Audit period,/ }).check();
  await expect(bulk.getByRole("status")).toHaveText("2 Events selected");
  await bulk.getByLabel("Move to Lane").selectOption({ label: lanes[1].name });
  await bulk.getByRole("button", { name: "Move", exact: true }).click();
  expect(await answerConfirm(page)).toBe("Change 2 Events?");
  await expect.poll(() => bodies.length).toBe(1);
  expect(bodies[0]).toMatchObject({ action: "move", lane_id: lanes[1].id });
});

test("on a phone the rows become cards with touch-sized targets and nothing scrolls sideways", async ({ context, page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await plannerApi(context, { today: "2026-09-23" });
  const list = await open(page);
  await expect(list.getByLabel("Sort by")).toBeVisible();
  const card = (await list.getByRole("button", { name: /^Board meeting,/ }).boundingBox())!;
  expect(card.height).toBeGreaterThanOrEqual(24);
  expect(card.x + card.width).toBeLessThanOrEqual(390);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await list.getByLabel("Sort by").selectOption({ label: "Title" });
  await list.getByRole("button", { name: /^Board meeting,/ }).click();
  await expect(page.getByRole("complementary", { name: "Event details" }).getByRole("heading", { name: "Board meeting" })).toBeVisible();
  expect(await axe(page)).toEqual([]);
});
