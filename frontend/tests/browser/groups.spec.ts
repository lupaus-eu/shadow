import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { adminWorkspace, mika, organizationId, sanna } from "./support/admin-fixture";
import { answerConfirm } from "./support/confirm";

test("an Owner creates a Group, adds and removes members, renames, and deletes it", async ({ context, page }) => {
  let groups: Array<{ id: string; name: string; version: number; members: Array<{ membership_id: string; name: string; email: string }> }> = [];
  const dialogs: string[] = [];
  await adminWorkspace(context, {
    extra: async (route, path) => {
      const request = route.request();
      if (path === "/groups" && request.method() === "GET") { await route.fulfill({ status: 200, json: groups }); return true; }
      if (path === "/groups" && request.method() === "POST") {
        const name = request.postDataJSON().name;
        if (groups.some((item) => item.name.toLowerCase() === name.toLowerCase())) { await route.fulfill({ status: 409, json: { detail: { reason: "duplicate_name" } } }); return true; }
        groups = [...groups, { id: "g1", name, version: 1, members: [] }];
        await route.fulfill({ status: 201, json: groups.at(-1) }); return true;
      }
      const member = path.match(/^\/groups\/g1\/members\/(.+)$/);
      if (member) {
        const who = [mika, sanna].find((item) => item.id === member[1])!;
        groups[0] = { ...groups[0], version: groups[0].version + 1, members: request.method() === "PUT" ? [...groups[0].members, { membership_id: who.id, name: who.display_name, email: who.email }] : groups[0].members.filter((item) => item.membership_id !== who.id) };
        await route.fulfill({ status: 200, json: groups[0] }); return true;
      }
      if (path === "/groups/g1" && request.method() === "PATCH") { groups[0] = { ...groups[0], name: request.postDataJSON().name, version: groups[0].version + 1 }; await route.fulfill({ status: 200, json: groups[0] }); return true; }
      if (path === "/groups/g1" && request.method() === "DELETE") {
        if (!new URL(request.url()).searchParams.get("confirm")) { await route.fulfill({ status: 409, json: { detail: { reason: "confirmation_required", members: 1, yearclocks: 0, losing_access: [] } } }); return true; }
        groups = []; await route.fulfill({ status: 204, body: "" }); return true;
      }
      return false;
    },
  });
  await page.goto(`/organizations/${organizationId}/admin/groups`);
  const panel = page.getByRole("region", { name: "Groups", exact: true });
  await expect(panel.getByText("No Groups yet.")).toBeVisible();
  await panel.getByLabel("Group name", { exact: true }).fill("Board");
  await panel.getByRole("button", { name: "Add Group" }).click();
  const board = panel.getByRole("region", { name: "Board" });
  await expect(board.getByText("0 members")).toBeVisible();
  await panel.getByLabel("Group name", { exact: true }).fill("board");
  await panel.getByRole("button", { name: "Add Group" }).click();
  await expect(panel.getByRole("alert")).toHaveText("Another Group already has this name.");

  await board.getByLabel("Add member: Board").selectOption({ label: "Mika Member" });
  await board.getByRole("button", { name: "Add", exact: true }).click();
  await expect(board.getByText("1 member", { exact: true })).toBeVisible();
  await board.getByLabel("Add member: Board").selectOption({ label: "Sanna Sales" });
  await board.getByRole("button", { name: "Add", exact: true }).click();
  await expect(board.getByText("2 members")).toBeVisible();
  expect(await new AxeBuilder({ page }).include(".groups").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await board.getByRole("button", { name: "Remove Sanna Sales: Board" }).click();
  await expect(board.getByText("1 member", { exact: true })).toBeVisible();

  await board.getByLabel("Group name: Board").fill("Board of directors");
  await board.getByRole("button", { name: "Rename" }).click();
  const renamed = panel.getByRole("region", { name: "Board of directors" });
  await renamed.getByRole("button", { name: "Delete: Board of directors" }).click();
  dialogs.push(await answerConfirm(page));
  await expect(panel.getByText("No Groups yet.")).toBeVisible();
  expect(dialogs).toEqual(["Delete the Group “Board of directors”? 1 member lose the access it gives to 0 Yearclocks."]);
});

test("members see their own Groups on the Organization page", async ({ context, page }) => {
  await adminWorkspace(context, {
    role: "member",
    extra: async (route, path) => {
      if (path !== "/me/groups") return false;
      await route.fulfill({ status: 200, json: [{ id: "g1", name: "Board", access: [{ yearclock_id: "y1", yearclock_name: "Budget", role: "viewer" }] }, { id: "g2", name: "Sales", access: [] }] });
      return true;
    },
  });
  await page.goto(`/organizations/${organizationId}`);
  const mine = page.getByRole("region", { name: "My groups" });
  await expect(mine.getByRole("listitem").first()).toContainText("Board");
  await expect(mine).toContainText("Budget: Viewer");
  await expect(mine).toContainText("No Yearclock access through this Group.");
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("group", { name: "My groups" }).getByRole("listitem")).toHaveText(["Board", "Sales"]);
  await expect(page.getByText("Groups", { exact: true })).toHaveCount(0);
});
