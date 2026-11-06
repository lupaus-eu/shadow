import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { plannerApi, yearclockPath } from "./support/yearclock-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const open = async (page: Page, query = "?window_start=2026-01-01", group = "Display", region = "Events in this window") => {
  await page.goto(`${yearclockPath}${query}`);
  await page.getByRole("radiogroup", { name: group }).getByRole("radio", { name: "Agenda" }).click();
  return page.getByRole("region", { name: region });
};

test("the agenda lists the window's Events by month and day beside the circle", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const agenda = await open(page);
  await expect(page.getByRole("group", { name: /Northwind Yearclock, January 2026/ })).toBeVisible();
  await expect(agenda.getByRole("heading", { level: 3 }).first()).toHaveText("January 2026");
  await expect(agenda.getByRole("heading", { level: 4, name: "Tuesday 10 March" })).toBeVisible();
  await expect(agenda.getByRole("button", { name: /^Board meeting,/ })).toBeVisible();
  await expect(agenda.getByRole("heading", { level: 4, name: "Monday 5 January" })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Yearclock panel" }).getByRole("tab")).toHaveText(["Filters"]);
  expect(await axe(page)).toEqual([]);
});

test("choosing a row selects the Event on the circle and in Details, and the circle's selection marks its row", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const agenda = await open(page);
  await agenda.getByRole("button", { name: /^Board meeting,/ }).click();
  await expect(page.getByRole("complementary", { name: "Event details" }).getByRole("heading", { name: "Board meeting" })).toBeVisible();
  const clock = page.getByRole("group", { name: /Northwind Yearclock/ });
  await expect(clock.getByRole("button", { name: /^Board meeting,/ })).toHaveAttribute("aria-pressed", "true");
  await clock.getByRole("button", { name: /^Audit period,/ }).click();
  await expect(agenda.getByRole("button", { name: /^Audit period,/ })).toHaveAttribute("aria-pressed", "true");
  await expect(agenda.getByRole("button", { name: /^Board meeting,/ })).toHaveAttribute("aria-pressed", "false");
});

test("a one-month window gives the single-month agenda", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const agenda = await open(page);
  await page.getByRole("radio", { name: "1 month", exact: true }).click();
  await expect(agenda.getByRole("heading", { level: 3 })).toHaveText(["January 2026"]);
  await expect(agenda.getByRole("heading", { level: 4 })).toHaveText(["Monday 5 January", "Monday 12 January", "Monday 19 January", "Wednesday 28 January"]);
});

test("the agenda is in Finnish and works from the keyboard", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", locale: "fi" });
  const agenda = await open(page, "?window_start=2026-01-01", "Näkymä", "Tapahtumat tällä jaksolla");
  await expect(agenda.getByRole("heading", { level: 4, name: /tiistai 10\. maaliskuuta/ })).toBeVisible();
  await expect(agenda.getByRole("heading", { level: 3, name: /maaliskuu 2026/ })).toBeVisible();
  await agenda.getByRole("button", { name: /^Board meeting,/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("complementary", { name: "Tapahtuman tiedot" }).getByRole("heading", { name: "Board meeting" })).toBeVisible();
});

test("a Viewer reads the agenda, and on a phone it fits the screen", async ({ context, page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-23" });
  const agenda = await open(page);
  await expect(agenda.getByRole("button", { name: /^Board meeting,/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "New Event" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const row = (await agenda.getByRole("button", { name: /^Board meeting,/ }).boundingBox())!;
  expect(row.height).toBeGreaterThanOrEqual(32);
  expect(await axe(page)).toEqual([]);
});
