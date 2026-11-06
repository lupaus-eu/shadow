import { expect, test, type Page } from "@playwright/test";

import { adminWorkspace, organizationId } from "./support/admin-fixture";
import { plannerApi, yearclockPath } from "./support/yearclock-fixture";

/** Buttons, fields, radios, and tabs shorter than 32 px on a desktop screen. */
const smallControls = (page: Page) => page.evaluate(() => [...document.querySelectorAll("main button, main input, main select, main [role=radio], main [role=tab], header button")]
  .filter((element) => {
    const box = element.getBoundingClientRect();
    return box.width > 0 && box.height > 0 && box.height < 31.5 && !/checkbox|radio|color/.test((element as HTMLInputElement).type ?? "") && !element.closest("svg");
  })
  .map((element) => `${element.tagName} ${(element.textContent ?? "").trim().slice(0, 30)} ${Math.round(element.getBoundingClientRect().height)}`));

test("controls are at least 32 px high on every administration page", async ({ context, page }) => {
  await adminWorkspace(context);
  for (const section of ["", "/admin/people", "/admin/groups", "/admin/yearclocks", "/admin/classification", "/admin/activity", "/admin/support", "/admin/agents", "/admin/billing", "/admin/settings"]) {
    await page.goto(`/organizations/${organizationId}${section}`);
    await expect(page.getByRole("main").getByRole("heading", { level: 2 }).first()).toBeVisible();
    expect({ section, small: await smallControls(page) }).toEqual({ section, small: [] });
  }
});

test("controls are at least 32 px high in the planner, its details, drawer, and settings", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ }).click();
  await expect(page.getByRole("complementary", { name: "Event details" })).toBeVisible();
  expect(await smallControls(page)).toEqual([]);
  await page.goto(`${yearclockPath}/settings`);
  await expect(page.getByRole("region", { name: "Lanes", exact: true })).toBeVisible();
  expect(await smallControls(page)).toEqual([]);
});
