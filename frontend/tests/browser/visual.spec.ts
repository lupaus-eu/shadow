import { existsSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { adminWorkspace, organizationId } from "./support/admin-fixture";
import { plannerApi, yearclockPath } from "./support/yearclock-fixture";

// Baselines are committed per platform (`visual.spec.ts-snapshots/*-chromium-<platform>.png`) and updated
// deliberately with `npx playwright test visual --update-snapshots`. A platform without baselines skips.
test.beforeEach(({}, testInfo) => {
  const baseline = join(testInfo.snapshotDir, `overview-chromium-${process.platform}.png`);
  test.skip(!["all", "changed"].includes(testInfo.config.updateSnapshots) && !existsSync(baseline), `no visual baselines for ${process.platform}`);
});

const shot = { animations: "disabled" as const, caret: "hide" as const, maxDiffPixelRatio: 0.01 };

test("Organization overview", async ({ context, page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await adminWorkspace(context);
  await page.goto(`/organizations/${organizationId}`);
  await expect(page.getByRole("region", { name: "Open a Yearclock" })).toBeVisible();
  await expect(page.getByText("PostgreSQL ready · schema 0021")).toBeVisible();
  await expect(page).toHaveScreenshot("overview.png", shot);
});

test("planner", async ({ context, page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await expect(page.getByRole("heading", { name: "Events in this window" })).toBeVisible();
  await expect(page.getByText("PostgreSQL ready · schema 0021")).toBeVisible();
  await expect(page).toHaveScreenshot("planner.png", shot);
});

test("Event drawer", async ({ context, page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ }).click();
  await page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("dialog", { name: "Edit" }).getByLabel("Title")).toHaveValue("Board meeting");
  await expect(page).toHaveScreenshot("event-drawer.png", shot);
});

test("People administration page", async ({ context, page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await adminWorkspace(context);
  await page.goto(`/organizations/${organizationId}/admin/people`);
  await expect(page.getByRole("region", { name: "People", exact: true }).getByText("Sanna Sales", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("admin-people.png", shot);
});

test("planner on a phone", async ({ context, page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await expect(page.getByRole("heading", { name: "Events in this window" })).toBeVisible();
  await expect(page).toHaveScreenshot("planner-phone.png", { ...shot, fullPage: true });
});

test("timeline", async ({ context, page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("radio", { name: "Timeline", exact: true }).click();
  await page.getByRole("radio", { name: "6 months", exact: true }).click();
  await expect(page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /^Board meeting,/ })).toBeVisible();
  await expect(page.getByText("PostgreSQL ready · schema 0021")).toBeVisible();
  await expect(page).toHaveScreenshot("timeline.png", shot);
});

test("list on a phone", async ({ context, page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("radio", { name: "List", exact: true }).click();
  await expect(page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /^Board meeting,/ })).toBeVisible();
  await expect(page).toHaveScreenshot("list-phone.png", { ...shot, fullPage: true });
});
