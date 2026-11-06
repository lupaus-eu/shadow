import { expect, test } from "@playwright/test";

const apiBase = "http://api.yearclock.test";
const organizationId = "3ea19a50-62af-446f-a608-c2c3c99cbb92";

test("an Owner previews and confirms a payment-gated seat increase", async ({
  context,
  page,
}) => {
  await context.route(`${apiBase}/api/v1/auth/session`, (route) =>
    route.fulfill({
      status: 200,
      json: {
        user_account: {
          id: "fc4dbf31-2fd3-43cf-bc95-96642b93b9eb",
          account_class: "customer",
          email: "owner@example.com",
          display_name: "Owner Example",
          locale: "en",
        },
      },
    }),
  );
  await context.route(`${apiBase}/api/v1/system/status`, (route) =>
    route.fulfill({
      status: 200,
      json: { status: "ok", database: "ready", schema_revision: "0005" },
    }),
  );
  await context.route(
    `${apiBase}/api/v1/organizations/${organizationId}`,
    (route) =>
      route.fulfill({
        status: 200,
        json: {
          organization: { id: organizationId, name: "Northwind" },
          membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null },
          yearclocks: [],
        },
      }),
  );
  let projection = {
    purchased: 3,
    occupied: 1,
    reserved: 0,
    available: 2,
    version: 1,
    pending_change: null as null | {
      id: string;
      kind: string;
      status: string;
      target_seats: number;
      effective_at: null;
    },
  };
  await context.route(
    `${apiBase}/api/v1/organizations/${organizationId}/billing/seats`,
    async (route) => {
      if (route.request().method() === "POST") {
        expect(route.request().postDataJSON()).toEqual({
          target_seats: 5,
          expected_version: 1,
          preview_id: "upcoming_in_preview",
          confirmed: true,
        });
        projection = {
          ...projection,
          version: 2,
          pending_change: {
            id: "a3a70b4d-512a-43d7-a81d-534743a83d69",
            kind: "increase",
            status: "pending_payment",
            target_seats: 5,
            effective_at: null,
          },
        };
        await route.fulfill({ status: 202, json: projection });
        return;
      }
      await route.fulfill({ status: 200, json: projection });
    },
  );
  await context.route(
    `${apiBase}/api/v1/organizations/${organizationId}/billing/seats/increase-preview`,
    async (route) => {
      expect(route.request().postDataJSON()).toEqual({
        target_seats: 5,
        expected_version: 1,
      });
      await route.fulfill({
        status: 200,
        json: {
          preview_id: "upcoming_in_preview",
          target_seats: 5,
          amount_due: 1200,
          currency: "eur",
          proration_date: "2026-07-29T09:00:00Z",
        },
      });
    },
  );

  await page.goto(`/organizations/${organizationId}/admin/billing`);

  await expect(
    page.getByRole("heading", { name: "Seat capacity" }),
  ).toBeVisible();
  const seats = page.getByRole("region", { name: "Seat capacity" });
  await expect(seats.getByRole("term")).toHaveText(["Purchased", "Occupied", "Reserved", "Available"]);
  await expect(seats.getByRole("definition")).toHaveText(["3", "1", "0", "2"]);
  await page.getByRole("spinbutton", { name: "Purchased seats" }).fill("5");
  await page.getByRole("button", { name: "Preview increase" }).click();
  await expect(page.getByText("€12.00 due now")).toBeVisible();
  await page.getByRole("button", { name: "Confirm and pay" }).click();
  await expect(
    page.getByText("Waiting for Stripe to confirm payment for 5 seats."),
  ).toBeVisible();
  await expect(seats.getByRole("definition").first()).toHaveText("3");
});
