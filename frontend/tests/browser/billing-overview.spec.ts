import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { adminWorkspace, organizationId } from "./support/admin-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const billing = `/organizations/${organizationId}/admin/billing`;
const seats = { purchased: 4, occupied: 3, reserved: 0, available: 1, version: 1, pending_change: null };
const invoice = (id: string, extra: Record<string, unknown> = {}) => ({ id, date: "2026-11-04T00:00:00Z", amount: 18000, currency: "eur", state: "paid", reason: "renewal", hosted_invoice_url: `https://invoice.stripe.test/${id}`, ...extra });

async function open(context: BrowserContext, answers: { nextCharge?: unknown; invoices?: unknown; subscription?: Record<string, unknown>; locale?: "en" | "fi" }) {
  await adminWorkspace(context, {
    locale: answers.locale,
    subscription: { current_period_end: "2026-12-04T00:00:00Z", ...answers.subscription },
    extra: async (route, path) => {
      if (path === "/billing/seats") { await route.fulfill({ status: 200, json: seats }); return true; }
      if (path === "/billing/next-charge") { await route.fulfill({ status: 200, json: answers.nextCharge }); return true; }
      if (path === "/billing/invoices") { await route.fulfill({ status: 200, json: answers.invoices }); return true; }
      return false;
    },
  });
}

test("the card shows the next charge with the seat rules, and the list shows the latest payments", async ({ context, page }) => {
  await open(context, {
    nextCharge: { status: "scheduled", charge_date: "2026-12-04T00:00:00Z", amount: 18000, currency: "eur", seats: 6 },
    invoices: { status: "ok", invoices: [invoice("in_1"), invoice("in_2", { state: "failed", reason: "seat_increase", amount: 3000 })] },
  });
  await page.goto(billing);
  const card = page.getByRole("region", { name: "Subscription" });
  await expect(card.getByText("€180.00 on 4 Dec 2026, for 6 seats.", { exact: false })).toBeVisible();
  await expect(card.getByText("Nothing is refunded.")).toBeVisible();
  const payments = page.getByRole("region", { name: "Payments" });
  await expect(payments.getByRole("row")).toHaveCount(3);
  await expect(payments.getByRole("row", { name: /Failed.*Seats added/ })).toBeVisible();
  await expect(payments.getByRole("link", { name: "View the invoice of 4 Nov 2026" }).first()).toHaveAttribute("href", "https://invoice.stripe.test/in_1");
  expect(await axe(page)).toEqual([]);
});

test("a scheduled cancellation and an unavailable Stripe each say so and the rest of the page works", async ({ context, page }) => {
  await open(context, {
    subscription: { cancel_at_period_end: true },
    nextCharge: { status: "none_cancelled", charge_date: null, amount: null, currency: null, seats: null },
    invoices: { status: "unavailable", invoices: [] },
  });
  await page.goto(billing);
  await expect(page.getByText("No further charge: the subscription ends at the end of the paid period.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Payments" }).getByText("could not be loaded from Stripe", { exact: false })).toBeVisible();
  await expect(page.getByRole("region", { name: "Seat capacity" })).toBeVisible();
  expect(await axe(page)).toEqual([]);
});

test("the overview is shown in Finnish and an empty list says so", async ({ context, page }) => {
  await open(context, {
    nextCharge: { status: "unavailable", charge_date: null, amount: null, currency: null, seats: null },
    invoices: { status: "ok", invoices: [] },
    locale: "fi",
  });
  await page.goto(billing);
  await expect(page.getByText("Seuraavaa veloitusta ei voitu ladata Stripestä juuri nyt.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Maksut" }).getByText("Laskuja ei ole vielä.")).toBeVisible();
});
