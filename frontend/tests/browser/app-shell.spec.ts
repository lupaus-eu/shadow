import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { adminWorkspace, organizationId } from "./support/admin-fixture";
import { plannerApi, yearclockPath } from "./support/yearclock-fixture";

const axe = (page: import("@playwright/test").Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));

test("the sidebar shows what each role may open and marks the current page", async ({ context, page }) => {
  await adminWorkspace(context, { role: "owner" });
  await page.goto(`/organizations/${organizationId}`);
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Northwind");
  await expect(nav.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  const admin = nav.getByRole("group", { name: "Administration" });
  await expect(admin.getByRole("link")).toHaveText(["People", "Groups", "Yearclocks and access", "Classification", "Activity", "Support Access", "Connect an agent", "Billing and seats", "Organization settings"]);
  await expect(nav.getByRole("group", { name: "Yearclocks" }).getByRole("link")).toHaveText(["Budget"]);
  expect(await axe(page)).toEqual([]);
  await expect(page).toHaveTitle("Northwind · Yearclock");
});

test("an Administrator has no billing or Organization settings, and a Member no administration", async ({ browser }) => {
  for (const [role, expected] of [["admin", ["People", "Groups", "Yearclocks and access", "Classification", "Activity", "Support Access", "Connect an agent"]], ["member", []]] as const) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await adminWorkspace(context, { role });
    await page.goto(`/organizations/${organizationId}`);
    const nav = page.getByRole("navigation", { name: "Main navigation" });
    await expect(nav.getByRole("link", { name: "Overview" })).toBeVisible();
    await expect(nav.getByRole("group", { name: "Administration" }).getByRole("link")).toHaveText([...expected]);
    await page.goto(`/organizations/${organizationId}/admin/billing`);
    await expect(page.getByRole("alert")).toHaveText("This page does not exist.");
    await context.close();
  }
});

test("administration pages have addresses, and back and forward move between them", async ({ context, page }) => {
  await adminWorkspace(context, { role: "owner" });
  await page.goto(`/organizations/${organizationId}/admin/people`);
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("People");
  await expect(nav.getByRole("link", { name: "People" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("region", { name: "People", exact: true })).toBeVisible();
  await nav.getByRole("link", { name: "Activity" }).click();
  await expect(page).toHaveURL(`/organizations/${organizationId}/admin/activity`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Activity");
  await page.goBack();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("People");
  await page.goForward();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Activity");
  await page.goto(`/organizations/${organizationId}/nowhere`);
  await expect(page.getByRole("alert")).toHaveText("This page does not exist.");
});

test("a Yearclock deep link opens inside the shell with its name as the page title", async ({ context, page }) => {
  await plannerApi(context);
  await page.goto(yearclockPath);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Northwind Yearclock");
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Northwind Yearclock" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "Events in this window" })).toBeVisible();
});

test("the skip link moves focus to the page, and the user menu holds language and sign out", async ({ context, page }) => {
  await adminWorkspace(context, { role: "owner" });
  await page.goto(`/organizations/${organizationId}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Northwind");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
  await page.getByRole("button", { name: "Account menu for Olivia Owner" }).click();
  const menu = page.getByRole("menu");
  await expect(menu.getByText("Signed in as Olivia Owner")).toBeVisible();
  await expect(menu.getByRole("menuitemradio")).toHaveText(["English", "Suomi"]);
  await expect(menu.getByRole("menuitem", { name: "Sign out" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
});

test("small screens open the navigation in a drawer that closes on navigation", async ({ context, page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await adminWorkspace(context, { role: "owner" });
  await page.goto(`/organizations/${organizationId}`);
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toHaveCount(0);
  await page.getByRole("button", { name: "Open navigation" }).click();
  const drawer = page.getByRole("dialog", { name: "Main navigation" });
  await expect(drawer).toBeVisible();
  expect(await axe(page)).toEqual([]);
  await drawer.getByRole("link", { name: "Groups" }).click();
  await expect(drawer).toHaveCount(0);
  await expect(page).toHaveURL(`/organizations/${organizationId}/admin/groups`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Groups");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
