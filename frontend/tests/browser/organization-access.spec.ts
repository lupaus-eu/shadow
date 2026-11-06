import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { adminWorkspace, budget, organizationId } from "./support/admin-fixture";
import { answerConfirm } from "./support/confirm";

test("an Owner shares a Yearclock with everyone, confirming edit access", async ({ context, page }) => {
  const bodies: unknown[] = [];
  const state = await adminWorkspace(context, {
    extra: async (route, path, current) => {
      if (path !== `/yearclocks/${budget.id}/organization-access`) return false;
      const body = route.request().postDataJSON();
      bodies.push(body);
      if (body.role === "editor" && !body.confirm) { await route.fulfill({ status: 409, json: { detail: { reason: "confirmation_required", members: 2 } } }); return true; }
      current.yearclocks[0] = { ...current.yearclocks[0], organization_access: body.role, version: current.yearclocks[0].version + 1 };
      await route.fulfill({ status: 200, json: { id: budget.id, organization_access: body.role, version: current.yearclocks[0].version } });
      return true;
    },
  });
  await page.goto(`/organizations/${organizationId}/admin/yearclocks`);
  const access = page.getByRole("region", { name: "Access" }).first();
  const everyone = access.getByLabel("Everyone in the Organization");
  await expect(everyone).toHaveValue("none");
  await expect(access.getByText("Applies to everyone who is a member now or joins later.", { exact: false })).toBeVisible();
  expect(await new AxeBuilder({ page }).include("[aria-label='Access']").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await everyone.selectOption("viewer");
  await expect(page.getByRole("region", { name: "Access" }).first().getByLabel("Everyone in the Organization")).toHaveValue("viewer");

  const dialogs: string[] = [];
  await page.getByRole("region", { name: "Access" }).first().getByLabel("Everyone in the Organization").selectOption("editor");
  dialogs.push(await answerConfirm(page));
  await expect(page.getByRole("region", { name: "Access" }).first().getByLabel("Everyone in the Organization")).toHaveValue("editor");
  expect(dialogs).toEqual(["Give edit access to everyone in the Organization? 2 members and everyone who joins later will be able to change this Yearclock."]);
  expect(bodies).toEqual([{ role: "viewer", expected_version: 1, confirm: false }, { role: "editor", expected_version: 2, confirm: false }, { role: "editor", expected_version: 2, confirm: true }]);
  expect(state.yearclocks[0].organization_access).toBe("editor");
});
