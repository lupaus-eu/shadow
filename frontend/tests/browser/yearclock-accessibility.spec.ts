import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { organizationId, plannerApi, yearclockPath } from "./support/yearclock-fixture";

async function axe(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  return results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

test("the dense planner has no automatically detectable WCAG A/AA violations", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await expect(page.getByRole("group", { name: /Northwind Yearclock/ })).toBeVisible();
  expect(await axe(page)).toEqual([]);

  await page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ }).click();
  await expect(page.getByRole("complementary", { name: "Event details" })).toBeVisible();
  expect(await axe(page)).toEqual([]);

  await page.getByRole("button", { name: "New Event" }).click();
  await expect(page.getByRole("form", { name: "New Event" })).toBeVisible();
  expect(await axe(page)).toEqual([]);
});

test("keyboard users reach every marker in chronological order and open details", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  const clock = page.getByRole("group", { name: /Northwind Yearclock/ });
  const markers = clock.getByRole("button");
  await expect(markers).toHaveCount(23);
  const names = await markers.evaluateAll((items) => items.map((item) => item.getAttribute("aria-label") ?? ""));
  const dates = await markers.evaluateAll((items) => items.map((item) => item.getAttribute("aria-label")!.split(", ")[1]));
  const parsed = dates.map((value) => Date.parse(value.split(" – ")[0]));
  expect(parsed).toEqual([...parsed].sort((a, b) => a - b));

  await page.getByRole("button", { name: "Current period" }).focus();
  let reached = 0;
  for (let step = 0; step < 60 && reached < names.length; step += 1) {
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? "");
    if (focused === names[reached]) reached += 1;
  }
  expect(reached).toBe(names.length);

  await markers.first().focus();
  const outline = await markers.first().evaluate((element) => getComputedStyle(element).strokeWidth);
  expect(outline).toBe("3px");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("complementary", { name: "Event details" }).getByRole("heading", { name: "Weekly finance check" })).toBeVisible();
  await markers.nth(3).focus();
  await page.keyboard.press(" ");
  await expect(page.getByRole("complementary", { name: "Event details" }).getByRole("heading", { name: "Finance check (moved)" })).toBeVisible();
  await expect(markers.nth(3)).toHaveAttribute("aria-pressed", "true");
});

test("a dense Series draws compact markers with one label and stays usable on a phone", async ({ context, page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  const labels = page.locator(".yc-series-label");
  await expect(labels).toHaveCount(1);
  await expect(labels).toHaveText("Weekly finance check");
  const radii = await page.locator("circle.yc-dense").evaluateAll((items) => [...new Set(items.map((item) => item.getAttribute("r")))]);
  expect(radii).toEqual(["2.8"]);
  await expect(page.locator("rect.yc-exception")).toHaveCount(1);

  const summary = page.getByRole("region", { name: "Events in this window" });
  const group = summary.getByText("Weekly finance check — recurring, 20 occurrences");
  await expect(group).toBeVisible();
  await group.click();
  const occurrence = summary.getByRole("button", { name: /^19 Jan 2026 Weekly finance check/ });
  const box = (await occurrence.boundingBox())!;
  expect(box.height).toBeGreaterThanOrEqual(24);
  expect(box.x + box.width).toBeLessThanOrEqual(375);
  await occurrence.click();
  const sheet = page.getByRole("complementary", { name: "Event details" });
  await expect(sheet.getByText(/Series date 19 Jan 2026/)).toBeVisible();
  const sheetBox = (await sheet.boundingBox())!;
  expect(sheetBox.x + sheetBox.width).toBeLessThanOrEqual(375);
  expect(await axe(page)).toEqual([]);
});
