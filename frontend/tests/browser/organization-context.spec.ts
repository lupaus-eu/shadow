import { expect, test, type BrowserContext } from "@playwright/test";

const apiBase = "http://api.yearclock.test";
const northwindId = "3ea19a50-62af-446f-a608-c2c3c99cbb92";
const contosoId = "981cfba1-17b4-4c06-868a-4d987da09392";

async function authenticatedContext(context: BrowserContext) {
  await context.route(`${apiBase}/api/v1/auth/session`, (route) =>
    route.fulfill({
      status: 200,
      json: {
        user_account: {
          id: "fc4dbf31-2fd3-43cf-bc95-96642b93b9eb",
          account_class: "customer",
          email: "consultant@example.com",
          display_name: "Consultant Example",
          locale: "en",
        },
      },
    }),
  );
  await context.route(`${apiBase}/api/v1/system/status`, (route) =>
    route.fulfill({
      status: 200,
      json: { status: "ok", database: "ready", schema_revision: "0004" },
    }),
  );
  await context.route(`${apiBase}/api/v1/organizations/${northwindId}`, (route) =>
    route.fulfill({
      status: 200,
      json: {
        organization: { id: northwindId, name: "Northwind" },
        membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null },
        yearclocks: [
          {
            id: "205fb875-dae5-4cad-ad5f-1c05bc1c745b",
            name: "Northwind Yearclock",
            lanes: [
              {
                id: "aa466c3d-1dd5-4c3e-99f2-e2bde6011448",
                name: "General",
              },
            ],
          },
        ],
      },
    }),
  );
  await context.route(`${apiBase}/api/v1/organizations/${contosoId}`, (route) =>
    route.fulfill({
      status: 200,
      json: {
        organization: { id: contosoId, name: "Contoso" },
        membership: { role: "admin" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null },
        yearclocks: [
          {
            id: "544bf29c-b321-4e42-a8bf-a10482ee2088",
            name: "Contoso Yearclock",
            lanes: [
              {
                id: "25368add-c1ad-4993-a3c2-63e1384f3620",
                name: "Management",
              },
            ],
          },
        ],
      },
    }),
  );
}

test("a customer with one membership enters it directly", async ({
  context,
  page,
}) => {
  await authenticatedContext(context);
  await context.route(`${apiBase}/api/v1/organizations`, (route) =>
    route.fulfill({
      status: 200,
      json: {
        organizations: [
          { id: northwindId, name: "Northwind", role: "owner" },
        ],
      },
    }),
  );

  await page.goto("/");

  await expect(page).toHaveURL(`/organizations/${northwindId}`);
  await expect(
    page.getByRole("heading", { name: "Northwind", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Organization Owner")).toBeVisible();
  await expect(
    page.getByRole("main").getByRole("link", { name: "Northwind Yearclock" }),
  ).toBeVisible();
  await expect(page.getByText("Lanes: General")).toBeVisible();
});

test("a customer selects between organizations and tabs keep explicit context", async ({
  context,
  page,
}) => {
  await authenticatedContext(context);
  await context.route(`${apiBase}/api/v1/organizations`, (route) =>
    route.fulfill({
      status: 200,
      json: {
        organizations: [
          { id: contosoId, name: "Contoso", role: "admin" },
          { id: northwindId, name: "Northwind", role: "owner" },
        ],
      },
    }),
  );

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Choose an organization" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Contoso Organization Admin" }),
  ).toHaveAttribute("href", `/organizations/${contosoId}`);
  await expect(
    page.getByRole("link", { name: "Northwind Organization Owner" }),
  ).toHaveAttribute("href", `/organizations/${northwindId}`);

  const northwindTab = await context.newPage();
  const contosoTab = await context.newPage();
  await Promise.all([
    northwindTab.goto(`/organizations/${northwindId}`),
    contosoTab.goto(`/organizations/${contosoId}`),
  ]);

  await expect(
    northwindTab.getByRole("heading", { name: "Northwind", exact: true }),
  ).toBeVisible();
  await expect(
    northwindTab.getByRole("main").getByRole("link", { name: "Northwind Yearclock" }),
  ).toBeVisible();
  await expect(northwindTab.getByText("Lanes: General")).toBeVisible();
  await expect(
    contosoTab.getByRole("heading", { name: "Contoso", exact: true }),
  ).toBeVisible();
  await expect(
    contosoTab.getByRole("main").getByRole("link", { name: "Contoso Yearclock" }),
  ).toBeVisible();
  await expect(contosoTab.getByText("Lanes: Management")).toBeVisible();
  await expect(northwindTab).toHaveURL(`/organizations/${northwindId}`);
  await expect(contosoTab).toHaveURL(`/organizations/${contosoId}`);
});
