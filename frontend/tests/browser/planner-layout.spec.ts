import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { plannerApi, yearclockPath } from "./support/yearclock-fixture";

const axe = (page: import("@playwright/test").Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));

test("one toolbar holds the window, navigation, search, and New Event; the keyboard moves through it", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  const window = page.getByRole("group", { name: "Planning Window" });
  const length = window.getByRole("radiogroup", { name: "Length" });
  await expect(length.getByRole("radio", { name: "12 months" })).toHaveAttribute("aria-checked", "true");
  await length.getByRole("radio", { name: "12 months" }).focus();
  await page.keyboard.press("ArrowLeft");
  await expect(length.getByRole("radio", { name: "6 months" })).toBeFocused();
  await expect(length.getByRole("radio", { name: "6 months" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText("Showing 1 Jan 2026 to 30 Jun 2026")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(window.getByRole("button", { name: "Previous period" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Showing 1 Jul 2025 to 31 Dec 2025")).toBeVisible();
  await window.getByRole("button", { name: "Current period" }).click();
  await expect(page.getByRole("search", { name: "Search this Yearclock" })).toBeVisible();
  await expect(page.getByRole("button", { name: "New Event" })).toBeVisible();
  expect(await axe(page)).toEqual([]);
});

test("the side panel's tabs switch with the keyboard, and choosing an Event opens Details", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  const tabs = page.getByRole("tablist", { name: "Yearclock panel" });
  await expect(tabs.getByRole("tab")).toHaveText(["Events", "Filters"]);
  await tabs.getByRole("tab", { name: "Events" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(tabs.getByRole("tab", { name: "Filters" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("region", { name: "Filters" })).toBeVisible();
  await page.keyboard.press("ArrowLeft");
  await page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ }).click();
  await expect(tabs.getByRole("tab")).toHaveText(["Events", "Details", "Filters"]);
  await expect(tabs.getByRole("tab", { name: "Details" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("complementary", { name: "Event details" }).getByRole("heading", { name: "Board meeting" })).toBeVisible();
  expect(await axe(page)).toEqual([]);
});

test("on a phone the circle comes first and Events can be read and opened below it", async ({ context, page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  const circle = (await page.getByRole("group", { name: /Northwind Yearclock, January 2026/ }).boundingBox())!;
  const panel = (await page.getByRole("tablist", { name: "Yearclock panel" }).boundingBox())!;
  expect(panel.y).toBeGreaterThan(circle.y + circle.height - 1);
  expect(circle.x + circle.width).toBeLessThanOrEqual(390);
  await page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Audit period/ }).click();
  await expect(page.getByRole("complementary", { name: "Event details" }).getByRole("heading", { name: "Audit period" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await axe(page)).toEqual([]);
});
