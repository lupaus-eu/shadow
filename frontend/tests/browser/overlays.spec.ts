import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { plannerApi, yearclockPath } from "./support/yearclock-fixture";

test("a confirmation is an accessible dialog: Escape cancels, focus returns, Enter confirms, success is a toast", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-25" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  const remove = page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Delete" });
  await remove.click();
  const dialog = page.getByRole("alertdialog", { name: /^Delete “Board meeting”/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Delete" })).toHaveCSS("background-color", "rgb(180, 35, 24)");
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  expect(await new AxeBuilder({ page }).include("[role=alertdialog]").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(remove).toBeFocused();
  expect(requests.some((item) => item.method === "DELETE")).toBe(false);

  await remove.click();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Delete" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => requests.some((item) => item.method === "DELETE")).toBe(true);
  const notifications = page.getByRole("region", { name: "Notifications" });
  await expect(notifications.getByRole("status")).toContainText("Event deleted. You can restore it for 30 days.");
  await notifications.getByRole("button", { name: "Dismiss" }).click();
  await expect(notifications.getByRole("status")).toHaveText("");
});
