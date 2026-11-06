import { expect, test } from "@playwright/test";

const apiBase = "http://api.yearclock.test";
const organizationId = "3ea19a50-62af-446f-a608-c2c3c99cbb92";

test("customer purchases seats and sees activation only after Stripe payment", async ({
  page,
}) => {
  let paymentCompleted = false;

  await page.route(`${apiBase}/api/v1/auth/session`, (route) =>
    route.fulfill({
      status: 200,
      json: {
        user_account: {
          id: "fc4dbf31-2fd3-43cf-bc95-96642b93b9eb",
          account_class: "customer",
          email: "owner@example.com",
          display_name: "Organization Owner",
          locale: "en",
        },
      },
    }),
  );
  await page.route(`${apiBase}/api/v1/system/status`, (route) =>
    route.fulfill({
      status: 200,
      json: { status: "ok", database: "ready", schema_revision: "0003" },
    }),
  );
  await page.route(`${apiBase}/api/v1/organizations`, (route) =>
    route.fulfill({ status: 200, json: { organizations: [] } }),
  );
  await page.route(`${apiBase}/api/v1/organization-signups`, async (route) => {
    const request = route.request().postDataJSON();
    expect(request).toMatchObject({
      organization_name: "Northwind Oy",
      time_zone: "Europe/Helsinki",
      default_locale: "en",
      billing_name: "Northwind Billing",
      billing_email: "billing@northwind.example",
      initial_seats: 3,
    });
    await route.fulfill({
      status: 201,
      json: {
        organization_id: organizationId,
        organization_name: "Northwind Oy",
        status: "pending_activation",
        initial_seats: 3,
        expires_at: "2026-07-30T09:00:00Z",
        checkout_url: `https://checkout.stripe.test/${organizationId}`,
        initial_content: null,
      },
    });
  });
  await page.route(`https://checkout.stripe.test/${organizationId}`, (route) => {
    return route.fulfill({
      status: 200,
      contentType: "text/html",
      body: `
        <main>
          <h1>Stripe Checkout</h1>
          <p>€30.00 × 3, billed monthly</p>
          <a href="https://checkout.stripe.test/${organizationId}/complete">
            Pay
          </a>
        </main>
      `,
    });
  });
  await page.route(
    `https://checkout.stripe.test/${organizationId}/complete`,
    (route) => {
      paymentCompleted = true;
      return route.fulfill({
        status: 303,
        headers: {
          location: `http://127.0.0.1:8174/organization-signups/${organizationId}?checkout=returned`,
        },
      });
    },
  );
  await page.route(
    `${apiBase}/api/v1/organization-signups/${organizationId}`,
    (route) =>
      route.fulfill({
        status: 200,
        json: {
          organization_id: organizationId,
          organization_name: "Northwind Oy",
          status: paymentCompleted ? "active" : "pending_activation",
          initial_seats: 3,
          expires_at: "2026-07-30T09:00:00Z",
          checkout_url: null,
          initial_content: paymentCompleted
            ? {
                owner_user_account_id:
                  "fc4dbf31-2fd3-43cf-bc95-96642b93b9eb",
                yearclock_id: "205fb875-dae5-4cad-ad5f-1c05bc1c745b",
                yearclock_name: "Yearclock",
                lane_id: "aa466c3d-1dd5-4c3e-99f2-e2bde6011448",
                lane_name: "General",
              }
            : null,
        },
      }),
  );

  await page.goto("/");
  await page.getByLabel("Organization name").fill("Northwind Oy");
  await page.getByLabel("IANA time zone").fill("Europe/Helsinki");
  await page.getByLabel("Billing name").fill("Northwind Billing");
  await page
    .getByLabel("Billing email")
    .fill("billing@northwind.example");
  await page.getByLabel("Seats").fill("3");

  await expect(page.getByText("3 × €30.00 per seat = €90.00 per month before tax, billed in advance")).toBeVisible();
  await expect(page.getByText("Tax is calculated at checkout and shown separately on the invoice.")).toBeVisible();
  await page.getByRole("button", { name: "Continue to secure checkout" }).click();

  await expect(page.getByRole("heading", { name: "Stripe Checkout" })).toBeVisible();
  await page.getByRole("link", { name: "Pay" }).click();

  await expect(
    page.getByRole("heading", { name: "Northwind Oy is active" }),
  ).toBeVisible();
  await expect(page.getByText("Owner seat: active")).toBeVisible();
  await expect(page.getByText("Yearclock · General")).toBeVisible();
});
