import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const apiBase = "http://api.yearclock.test";

test("the sign-in card uses the design foundation, passes axe, and shows keyboard focus", async ({ context, page }) => {
  await context.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 401, json: {} }));
  await page.goto("/");
  const card = page.getByRole("region", { name: "Sign in to Yearclock" });
  await expect(card).toBeVisible();
  const action = card.getByRole("link", { name: "Continue with Authentik" });
  await expect(action).toHaveCSS("background-color", "rgb(15, 118, 110)");
  expect(await page.evaluate(() => getComputedStyle(document.body.querySelector("main")!).fontFamily)).toContain("Inter Variable");
  await page.keyboard.press("Tab");
  await expect(action).toBeFocused();
  await expect(action).toHaveCSS("outline-style", "solid");
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
});

test("session problems appear in the same card as alerts", async ({ context, page }) => {
  await context.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 500, json: {} }));
  await page.goto("/");
  await expect(page.getByRole("alert")).toHaveText("Yearclock is temporarily unavailable.");
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
});
