import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { adminWorkspace, budget, mika, organizationId } from "./support/admin-fixture";
import { answerConfirm } from "./support/confirm";

const mikaAccess = { person: { membership_id: mika.id, name: "Mika Member", email: mika.email, organization_role: "member" }, yearclocks: [
  { id: budget.id, name: "Budget", archived: false, role: "editor", sources: [{ kind: "group", role: "editor", group_id: "g1", group_name: "Board" }, { kind: "direct", role: "viewer" }] },
  { id: "c1", name: "Company", archived: false, role: "viewer", sources: [{ kind: "organization", role: "viewer" }] },
] };

test("the People list shows where a member's access comes from, and removal names what is lost", async ({ context, page }) => {
  const state = await adminWorkspace(context, {
    extra: async (route, path, current) => {
      if (path === `/access-overview/people/${mika.id}`) { await route.fulfill({ status: 200, json: mikaAccess }); return true; }
      if (path === `/memberships/${mika.id}` && route.request().method() === "DELETE") { current.memberships = current.memberships.filter((item) => item.id !== mika.id); await route.fulfill({ status: 204, body: "" }); return true; }
      return false;
    },
  });
  await page.goto(`/organizations/${organizationId}/admin/people`);
  const people = page.getByRole("region", { name: "People", exact: true });
  await people.getByRole("button", { name: "Access for Mika Member" }).click();
  const access = people.getByRole("region", { name: "Access for Mika Member" });
  await expect(access.getByRole("listitem").first()).toContainText("Budget — Editor");
  await expect(access).toContainText("Group Board: Editor");
  await expect(access).toContainText("Direct: Viewer");
  await expect(access).toContainText("Everyone in the Organization: Viewer");
  await expect(people.getByRole("button", { name: "Access for Mika Member" })).toHaveAttribute("aria-expanded", "true");
  expect(await new AxeBuilder({ page }).include(".access-overview").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);

  const dialogs: string[] = [];
  await people.getByRole("button", { name: "Remove Mika Member" }).click();
  expect(await new AxeBuilder({ page }).include("[role=alertdialog]").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  dialogs.push(await answerConfirm(page, "cancel"));
  await expect(people.getByRole("button", { name: "Remove Mika Member" })).toBeFocused();
  expect(dialogs[0]).toBe("Remove Mika Member from the Organization? They lose access to: Budget (Editor), Company (Viewer). Their Group memberships and direct access are removed too.");
  expect(state.requests.some((item) => item.method === "DELETE")).toBe(false);
  await people.getByRole("button", { name: "Remove Mika Member" }).click();
  await answerConfirm(page);
  await expect(people.getByText("Mika Member", { exact: true })).toHaveCount(0);
});

test("a Yearclock's access shows who can open it and why", async ({ context, page }) => {
  await adminWorkspace(context, {
    extra: async (route, path) => {
      if (path !== `/access-overview/yearclocks/${budget.id}`) return false;
      await route.fulfill({ status: 200, json: { id: budget.id, name: "Budget", people: [
        { membership_id: "o", name: "Olivia Owner", email: "owner@example.com", organization_role: "owner", role: "editor", sources: [{ kind: "role", role: "editor", organization_role: "owner" }] },
        { membership_id: mika.id, name: "Mika Member", email: mika.email, organization_role: "member", role: "editor", sources: mikaAccess.yearclocks[0].sources },
      ] } });
      return true;
    },
  });
  await page.goto(`/organizations/${organizationId}/admin/yearclocks`);
  const access = page.getByRole("region", { name: "Access" }).first();
  await access.getByRole("button", { name: "Who has access" }).click();
  const who = page.getByRole("region", { name: "Who has access: Budget" });
  await expect(who).toContainText("Olivia Owner — Editor");
  await expect(who).toContainText("Owner (sees every Yearclock)");
  await expect(who).toContainText("Group Board: Editor");
  await access.getByRole("button", { name: "Hide" }).click();
  await expect(who).toHaveCount(0);
});
