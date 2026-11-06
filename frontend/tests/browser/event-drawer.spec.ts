import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { plannerApi, yearclockPath } from "./support/yearclock-fixture";

const axe = (page: import("@playwright/test").Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));

test("New Event opens a drawer beside the circle; Escape closes it and focus returns", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  const trigger = page.getByRole("button", { name: "New Event" });
  await trigger.click();
  const drawer = page.getByRole("dialog", { name: "New Event" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("form", { name: "New Event" }).getByLabel("Title")).toBeVisible();
  const box = (await drawer.boundingBox())!;
  const viewport = page.viewportSize()!;
  expect(box.x + box.width).toBeCloseTo(viewport.width, 0);
  expect(box.width).toBeLessThan(viewport.width / 2);
  expect(await axe(page)).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("editing from Details uses the drawer and returns focus to Edit", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ }).click();
  const edit = page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit" });
  await edit.click();
  const drawer = page.getByRole("dialog", { name: "Edit" });
  await expect(drawer.getByLabel("Title")).toHaveValue("Board meeting");
  await drawer.getByRole("button", { name: "Cancel" }).click();
  await expect(drawer).toHaveCount(0);
  await expect(edit).toBeFocused();
});

test("on a phone the drawer covers the screen", async ({ context, page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await page.getByRole("button", { name: "New Event" }).click();
  const box = (await page.getByRole("dialog", { name: "New Event" }).boundingBox())!;
  expect(box.x).toBe(0);
  expect(box.width).toBe(390);
});

test("Yearclock settings hold Layout, Lanes, Categories, Plan a season again, copy and link", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  await expect(page).toHaveURL(`${yearclockPath}/settings`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Yearclock settings: Northwind Yearclock");
  for (const name of ["Layout", "Lanes", "Categories", "Plan a season again", "Copy from another Yearclock", "Link from another Yearclock"]) await expect(page.getByRole("region", { name, exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Northwind Yearclock" })).toHaveAttribute("aria-current", "page");
  expect(await axe(page)).toEqual([]);
});

test("Viewers get no settings link and the settings address shows nothing to change", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-23" });
  await page.goto(yearclockPath);
  await expect(page.getByRole("heading", { name: "Events in this window" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Yearclock settings" })).toHaveCount(0);
  await page.goto(`${yearclockPath}/settings`);
  await expect(page.getByRole("alert")).toHaveText("This Yearclock does not exist or you do not have access to it.");
  await expect(page.getByRole("region", { name: "Lanes" })).toHaveCount(0);
});
