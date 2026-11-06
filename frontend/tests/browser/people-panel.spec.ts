import { expect, test, type BrowserContext } from "@playwright/test";
import { answerConfirm } from "./support/confirm";

const apiBase = "http://api.yearclock.test";
const organizationId = "3ea19a50-62af-446f-a608-c2c3c99cbb92";
const ownerMembership = { id: "6b1f2a9e-0c3d-4b5a-9e8f-1a2b3c4d5e6f", user_account_id: "fc4dbf31-2fd3-43cf-bc95-96642b93b9eb", email: "owner@example.com", display_name: "Olivia Owner", role: "owner", version: 1 };
const memberMembership = { id: "7c2e3b0f-1d4e-4c6b-8f9a-2b3c4d5e6f70", user_account_id: "0d9c8b7a-6f5e-4d3c-2b1a-0f9e8d7c6b5a", email: "mika@example.com", display_name: "Mika Member", role: "member", version: 1 };

async function workspace(context: BrowserContext, role: "owner" | "admin" | "member") {
  await context.route(`${apiBase}/api/v1/auth/session`, (route) =>
    route.fulfill({ status: 200, json: { user_account: { id: ownerMembership.user_account_id, account_class: "customer", email: "owner@example.com", display_name: "Olivia Owner", locale: "en" } } }),
  );
  await context.route(`${apiBase}/api/v1/system/status`, (route) =>
    route.fulfill({ status: 200, json: { status: "ok", database: "ready", schema_revision: "0021" } }),
  );
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) =>
    route.fulfill({ status: 200, json: { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: [] } }),
  );
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/billing/seats`, (route) =>
    route.fulfill({ status: 200, json: { purchased: 3, occupied: 2, reserved: 0, available: 1, version: 1, pending_change: null } }),
  );
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/invitations`, (route) =>
    route.fulfill({ status: 200, json: [] }),
  );
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks?include_archived=true`, (route) =>
    route.fulfill({ status: 200, json: [] }),
  );
}

test("an Owner changes a role and removes a member, and the final Owner is protected", async ({ context, page }) => {
  await workspace(context, "owner");
  let members = [ownerMembership, { ...memberMembership }];
  const requests: string[] = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/memberships**`, async (route) => {
    const request = route.request();
    requests.push(`${request.method()} ${new URL(request.url()).pathname}`);
    if (request.method() === "PATCH") {
      expect(request.postDataJSON()).toEqual({ role: "admin", expected_version: 1 });
      members = [ownerMembership, { ...memberMembership, role: "admin", version: 2 }];
      await route.fulfill({ status: 200, json: members[1] });
      return;
    }
    if (request.method() === "DELETE") {
      expect(new URL(request.url()).searchParams.get("expected_version")).toBe("2");
      members = [ownerMembership];
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({ status: 200, json: members });
  });

  await page.goto(`/organizations/${organizationId}/admin/people`);
  const people = page.getByRole("region", { name: "People", exact: true });
  await expect(people.getByText("Mika Member", { exact: true })).toBeVisible();
  await expect(people.getByText("The only Owner: transfer ownership")).toBeVisible();
  await expect(people.getByRole("button", { name: "Remove Olivia Owner" })).toHaveCount(0);

  await people.getByLabel("People: Mika Member").selectOption("admin");
  await expect(people.getByLabel("People: Mika Member")).toHaveValue("admin");
  await people.getByRole("button", { name: "Remove Mika Member" }).click();
  await answerConfirm(page);
  await expect(people.getByText("Mika Member", { exact: true })).toHaveCount(0);
  expect(requests).toContain(`PATCH /api/v1/organizations/${organizationId}/memberships/${memberMembership.id}`);
  expect(requests).toContain(`DELETE /api/v1/organizations/${organizationId}/memberships/${memberMembership.id}`);
});

test("a Member sees neither the People panel nor invitations", async ({ context, page }) => {
  await workspace(context, "member");
  let membershipRequests = 0;
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/memberships**`, (route) => {
    membershipRequests += 1;
    return route.fulfill({ status: 403, json: { detail: "Organization management role required" } });
  });

  await page.goto(`/organizations/${organizationId}`);
  await expect(page.getByRole("heading", { name: "Northwind", exact: true })).toBeVisible();
  await expect(page.getByText("Member", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "People" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Invite people" })).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "People" })).toHaveCount(0);
  await page.goto(`/organizations/${organizationId}/admin/people`);
  await expect(page.getByRole("alert")).toHaveText("This page does not exist.");
  expect(membershipRequests).toBe(0);
});

test("the Invitation form offers Member and hides Owner from Admins", async ({ context, page }) => {
  await workspace(context, "admin");
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/memberships**`, (route) =>
    route.fulfill({ status: 200, json: [ownerMembership] }),
  );
  await page.goto(`/organizations/${organizationId}/admin/people`);
  const role = page.getByLabel("Role", { exact: true });
  await expect(role.locator("option")).toHaveText(["Member", "Administrator"]);
});
