import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { adminWorkspace, budget, organizationId } from "./support/admin-fixture";

test("an Owner gives a Group access to a Yearclock, changes its role, and removes it", async ({ context, page }) => {
  let grants: Array<{ group_id: string; name: string; role: string; version: number }> = [];
  const bodies: unknown[] = [];
  await adminWorkspace(context, {
    extra: async (route, path) => {
      const request = route.request();
      if (path === "/groups" && request.method() === "GET") { await route.fulfill({ status: 200, json: [{ id: "g1", name: "Board", version: 1, members: [] }, { id: "g2", name: "Finance", version: 1, members: [] }] }); return true; }
      if (path === `/yearclocks/${budget.id}/group-access`) {
        if (request.method() === "GET") { await route.fulfill({ status: 200, json: grants }); return true; }
        const body = request.postDataJSON();
        bodies.push(body);
        const existing = grants.find((grant) => grant.group_id === body.group_id);
        const next = { group_id: body.group_id, name: body.group_id === "g1" ? "Board" : "Finance", role: body.role, version: existing ? existing.version + 1 : 1 };
        grants = [...grants.filter((grant) => grant.group_id !== body.group_id), next];
        await route.fulfill({ status: 200, json: next }); return true;
      }
      if (path === `/yearclocks/${budget.id}/group-access/g2` && request.method() === "DELETE") { grants = grants.filter((grant) => grant.group_id !== "g2"); await route.fulfill({ status: 204, body: "" }); return true; }
      return false;
    },
  });
  await page.goto(`/organizations/${organizationId}/admin/yearclocks`);
  const access = page.getByRole("region", { name: "Access" }).first();
  await access.getByLabel("Group", { exact: true }).selectOption({ label: "Finance" });
  await access.getByLabel("Role for Group Finance").last().selectOption("editor");
  await access.getByRole("button", { name: "Grant" }).last().click();
  await expect(access.getByRole("listitem").filter({ hasText: "Finance" })).toBeVisible();
  await expect(access.getByLabel("Role for Group Finance").first()).toHaveValue("editor");
  expect(await new AxeBuilder({ page }).include("[aria-label='Access']").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await access.getByLabel("Role for Group Finance").first().selectOption("viewer");
  await expect(access.getByLabel("Role for Group Finance").first()).toHaveValue("viewer");
  await access.getByRole("button", { name: "Remove access for Group Finance" }).click();
  await expect(access.getByRole("button", { name: "Remove access for Group Finance" })).toHaveCount(0);
  expect(bodies).toEqual([{ group_id: "g2", role: "editor" }, { group_id: "g2", role: "viewer", expected_version: 1 }]);
});
