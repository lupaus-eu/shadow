import { expect, test } from "@playwright/test";

const apiBase = "http://api.yearclock.test";
const organizationId = "3ea19a50-62af-446f-a608-c2c3c99cbb92";
const planning = { id: "205fb875-dae5-4cad-ad5f-1c05bc1c745b", name: "Planning", version: 1, access_role: "editor", lanes: [{ id: "aa466c3d-1dd5-4c3e-99f2-e2bde6011448", name: "General", display_order: 0, version: 1 }] };
const board = { id: "544bf29c-b321-4e42-a8bf-a10482ee2088", name: "Board", version: 1, access_role: "viewer", lanes: [{ id: "25368add-c1ad-4993-a3c2-63e1384f3620", name: "Governance", display_order: 0, version: 1 }] };

test("an Editor gets mutation controls while a Viewer gets the same details read-only", async ({ context, page }) => {
  await context.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 200, json: { user_account: { id: "0d9c8b7a-6f5e-4d3c-2b1a-0f9e8d7c6b5a", account_class: "customer", email: "mika@example.com", display_name: "Mika Member", locale: "en" } } }));
  await context.route(`${apiBase}/api/v1/system/status`, (route) => route.fulfill({ status: 200, json: { status: "ok", database: "ready", schema_revision: "0021" } }));
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role: "member" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: [planning, board] } }));
  for (const clock of [planning, board]) {
    await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${clock.id}/events**`, (route) => route.fulfill({ status: 200, json: [{ id: `${clock.id.slice(0, 8)}-0000-4000-8000-000000000001`, lane_id: clock.lanes[0].id, category_id: null, title: `${clock.name} review`, description: "Agenda and minutes", location: null, links: [], starts_on: "2026-10-01", ends_on: null, version: 1 }] }));
    await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${clock.id}/deleted-events`, (route) => route.fulfill({ status: 200, json: [] }));
    await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${clock.id}/categories`, (route) => route.fulfill({ status: 200, json: [] }));
  }
  let managementRequests = 0;
  await context.route(new RegExp(`${apiBase}/api/v1/organizations/${organizationId}/(memberships|invitations|billing/seats|yearclocks\\?).*`), (route) => {
    managementRequests += 1;
    return route.fulfill({ status: 403, json: {} });
  });

  await page.goto(`/organizations/${organizationId}`);
  await expect(page.getByRole("region", { name: "Yearclocks" })).toHaveCount(0);
  await page.getByRole("main").getByRole("link", { name: "Planning" }).click();
  const editable = page.getByRole("region", { name: "Planning" });
  await editable.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Planning review/ }).click();
  await expect(editable.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit" })).toBeVisible();
  await expect(editable.getByRole("button", { name: "New Event" })).toBeVisible();
  await page.goto(`/organizations/${organizationId}/yearclocks/${board.id}`);
  const readOnly = page.getByRole("region", { name: "Board" });
  await readOnly.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board review/ }).click();
  const readOnlyDetails = readOnly.getByRole("complementary", { name: "Event details" });
  await expect(readOnlyDetails.getByText("Agenda and minutes")).toBeVisible();
  await expect(readOnly.getByRole("button", { name: "New Event" })).toHaveCount(0);
  await expect(readOnlyDetails.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await expect(readOnlyDetails.getByRole("button", { name: "Delete" })).toHaveCount(0);
  await expect(readOnly.getByRole("link", { name: "Yearclock settings" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Yearclocks" })).toHaveCount(0);
  expect(managementRequests).toBe(0);
});
