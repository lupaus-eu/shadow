import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { adminWorkspace, budget, mika, organizationId } from "./support/admin-fixture";

test("Yearclock V2 administration journey: Group, Group access, sharing, bulk invitations, access overview", async ({ context, page }) => {
  let groups: Array<{ id: string; name: string; version: number; members: Array<{ membership_id: string; name: string; email: string }> }> = [];
  let grants: Array<{ group_id: string; name: string; role: string; version: number }> = [];
  await adminWorkspace(context, {
    extra: async (route, path, state) => {
      const request = route.request();
      const method = request.method();
      if (path === "/groups" && method === "GET") { await route.fulfill({ status: 200, json: groups }); return true; }
      if (path === "/groups" && method === "POST") { groups = [{ id: "g1", name: request.postDataJSON().name, version: 1, members: [] }]; await route.fulfill({ status: 201, json: groups[0] }); return true; }
      if (path === `/groups/g1/members/${mika.id}`) { groups[0] = { ...groups[0], version: 2, members: [{ membership_id: mika.id, name: mika.display_name, email: mika.email }] }; await route.fulfill({ status: 200, json: groups[0] }); return true; }
      if (path === `/yearclocks/${budget.id}/group-access`) {
        if (method === "PUT") { grants = [{ group_id: "g1", name: "Finance", role: request.postDataJSON().role, version: 1 }]; await route.fulfill({ status: 200, json: grants[0] }); return true; }
        await route.fulfill({ status: 200, json: grants }); return true;
      }
      if (path === `/yearclocks/${budget.id}/organization-access`) { state.yearclocks[0] = { ...state.yearclocks[0], organization_access: request.postDataJSON().role, version: 2 }; await route.fulfill({ status: 200, json: { id: budget.id, organization_access: request.postDataJSON().role, version: 2 } }); return true; }
      if (path === "/invitations/bulk") { await route.fulfill({ status: 200, json: { invite: ["new@example.com"], skipped: [], seats_needed: 0, created: request.postDataJSON().dry_run ? 0 : 1 } }); return true; }
      if (path === `/access-overview/people/${mika.id}`) { await route.fulfill({ status: 200, json: { person: { membership_id: mika.id, name: "Mika Member", email: mika.email, organization_role: "member" }, yearclocks: [{ id: budget.id, name: "Budget", archived: false, role: grants[0]?.role ?? "viewer", sources: [...grants.map((grant) => ({ kind: "group", role: grant.role, group_id: grant.group_id, group_name: grant.name })), { kind: "organization", role: "viewer" }] }] } }); return true; }
      return false;
    },
  });
  await page.goto(`/organizations/${organizationId}/admin/groups`);

  const panel = page.getByRole("region", { name: "Groups" });
  await panel.getByLabel("Group name", { exact: true }).fill("Finance");
  await panel.getByRole("button", { name: "Add Group" }).click();
  const finance = panel.getByRole("region", { name: "Finance" });
  await finance.getByLabel("Add member: Finance").selectOption({ label: "Mika Member" });
  await finance.getByRole("button", { name: "Add", exact: true }).click();
  await expect(finance.getByText("1 member", { exact: true })).toBeVisible();

  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Yearclocks and access" }).click();
  const access = page.getByRole("region", { name: "Access" }).first();
  await access.getByLabel("Everyone in the Organization").selectOption("viewer");
  await expect(page.getByRole("region", { name: "Access" }).first().getByLabel("Everyone in the Organization")).toHaveValue("viewer");
  const refreshed = page.getByRole("region", { name: "Access" }).first();
  await refreshed.getByLabel("Group", { exact: true }).selectOption({ label: "Finance" });
  await refreshed.getByLabel("Role for Group Finance").last().selectOption("editor");
  await refreshed.getByRole("button", { name: "Grant" }).last().click();
  await expect(refreshed.getByLabel("Role for Group Finance").first()).toHaveValue("editor");

  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "People" }).click();
  await page.getByText("Invite several people").click();
  const bulk = page.locator(".bulk-invitations");
  await bulk.getByLabel("Email addresses").fill("new@example.com");
  await bulk.getByRole("button", { name: "Preview" }).click();
  await bulk.getByRole("button", { name: "Send 1 invitation" }).click();
  await expect(bulk.getByRole("status")).toHaveText("1 invitation sent.");

  const people = page.getByRole("region", { name: "People", exact: true });
  await people.getByRole("button", { name: "Access for Mika Member" }).click();
  const overview = people.getByRole("region", { name: "Access for Mika Member" });
  await expect(overview).toContainText("Budget — Editor");
  await expect(overview).toContainText("Group Finance: Editor");
  await expect(overview).toContainText("Everyone in the Organization: Viewer");
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
});
