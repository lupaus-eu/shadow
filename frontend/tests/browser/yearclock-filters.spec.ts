import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, organizationId, plannerApi, sampleEvents, yearclockPath } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";

const decision = { id: "1abe1000-0000-4000-8000-000000000001", name: "Decision needed", color: "#c62828", version: 1, usage: 1 };

async function openPlanner(context: import("@playwright/test").BrowserContext, page: import("@playwright/test").Page) {
  const events = sampleEvents();
  events[1] = { ...events[1], label_ids: [decision.id] };
  await plannerApi(context, { today: "2026-09-24", events });
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/labels`, (route) => route.fulfill({ status: 200, json: [decision] }));
  await page.goto(yearclockPath);
  await showTab(page, "Filters");
  return page.getByRole("region", { name: "Filters" });
}

test("filters combine Lanes, Categories, and Labels, count matches, and announce hidden Events", async ({ context, page }) => {
  const filters = await openPlanner(context, page);
  const clock = page.getByRole("group", { name: /Northwind Yearclock/ });
  const summary = page.getByRole("region", { name: "Events in this window" });
  await expect(filters.getByRole("group", { name: "Lanes" }).getByLabel("Governance (2)")).toBeVisible();
  await expect(filters.getByRole("status")).toHaveText("");
  expect(await new AxeBuilder({ page }).include(".yc-filters").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);

  await filters.getByRole("group", { name: "Lanes" }).getByLabel("Governance (2)").check();
  await expect(clock.getByRole("button", { name: /^Board meeting,/ })).toBeVisible();
  await expect(clock.getByRole("button", { name: /^Year-end close,/ })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: /^Filters \(\d+ hidden\)/ })).toBeVisible();
  await showTab(page, "Events");
  await expect(summary.getByRole("button", { name: /Board meeting/ })).toBeVisible();
  await expect(summary.getByText("Weekly finance check")).toHaveCount(0);
  await showTab(page, "Filters");
  await expect(filters.getByRole("status")).toContainText(/\d+ Events hidden by filters\./);
  await expect(filters.getByRole("group", { name: "Labels" }).getByLabel("Decision needed (1)")).toBeVisible();

  await filters.getByRole("group", { name: "Labels" }).getByLabel("Decision needed (1)").check();
  await expect(clock.getByRole("button", { name: /^Audit period,/ })).toBeVisible();
  await expect(clock.getByRole("button", { name: /^Board meeting,/ })).toHaveCount(0);
  await expect(filters.getByRole("group", { name: "Categories" }).getByLabel("Audit (1)")).toBeVisible();
  await expect(filters.getByRole("group", { name: "Categories" }).getByLabel("Board (0)")).toBeVisible();

  await filters.getByRole("button", { name: "Show all" }).click();
  await expect(clock.getByRole("button", { name: /^Board meeting,/ })).toBeVisible();
  await expect(filters.getByRole("status")).toHaveText("");
});

test("uncategorized Events can be shown alone, and filters survive a reload per Yearclock", async ({ context, page }) => {
  const filters = await openPlanner(context, page);
  const clock = page.getByRole("group", { name: /Northwind Yearclock/ });
  await filters.getByRole("group", { name: "Categories" }).getByRole("checkbox", { name: /^No Category/ }).check();
  await expect(clock.getByRole("button", { name: /^Year-end close,/ })).toBeVisible();
  await expect(clock.getByRole("button", { name: /^Board meeting,/ })).toHaveCount(0);
  await page.reload();
  await showTab(page, "Filters");
  await expect(page.getByRole("region", { name: "Filters" }).getByRole("group", { name: "Categories" }).getByRole("checkbox", { name: /^No Category/ })).toBeChecked();
  await expect(clock.getByRole("button", { name: /^Board meeting,/ })).toHaveCount(0);
  await page.getByRole("region", { name: "Filters" }).getByRole("button", { name: "Show all" }).click();
  await page.reload();
  await expect(clock.getByRole("button", { name: /^Board meeting,/ })).toBeVisible();
});

test("filters work from the keyboard", async ({ context, page }) => {
  const filters = await openPlanner(context, page);
  const governance = filters.getByRole("group", { name: "Lanes" }).getByLabel("Governance (2)");
  await governance.focus();
  await page.keyboard.press("Space");
  await expect(governance).toBeChecked();
  await expect(filters.getByRole("status")).toContainText("hidden by filters");
  await filters.getByRole("button", { name: "Show all" }).focus();
  await page.keyboard.press("Enter");
  await expect(governance).not.toBeChecked();
});
