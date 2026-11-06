import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { categories, lanes, plannerApi, sampleEvents, yearclockPath } from "./support/yearclock-fixture";

function created(requests: Awaited<ReturnType<typeof plannerApi>>) {
  return requests.filter((item) => item.method === "POST" && item.path === "/events").map((item) => item.body as Record<string, unknown>);
}

test("Duplicate opens a prefilled create form and saves nothing until Save", async ({ context, page }) => {
  const events = sampleEvents();
  events[0] = { ...events[0], label_ids: [] };
  const requests = await plannerApi(context, { today: "2026-09-25", events });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await page.getByRole("button", { name: "Duplicate" }).click();
  const form = page.getByRole("form", { name: "New Event" });
  await expect(form.getByLabel("Title")).toHaveValue("Board meeting");
  await expect(form.getByLabel("Start date")).toHaveValue("2026-03-10");
  await expect(form.getByRole("combobox", { name: "Lane" })).toHaveValue(lanes[0].id);
  await expect(form.getByRole("combobox", { name: "Category" })).toHaveValue(categories[0].id);
  await expect(form.getByLabel("Link text")).toHaveValue("Board page");
  await expect(form.getByLabel("Address")).toHaveValue("https://example.com/board");
  await expect(form.getByLabel("Location")).toHaveValue("Room 4");
  expect(created(requests)).toEqual([]);
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);

  await form.getByLabel("Start date").fill("2026-03-17");
  await form.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => created(requests).length).toBe(1);
  expect(created(requests)[0]).toMatchObject({ title: "Board meeting", starts_on: "2026-03-17", lane_id: lanes[0].id, category_id: categories[0].id, location: "Room 4", links: [{ title: "Board page", url: "https://example.com/board" }], origin: "duplicate" });
});

test("Plan again next year moves the dates, and an Occurrence duplicates as a single Event", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-25" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Audit period,/ }).click();
  await page.getByRole("button", { name: "Plan again next year" }).click();
  const form = page.getByRole("form", { name: "New Event" });
  await expect(form.getByLabel("Start date")).toHaveValue("2027-04-01");
  await expect(form.getByLabel("End date")).toHaveValue("2027-05-15");
  await form.getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("button", { name: /^Weekly finance check,/ }).first().click();
  await page.getByRole("button", { name: "Duplicate" }).click();
  await expect(form.getByRole("combobox", { name: "Repeat" })).toHaveValue("");
  await form.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => created(requests).length).toBe(1);
  expect(created(requests)[0]).toMatchObject({ title: "Weekly finance check", starts_on: "2026-01-05", origin: "duplicate" });
  expect(requests.some((item) => item.method === "POST" && item.path === "/series")).toBe(false);
});

test("Viewers are not offered Duplicate or Plan again", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-25" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await expect(page.getByRole("complementary", { name: "Event details" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Duplicate" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Plan again next year" })).toHaveCount(0);
});

test("a read-only Organization does not offer Duplicate or Plan again", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-25", subscription: { state: "canceled", writable: false } });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await expect(page.getByRole("complementary", { name: "Event details" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Duplicate" })).toHaveCount(0);
});
