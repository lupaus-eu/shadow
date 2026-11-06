import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { adminWorkspace, organizationId } from "./support/admin-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const billing = `/organizations/${organizationId}/admin/billing`;

test("an Owner cancels at the end of the period after reading what happens, and the card shows the end date", async ({ context, page }) => {
  const calls: unknown[] = [];
  await adminWorkspace(context, {
    subscription: { current_period_end: "2026-11-04T00:00:00Z" },
    extra: async (route, path) => {
      if (path === "/billing/cancel") { calls.push(route.request().postDataJSON()); await route.fulfill({ status: 200, json: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: true, current_period_end: "2026-11-04T00:00:00Z", released_seat_decrease: false } }); return true; }
      if (path === "/billing/seats") { await route.fulfill({ status: 200, json: { purchased: 4, occupied: 3, reserved: 0, available: 1, version: 1, pending_change: null } }); return true; }
      return false;
    },
  });
  await page.goto(billing);
  const card = page.getByRole("region", { name: "Subscription" });
  await expect(card.getByText("Active. The next payment is on 4 November 2026.")).toBeVisible();
  await card.getByRole("button", { name: "Cancel subscription" }).click();
  const dialog = page.getByRole("dialog", { name: "Cancel the subscription?" });
  await expect(dialog.getByText("on 4 November 2026")).toBeVisible();
  await expect(dialog.getByText("Nothing is deleted, and an Owner can subscribe again.", { exact: false })).toBeVisible();
  await expect(dialog.getByText("A scheduled seat decrease is released")).toBeVisible();
  expect(await axe(page)).toEqual([]);
  await dialog.getByLabel("Why are you cancelling? (optional)").selectOption("switching");
  await dialog.getByRole("button", { name: "Cancel subscription" }).click();
  expect(calls).toEqual([{ reason: "switching" }]);
  await expect(page.getByText("The subscription ends on 4 November 2026.")).toBeVisible();
});

test("a scheduled cancellation shows its end date and can be undone", async ({ context, page }) => {
  let undone = 0;
  await adminWorkspace(context, {
    subscription: { cancel_at_period_end: true, current_period_end: "2026-11-04T00:00:00Z" },
    extra: async (route, path) => {
      if (path === "/billing/cancel/undo") { undone += 1; await route.fulfill({ status: 200, json: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: "2026-11-04T00:00:00Z", released_seat_decrease: false } }); return true; }
      if (path === "/billing/seats") { await route.fulfill({ status: 200, json: { purchased: 4, occupied: 3, reserved: 0, available: 1, version: 1, pending_change: null } }); return true; }
      return false;
    },
  });
  await page.goto(billing);
  const card = page.getByRole("region", { name: "Subscription" });
  await expect(card.getByText("Cancellation scheduled: the subscription ends on 4 November 2026.")).toBeVisible();
  await expect(card.getByRole("button", { name: "Cancel subscription" })).toHaveCount(0);
  await card.getByRole("button", { name: "Undo cancellation" }).click();
  await expect(page.getByText("The cancellation was undone. The subscription continues.")).toBeVisible();
  expect(undone).toBe(1);
});

