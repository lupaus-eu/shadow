import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { plannerApi, yearclockPath } from "./support/yearclock-fixture";

test("the Planning Window length changes, steps by periods, and is remembered", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-25" });
  await page.goto(yearclockPath);
  const toolbar = page.getByRole("group", { name: "Planning Window" });
  await expect(page.getByText("Showing 1 Jan 2026 to 31 Dec 2026")).toBeVisible();
  await toolbar.getByRole("radio", { name: "3 months", exact: true }).click();
  await expect(page.getByText("Showing 1 Jan 2026 to 31 Mar 2026")).toBeVisible();
  await expect(page.getByRole("group", { name: "Northwind Yearclock, January 2026 to March 2026" })).toBeVisible();
  await expect(page.locator(".yc-month-label")).toHaveCount(3);
  await toolbar.getByRole("button", { name: "Next period" }).click();
  await expect(page.getByText("Showing 1 Apr 2026 to 30 Jun 2026")).toBeVisible();
  await toolbar.getByRole("button", { name: "Next month" }).click();
  await expect(page.getByText("Showing 1 May 2026 to 31 Jul 2026")).toBeVisible();
  await toolbar.getByRole("button", { name: "Current period" }).click();
  await expect(page.getByText(/Showing\ 1\ Sept?\ 2026\ to\ 30\ Nov\ 2026/)).toBeVisible();
  expect(requests.some((request) => request.method === "GET" && request.path === "/events" && request.search.includes("months=3"))).toBe(true);

  await page.reload();
  await expect(page.getByRole("group", { name: "Planning Window" }).getByRole("radio", { name: "3 months", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText(/Showing\ 1\ Sept?\ 2026\ to\ 30\ Nov\ 2026/)).toBeVisible();

  await page.getByRole("group", { name: "Planning Window" }).getByRole("radio", { name: "24 months", exact: true }).click();
  await expect(page.getByText(/Showing\ 1\ Sept?\ 2026\ to\ 31\ Aug\ 2028/)).toBeVisible();
  await expect(page.locator(".yc-month-label")).toHaveCount(24);
});

test("a one-month window shows numbered day marks", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-25" });
  await page.goto(yearclockPath);
  await page.getByRole("group", { name: "Planning Window" }).getByRole("radio", { name: "1 month", exact: true }).click();
  await expect(page.getByText("Showing 1 Jan 2026 to 31 Jan 2026")).toBeVisible();
  await page.getByRole("group", { name: "Planning Window" }).getByRole("button", { name: "Current period" }).click();
  await expect(page.getByText(/Showing\ 1\ Sept?\ 2026\ to\ 30\ Sept?\ 2026/)).toBeVisible();
  await expect(page.locator(".yc-day-tick")).toHaveCount(30);
  await expect(page.locator(".yc-day-label")).toHaveText(["1", "5", "10", "15", "20", "25", "30"]);
  await expect(page.locator(".yc-month-label")).toHaveCount(0);
  expect(await new AxeBuilder({ page }).include(".yc-planner").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await page.getByRole("group", { name: "Planning Window" }).getByRole("radio", { name: "6 months", exact: true }).click();
  await expect(page.locator(".yc-day-tick")).toHaveCount(0);
});
