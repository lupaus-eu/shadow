import { expect, test } from "@playwright/test";

import { apiBase, organizationId, plannerApi, yearclockPath } from "./support/yearclock-fixture";

test("a full Yearclock explains the Event limit instead of failing silently", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", events: [] });
  await context.route(new RegExp(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/[^/]+/events$`), (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({ status: 409, json: { detail: { reason: "limit_reached", limit: "events_per_yearclock", maximum: 3000 } } });
  });
  await page.goto(yearclockPath);
  const hit = page.locator(".yc-lane-hit").first();
  await hit.scrollIntoViewIfNeeded();
  const box = (await hit.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2 + 2, box.y + 6);
  const form = page.getByRole("form", { name: "New Event" });
  await form.getByLabel("Title").fill("One too many");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "reached its limit of 3000 Events" })).toBeVisible();
});
