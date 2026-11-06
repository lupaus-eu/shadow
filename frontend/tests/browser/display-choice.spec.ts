import { expect, test } from "@playwright/test";

import { plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";

test("the circle is the default display, and a stored choice that does not exist is ignored", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await context.addInitScript(`localStorage.setItem("yearclock.display.${yearclockId}", "gantt")`);
  await page.goto(yearclockPath);
  await expect(page.getByRole("group", { name: /Northwind Yearclock, January 2026/ })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Yearclock panel" }).getByRole("tab")).toHaveText(["Events", "Filters"]);
});

test("every display shows the same Events for the same window, and the choice is kept for this Yearclock only", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("radio", { name: "1 month", exact: true }).click();
  const names = async (display: string) => {
    await page.getByRole("radio", { name: display, exact: true }).click();
    const scope = display === "Circle" ? page.getByRole("group", { name: /Northwind Yearclock/ }) : page.getByRole("region", { name: "Events in this window" });
    return (await scope.getByRole("button").evaluateAll((buttons) => buttons.map((button) => button.getAttribute("aria-label")).filter(Boolean))).sort();
  };
  const circle = await names("Circle");
  expect(circle).toHaveLength(4);
  for (const display of ["Timeline", "List", "Agenda"]) expect(await names(display), display).toEqual(circle);
  await page.reload();
  await expect(page.getByRole("radio", { name: "Agenda", exact: true })).toHaveAttribute("aria-checked", "true");
  expect(await page.evaluate((id) => localStorage.getItem(`yearclock.display.${id}`), yearclockId)).toBe("agenda");
  expect(await page.evaluate(() => Object.keys(localStorage).filter((key) => key.startsWith("yearclock.display.")).length)).toBe(1);
});

test("the Display radio group moves and selects with the arrow keys", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  const group = page.getByRole("radiogroup", { name: "Display" });
  await group.getByRole("radio", { name: "Circle" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(group.getByRole("radio", { name: "Timeline" })).toBeFocused();
  await expect(group.getByRole("radio", { name: "Timeline" })).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(group.getByRole("radio", { name: "Agenda" })).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("ArrowRight");
  await expect(group.getByRole("radio", { name: "Circle" })).toHaveAttribute("aria-checked", "true");
});