test("a failure stays in the dialog and Finnish texts are used", async ({ context, page }) => {
  await adminWorkspace(context, {
    locale: "fi",
    extra: async (route, path) => {
      if (path === "/billing/cancel") { await route.fulfill({ status: 502, json: { detail: "unable to change the subscription" } }); return true; }
      if (path === "/billing/seats") { await route.fulfill({ status: 200, json: { purchased: 4, occupied: 3, reserved: 0, available: 1, version: 1, pending_change: null } }); return true; }
      return false;
    },
  });
  await page.goto(billing);
  await page.getByRole("button", { name: "Peruuta tilaus" }).click();
  const dialog = page.getByRole("dialog", { name: "Peruutetaanko tilaus?" });
  await dialog.getByRole("button", { name: "Peruuta tilaus" }).click();
  await expect(dialog.getByRole("alert")).toHaveText("Tilausta ei voitu muuttaa. Yritä uudelleen.");
  await dialog.getByRole("button", { name: "Pidä tilaus" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("an ended subscription offers to subscribe again with at least the current people, and waits after Checkout", async ({ context, page }) => {
  const asked: unknown[] = [];
  await adminWorkspace(context, {
    subscription: { state: "read_only", writable: false, ended: true },
    extra: async (route, path) => {
      if (path === "/billing/resubscribe") { asked.push(route.request().postDataJSON()); await route.fulfill({ status: 200, json: { url: "http://checkout.test/resub" } }); return true; }
      if (path === "/billing/seats") { await route.fulfill({ status: 200, json: { purchased: 4, occupied: 3, reserved: 1, available: 0, version: 1, pending_change: null } }); return true; }
      return false;
    },
  });
  await page.route("http://checkout.test/**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<title>Checkout</title>" }));
  await page.goto(billing);
  const card = page.getByRole("region", { name: "Subscription" });
  await expect(card.getByText("The subscription has ended. The Organization is read-only and its content is kept.")).toBeVisible();
  await expect(card.getByRole("button", { name: "Cancel subscription" })).toHaveCount(0);
  await expect(card.getByLabel("Seats")).toHaveValue("4");
  await expect(card.getByText("At least 4, the people and invitations the Organization has now.")).toBeVisible();
  expect(await axe(page)).toEqual([]);
  await card.getByLabel("Seats").fill("3");
  await expect(card.getByRole("button", { name: "Continue to payment" })).toBeDisabled();
  await card.getByLabel("Seats").fill("6");
  await card.getByRole("button", { name: "Continue to payment" }).click();
  await page.waitForURL("http://checkout.test/**");
  expect(asked).toEqual([{ seats: 6 }]);
});

test("coming back from Checkout says the payment is being confirmed, and the notice for everyone says the subscription ended", async ({ context, page }) => {
  await adminWorkspace(context, {
    subscription: { state: "read_only", writable: false, ended: true },
    extra: async (route, path) => { if (path === "/billing/seats") { await route.fulfill({ status: 200, json: { purchased: 4, occupied: 3, reserved: 0, available: 1, version: 1, pending_change: null } }); return true; } return false; },
  });
  await page.goto(`${billing}?checkout=returned`);
  await expect(page.getByText("Waiting for the payment to be confirmed. This page updates by itself.")).toBeVisible();
  await page.goto(`/organizations/${organizationId}/admin/people`);
  await expect(page.getByText("because its subscription has ended")).toBeVisible();
});

test("the billing contact is edited here and saved, with a notice about what happens", async ({ context, page }) => {
  const saved: unknown[] = [];
  await adminWorkspace(context, {
    extra: async (route, path) => {
      if (path === "/billing/contact" && route.request().method() === "PUT") { saved.push(route.request().postDataJSON()); await route.fulfill({ status: 200, json: route.request().postDataJSON() }); return true; }
      if (path === "/billing/seats") { await route.fulfill({ status: 200, json: { purchased: 4, occupied: 3, reserved: 0, available: 1, version: 1, pending_change: null } }); return true; }
      return false;
    },
  });
  await page.goto(billing);
  const card = page.getByRole("region", { name: "Billing contact" });
  await expect(card.getByText("the old address gets a short notice", { exact: false })).toBeVisible();
  await expect(card.getByLabel("Billing email")).toHaveValue("billing@example.com");
  await expect(card.getByRole("button", { name: "Save billing contact" })).toBeDisabled();
  expect(await axe(page)).toEqual([]);
  await card.getByLabel("Billing email").fill("not an address");
  await expect(card.getByRole("button", { name: "Save billing contact" })).toBeDisabled();
  await card.getByLabel("Billing email").fill("finance@example.org");
  await card.getByLabel("Billing name").fill("Northwind Oy");
  await card.getByRole("button", { name: "Save billing contact" }).click();
  await expect(page.getByText("Billing contact saved.")).toBeVisible();
  expect(saved).toEqual([{ billing_name: "Northwind Oy", billing_email: "finance@example.org" }]);
});

test("a rate limit and a failure show where they happen, in Finnish too", async ({ context, page }) => {
  let status = 429;
  await adminWorkspace(context, {
    locale: "fi",
    extra: async (route, path) => {
      if (path === "/billing/contact" && route.request().method() === "PUT") { await route.fulfill({ status, json: { detail: { reason: "rate_limited", retry_after_seconds: 7300 } } }); return true; }
      if (path === "/billing/seats") { await route.fulfill({ status: 200, json: { purchased: 4, occupied: 3, reserved: 0, available: 1, version: 1, pending_change: null } }); return true; }
      return false;
    },
  });
  await page.goto(billing);
  const card = page.getByRole("region", { name: "Laskutusyhteys" });
  await card.getByLabel("Laskutusnimi").fill("Northwind Oy");
  await card.getByRole("button", { name: "Tallenna laskutusyhteys" }).click();
  await expect(card.getByRole("alert")).toHaveText("Laskutusyhteyttä on muutettu liian usein. Yritä uudelleen noin 3 tunnin kuluttua.");
  status = 502;
  await card.getByRole("button", { name: "Tallenna laskutusyhteys" }).click();
  await expect(card.getByRole("alert")).toHaveText("Laskutusyhteyttä ei voitu tallentaa. Yritä uudelleen.");
});
