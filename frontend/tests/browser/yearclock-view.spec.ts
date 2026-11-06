import { expect, test } from "@playwright/test";

import { organizationId, plannerApi, yearclockPath } from "./support/yearclock-fixture";

test("the circular Yearclock draws point and range Events with an equivalent summary", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);

  const clock = page.getByRole("group", { name: "Northwind Yearclock, January 2026 to December 2026" });
  await expect(clock).toBeVisible();
  const point = clock.getByRole("button", { name: /^Board meeting, 10 Mar 2026, single day, Governance, Board/ });
  const range = clock.getByRole("button", { name: /^Audit period, 1 Apr 2026 – 15 May 2026, date range, Governance, Audit/ });
  await expect(point).toHaveJSProperty("tagName", "circle");
  await expect(range).toHaveJSProperty("tagName", "path");
  await expect(clock.getByRole("button", { name: /^Year-end close, .*continues into the next window/ })).toBeVisible();

  const summary = page.getByRole("region", { name: "Events in this window" });
  await expect(summary.getByRole("button", { name: /10 Mar 2026 Board meeting — Governance · Board/ })).toBeVisible();
  await expect(summary.getByRole("button", { name: /1 Apr 2026 – 15 May 2026 Audit period/ })).toBeVisible();

  await point.click();
  const details = page.getByRole("complementary", { name: "Event details" });
  await expect(details.getByRole("heading", { name: "Board meeting" })).toBeVisible();
  await expect(details.getByText("Budget approval")).toBeVisible();
  await expect(details.getByRole("link", { name: "https://example.com/agenda" })).toHaveAttribute("href", "https://example.com/agenda");
  await expect(details.getByRole("link", { name: "Board page" })).toHaveAttribute("href", "https://example.com/board");
  await expect(details.getByText("Room 4", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Events" }).click();
  await expect(summary.getByRole("button", { name: /Board meeting/ })).toHaveAttribute("aria-pressed", "true");
});

test("today, elapsed time, and month lengths follow the selected window", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await expect(page.getByText("Today", { exact: true })).toBeVisible();
  await expect(page.getByText("73% of this window has passed.")).toBeVisible();

  await page.getByRole("button", { name: "Next period" }).click();
  await expect(page.getByRole("group", { name: "Northwind Yearclock, January 2027 to December 2027" })).toBeVisible();
  await expect(page.getByText("Today", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/% of this window has passed/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Year-end close, .*continues from the previous window/ })).toBeVisible();

  await page.getByLabel("Start month").fill("2027-11");
  await expect(page.getByRole("group", { name: "Northwind Yearclock, November 2027 to October 2028" })).toBeVisible();
  await expect(page.getByText("Showing 1 Nov 2027 to 31 Oct 2028")).toBeVisible();

  const angles = await page.locator(".yc-month-line").evaluateAll((lines) =>
    lines.map((line) => Math.atan2(Number(line.getAttribute("x2")) - 200, 200 - Number(line.getAttribute("y2")))),
  );
  const febStart = angles[3];
  const marStart = angles[4];
  const janStart = angles[2];
  const february = (marStart - febStart + 2 * Math.PI) % (2 * Math.PI);
  const january = (febStart - janStart + 2 * Math.PI) % (2 * Math.PI);
  expect(february / january).toBeCloseTo(29 / 31, 2);
});

test("the Planning Window crosses a month boundary with the month buttons", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await page.getByRole("button", { name: "Previous month" }).click();
  await expect(page.getByRole("group", { name: "Northwind Yearclock, December 2025 to November 2026" })).toBeVisible();
  expect(requests.some((request) => request.path === "/events" && request.search.includes("window_start=2025-12-01"))).toBe(true);
});

test("a small screen keeps the circle inside the viewport and shows details below it", async ({ context, page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  const clock = page.getByRole("group", { name: /Northwind Yearclock/ });
  const box = (await clock.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(360);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  await page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ }).click();
  const sheet = page.getByRole("complementary", { name: "Event details" });
  const sheetBox = (await sheet.boundingBox())!;
  expect(sheetBox.x).toBeGreaterThanOrEqual(0);
  expect(sheetBox.x + sheetBox.width).toBeLessThanOrEqual(360);
  const circle = (await clock.boundingBox())!;
  expect(sheetBox.y).toBeGreaterThanOrEqual(circle.y + circle.height);
  await sheet.getByRole("button", { name: "Close" }).click();
  await expect(sheet).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Events" })).toHaveAttribute("aria-selected", "true");
});

test("a Viewer sees the same details without mutation controls", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-23" });
  await page.goto(yearclockPath);
  await expect(page.getByRole("button", { name: "New Event" })).toHaveCount(0);
  await page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ }).click();
  const details = page.getByRole("complementary", { name: "Event details" });
  await expect(details.getByText("Budget approval")).toBeVisible();
  await expect(details.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await expect(details.getByRole("button", { name: "Delete" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Yearclock settings" })).toHaveCount(0);
});

test("an Editor creates an Event by selecting a Lane position on the circle", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-23", events: [] });
  await page.goto(yearclockPath);
  const hit = page.locator(".yc-lane-hit").first();
  await hit.scrollIntoViewIfNeeded();
  const box = (await hit.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2 + 2, box.y + 6);
  const form = page.getByRole("form", { name: "New Event" });
  await expect(form.getByLabel("Start date")).toHaveValue("2026-01-01");
  await expect(form.getByLabel("Lane")).toHaveValue(/aa466c3d/);
  await form.getByLabel("Title").fill("Strategy day");
  await form.getByLabel("Location").fill("Main hall");
  await form.getByRole("button", { name: "Add link" }).click();
  await form.getByLabel("Link text").fill("Strategy");
  await form.getByLabel("Address").fill("ftp://example.com");
  await expect(form.getByText("Link 1 must be an address starting with http:// or https://.")).toBeVisible();
  await expect(form.getByRole("button", { name: "Save" })).toBeDisabled();
  await form.getByLabel("Address").fill("https://example.com/strategy");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
  const created = requests.find((request) => request.method === "POST" && request.path === "/events");
  expect(created?.body).toMatchObject({ title: "Strategy day", starts_on: "2026-01-01", lane_id: "aa466c3d-1dd5-4c3e-99f2-e2bde6011448", location: "Main hall", links: [{ title: "Strategy", url: "https://example.com/strategy" }] });
});

test("screenshot of the planner", async ({ context, page }) => {
  test.skip(!process.env.YEARCLOCK_SCREENSHOT_DIR, "set YEARCLOCK_SCREENSHOT_DIR to capture");
  await plannerApi(context, { today: "2026-09-23" });
  await page.setViewportSize({ width: 1280, height: 1400 });
  await page.goto(yearclockPath);
  await page.getByRole("group", { name: /Northwind Yearclock/ }).screenshot({ path: `${process.env.YEARCLOCK_SCREENSHOT_DIR}/planner.png` });
});
