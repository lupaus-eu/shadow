import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { adminWorkspace, organizationId } from "./support/admin-fixture";
import { plannerApi, yearclockPath } from "./support/yearclock-fixture";

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

/** Horizontal overflow and the touch targets under 44 px in the page and top bar (card links use the whole card). */
async function phoneCheck(page: Page) {
  return page.evaluate(() => {
    const overflow = document.documentElement.scrollWidth - window.innerWidth;
    const small = [...document.querySelectorAll("main a, main button, main input, main select, header button, header a")]
      .filter((element) => {
        const box = element.getBoundingClientRect();
        const type = (element as HTMLInputElement).type ?? "";
        const coversCard = element.tagName === "A" && getComputedStyle(element, "::after").position === "absolute";
        return box.width > 0 && box.height > 0 && box.height < 44 && !/checkbox|radio|color/.test(type) && !coversCard && !element.closest("svg");
      })
      .map((element) => `${element.tagName} ${(element.textContent ?? "").trim().slice(0, 30)}`);
    return { overflow, small };
  });
}

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));

test("administration pages fit a phone with touch-sized controls", async ({ context, page }) => {
  await adminWorkspace(context);
  for (const section of ["", "/admin/people", "/admin/groups", "/admin/yearclocks", "/admin/classification", "/admin/activity", "/admin/support", "/admin/agents", "/admin/billing", "/admin/settings"]) {
    await page.goto(`/organizations/${organizationId}${section}`);
    await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("");
    await expect(page.getByRole("main").getByRole("heading", { level: 2 }).first()).toBeVisible();
    expect({ section, ...(await phoneCheck(page)) }).toEqual({ section, overflow: 0, small: [] });
  }
});

test("the planner, the drawer, and settings work on a phone", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await expect(page.getByRole("heading", { name: "Events in this window" })).toBeVisible();
  expect(await phoneCheck(page)).toEqual({ overflow: 0, small: [] });
  await page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ }).tap();
  const details = page.getByRole("complementary", { name: "Event details" });
  await expect(details.getByRole("heading", { name: "Board meeting" })).toBeVisible();
  await details.getByRole("button", { name: "Edit" }).tap();
  const drawer = page.getByRole("dialog", { name: "Edit" });
  expect((await drawer.boundingBox())!.width).toBe(390);
  expect(await axe(page)).toEqual([]);
  await drawer.getByRole("button", { name: "Cancel" }).tap();
  await page.getByRole("link", { name: "Yearclock settings" }).tap();
  await expect(page.getByRole("region", { name: "Lanes", exact: true })).toBeVisible();
  expect(await phoneCheck(page)).toEqual({ overflow: 0, small: [] });
});

test("the navigation drawer and account menu work by touch", async ({ context, page }) => {
  await adminWorkspace(context);
  await page.goto(`/organizations/${organizationId}`);
  await page.getByRole("button", { name: "Open navigation" }).tap();
  await page.getByRole("dialog", { name: "Main navigation" }).getByRole("link", { name: "Activity" }).tap();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Activity");
  await page.getByRole("button", { name: "Account menu for Olivia Owner" }).tap();
  const item = page.getByRole("menuitem", { name: "Sign out" });
  expect((await item.boundingBox())!.height).toBeGreaterThanOrEqual(44);
});
