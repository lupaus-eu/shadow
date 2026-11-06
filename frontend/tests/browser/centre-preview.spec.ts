import { expect, test } from "@playwright/test";

import { plannerApi, sampleEvents, yearclockPath } from "./support/yearclock-fixture";

test("hovering or focusing an Event previews it in the centre without changing selection", async ({ context, page }) => {
  const events = sampleEvents();
  events[0] = { ...events[0], title: "Board meeting with a very long agenda title" };
  await plannerApi(context, { today: "2026-09-25", events });
  await page.goto(yearclockPath);
  const preview = page.locator(".yc-preview");
  await expect(preview).toHaveCount(0);
  await expect(page.locator(".yc-center-label")).toHaveText("Today");

  const board = page.getByRole("button", { name: /^Board meeting with a very long agenda title,/ });
  await board.hover();
  await expect(preview.locator(".yc-preview-title")).toHaveText("Board meeting with a…");
  await expect(preview.locator(".yc-preview-meta")).toHaveText(["10 Mar 2026", "Governance"]);
  expect(await preview.evaluate((node) => node.closest("[aria-hidden='true']") !== null)).toBe(true);
  await expect(page.locator(".yc-center-label")).toHaveCount(0);
  await page.mouse.move(5, 5);
  await expect(preview).toHaveCount(0);

  const audit = page.getByRole("button", { name: /^Audit period,/ });
  await audit.focus();
  await expect(preview.locator(".yc-preview-title")).toHaveText("Audit period");
  await expect(audit).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("complementary", { name: "Event details" })).toHaveCount(0);
  await page.keyboard.press("Tab");
  await expect(preview.locator(".yc-preview-title")).not.toHaveText("Audit period");
});

test("the preview works in a one-month window on a small screen", async ({ context, page }) => {
  const events = sampleEvents();
  events.push({ ...events[0], id: "e7777777-0000-4000-8000-000000000000", title: "Budget kickoff", starts_on: "2026-09-15", ends_on: null });
  await plannerApi(context, { today: "2026-09-25", events });
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto(yearclockPath);
  const toolbar = page.getByRole("group", { name: "Planning Window" });
  await toolbar.getByRole("radio", { name: "1 month", exact: true }).click();
  await toolbar.getByRole("button", { name: "Current period" }).click();
  const kickoff = page.getByRole("button", { name: /^Budget kickoff,/ });
  await kickoff.focus();
  await expect(page.locator(".yc-preview-title")).toHaveText("Budget kickoff");
  await expect(page.locator(".yc-preview-meta").first()).toHaveText(/15 Sept? 2026/);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
