import { expect, test } from "@playwright/test";

import { apiBase, organizationId, plannerApi, yearclockPath } from "./support/yearclock-fixture";

test("a failed renewal shows the grace deadline while editing continues", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", subscription: { state: "grace", writable: true, grace_expires_at: "2026-09-30T09:00:00Z" } });
  await page.goto(yearclockPath);
  await expect(page.getByRole("alert").filter({ hasText: "A renewal payment failed. Everything keeps working until 30 September 2026" })).toBeVisible();
  await expect(page.getByRole("button", { name: "New Event" })).toBeVisible();
});

test("a read-only Organization keeps content visible and hides editing", async ({ context, page }) => {
  await plannerApi(context, { role: "admin", today: "2026-09-23", subscription: { state: "read_only", writable: false } });
  await page.goto(yearclockPath);
  await expect(page.getByRole("alert").filter({ hasText: "This Organization is read-only" })).toBeVisible();
  await expect(page.getByText("Ask an Organization Owner to resolve billing.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "New Event" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Yearclocks" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Invite people" })).toHaveCount(0);
});

test("an Owner opens the billing portal, also while read-only", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", subscription: { state: "read_only", writable: false } });
  let portalRequests = 0;
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/billing/portal`, (route) => {
    portalRequests += 1;
    expect(route.request().method()).toBe("POST");
    return route.fulfill({ status: 200, json: { url: "https://billing.stripe.test/session/demo" } });
  });
  await context.route("https://billing.stripe.test/**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<title>Stripe portal</title><h1>Stripe portal</h1>" }));
  await page.goto(yearclockPath);
  await page.getByRole("button", { name: "Manage billing" }).click();
  await expect(page).toHaveURL("https://billing.stripe.test/session/demo");
  expect(portalRequests).toBe(1);
});

test("a scheduled cancellation states when the subscription ends", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", subscription: { cancel_at_period_end: true, current_period_end: "2026-10-15T00:00:00Z" } });
  await page.goto(yearclockPath);
  await expect(page.getByText("The subscription is cancelled and ends on 15 October 2026. Content stays")).toBeVisible();
  await expect(page.getByRole("button", { name: "New Event" })).toBeVisible();
});
