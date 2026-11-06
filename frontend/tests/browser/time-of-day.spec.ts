import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { plannerApi, sampleEvents, yearclockPath } from "./support/yearclock-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));

function timedEvents() {
  const list = sampleEvents();
  list[0] = { ...list[0], starts_at: "14:00", ends_at: "16:00" } as (typeof list)[number];
  return [...list, { ...list[0], id: "e0000000-0000-4000-8000-0000000000aa", title: "Morning stand-up", starts_at: "08:30", ends_at: null, version: 1 } as (typeof list)[number], { ...list[0], id: "e0000000-0000-4000-8000-0000000000ab", title: "Open day", starts_at: null, ends_at: null, version: 1 } as (typeof list)[number]];
}

test("times show with the date in the panel, the list, the agenda, and the print list, and same-day Events are ordered", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", events: timedEvents() });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await expect(page.getByRole("complementary", { name: "Event details" }).getByText("10 Mar 2026, 14:00–16:00")).toBeVisible();
  await page.getByRole("radio", { name: "List" }).check();
  const rows = page.getByRole("table").getByRole("row").filter({ hasText: "10 Mar 2026" });
  await expect(rows.nth(0)).toContainText("Open day");
  await expect(rows.nth(1)).toContainText("Morning stand-up");
  await expect(rows.nth(1)).toContainText("08:30");
  await expect(rows.nth(2)).toContainText("Board meeting");
  await expect(rows.nth(2)).toContainText("14:00–16:00");
  await page.getByRole("radio", { name: "Agenda" }).check();
  await expect(page.locator(".yc-agenda-item").filter({ hasText: "Board meeting" })).toContainText("14:00–16:00");
  await page.getByRole("radio", { name: "Circle" }).check();
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".yc-print-events").getByText("10 Mar 2026, 14:00–16:00")).toBeVisible();
});

test("the editor offers optional start and end times, ties the end to the start, and sends them", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-23" });
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit", exact: true }).click();
  const form = page.getByRole("form", { name: "Edit" });
  await expect(form.getByLabel("End time (optional)")).toBeDisabled();
  await form.getByLabel("Start time (optional)").fill("14:00");
  await expect(form.getByLabel("End time (optional)")).toBeEnabled();
  await form.getByLabel("End time (optional)").fill("13:00");
  await expect(form.getByText("The end time must be after the start time.")).toBeVisible();
  await expect(form.getByRole("button", { name: "Save" })).toBeDisabled();
  expect(await axe(page)).toEqual([]);
  await form.getByLabel("End time (optional)").fill("15:30");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
  expect(requests.find((request) => request.method === "PATCH")?.body).toMatchObject({ starts_at: "14:00", ends_at: "15:30" });
});

test("on a longer Event the end time may be earlier than the start time, and clearing the start clears the end", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-23" });
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Audit period,/ }).click();
  await page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit", exact: true }).click();
  const form = page.getByRole("form", { name: "Edit" });
  await form.getByLabel("Start time (optional)").fill("14:00");
  await form.getByLabel("End time (optional)").fill("10:00");
  await expect(form.getByText("The end time must be after the start time.")).toHaveCount(0);
  await form.getByLabel("Start time (optional)").fill("");
  await expect(form.getByLabel("End time (optional)")).toHaveValue("");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
  expect(requests.find((request) => request.method === "PATCH")?.body).toMatchObject({ starts_at: null, ends_at: null });
});

test("the time fields and the history field names are in Finnish", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", locale: "fi" });
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: "Uusi tapahtuma" }).click();
  const form = page.getByRole("form", { name: "Uusi tapahtuma" });
  await expect(form.getByLabel("Alkamisaika (valinnainen)")).toBeVisible();
  await expect(form.getByLabel("Päättymisaika (valinnainen)")).toBeDisabled();
});
