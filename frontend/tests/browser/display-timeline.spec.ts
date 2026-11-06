import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { lanes, plannerApi, yearclockPath } from "./support/yearclock-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const open = async (page: Page, query = "?window_start=2026-01-01") => {
  await page.goto(`${yearclockPath}${query}`);
  await page.getByRole("radiogroup", { name: "Display" }).getByRole("radio", { name: "Timeline" }).click();
  return page.getByRole("region", { name: "Events in this window" });
};

test("the timeline draws each Lane as a named row with the circle's Events and accessible names", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const timeline = await open(page);
  await expect(timeline.getByRole("group", { name: lanes[0].name }).getByRole("button", { name: /^Board meeting, 10 Mar 2026, single day, Governance, Board/ })).toBeVisible();
  await expect(timeline.getByRole("group", { name: lanes[0].name }).getByRole("button", { name: /^Audit period, 1 Apr 2026 – 15 May 2026, date range, Governance, Audit/ })).toBeVisible();
  await expect(timeline.getByRole("group", { name: lanes[1].name }).getByRole("button", { name: /^Year-end close, .*continues into the next window/ })).toBeVisible();
  const inTimeline = await timeline.getByRole("button").count();
  await page.getByRole("radio", { name: "Circle", exact: true }).click();
  expect(await page.getByRole("group", { name: /Northwind Yearclock, January 2026/ }).getByRole("button").count()).toBe(inTimeline);
  await page.getByRole("radio", { name: "Timeline" }).click();
  await expect(page.locator(".yc-timeline-today")).toHaveCount(2);
  await expect(page.locator(".yc-timeline .yc-series-label")).toHaveText("Weekly finance check");
  expect(await axe(page)).toEqual([]);
});

test("choosing a marker or bar selects the Event and opens Details, and the selection follows the display", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const timeline = await open(page);
  await timeline.getByRole("button", { name: /^Audit period,/ }).click();
  await expect(page.getByRole("complementary", { name: "Event details" }).getByRole("heading", { name: "Audit period" })).toBeVisible();
  await expect(timeline.getByRole("button", { name: /^Audit period,/ })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("radio", { name: "Circle", exact: true }).click();
  await expect(page.getByRole("group", { name: /Northwind Yearclock/ }).getByRole("button", { name: /^Audit period,/ })).toHaveAttribute("aria-pressed", "true");
});

test("an Editor starts a new Event by choosing an empty day on a Lane; a Viewer cannot", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const timeline = await open(page);
  const track = timeline.getByRole("group", { name: lanes[0].name }).locator("> div").nth(1);
  const box = (await track.boundingBox())!;
  await track.click({ position: { x: box.width * 0.5, y: 6 } });
  const form = page.getByRole("dialog", { name: "New Event" });
  await expect(form.getByLabel("Start date")).toHaveValue("2026-07-02");
  await expect(form.getByLabel("Lane")).toHaveValue(lanes[0].id);
  await form.getByRole("button", { name: "Cancel" }).click();
  await expect(form).toHaveCount(0);
});

test("a Viewer's timeline has no creation by day", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-23" });
  const timeline = await open(page);
  const track = timeline.getByRole("group", { name: lanes[0].name }).locator("> div").nth(1);
  const box = (await track.boundingBox())!;
  await track.click({ position: { x: box.width * 0.5, y: 6 } });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(timeline.getByRole("button", { name: /^Board meeting,/ })).toBeVisible();
});

test("the axis follows the window length: months, weeks for 3 months, days for 1 month, and wide windows scroll inside", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const timeline = await open(page);
  await expect(timeline.locator("[aria-hidden=true]").getByText("Jan", { exact: true }).first()).toBeVisible();
  await page.getByRole("radio", { name: "3 months", exact: true }).click();
  await expect(timeline.locator("[aria-hidden=true]").getByText("Jan", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "1 month", exact: true }).click();
  await expect(timeline.locator("[aria-hidden=true]").getByText("January 2026")).toBeVisible();
  await expect(timeline.locator("[aria-hidden=true]").getByText("31", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "24 months", exact: true }).click();
  const scroll = page.locator("[data-timeline-scroll]");
  expect(await scroll.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("the keyboard reaches markers and bars in Lane order, and Enter selects", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const timeline = await open(page);
  const board = timeline.getByRole("button", { name: /^Board meeting,/ });
  await board.focus();
  await page.keyboard.press("Tab");
  await expect(timeline.getByRole("button", { name: /^Audit period,/ })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(timeline.getByRole("button", { name: /^Audit period,/ })).toHaveAttribute("aria-pressed", "true");
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  test("the timeline scrolls inside its container with touch-sized targets", async ({ context, page }) => {
    await plannerApi(context, { today: "2026-09-23" });
    const timeline = await open(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const bar = (await timeline.getByRole("button", { name: /^Audit period,/ }).boundingBox())!;
    expect(bar.height).toBeGreaterThanOrEqual(40);
    const dot = (await timeline.getByRole("button", { name: /^Weekly finance check, 5 Jan 2026/ }).boundingBox())!;
    expect(dot.height).toBeGreaterThanOrEqual(44);
    expect(await axe(page)).toEqual([]);
  });
});
