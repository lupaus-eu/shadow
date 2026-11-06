import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { adminWorkspace, organizationId } from "./support/admin-fixture";

test("an Admin previews a pasted list, sees skips and missing seats, and then sends", async ({ context, page }) => {
  let seats = 2;
  const bodies: Array<Record<string, unknown>> = [];
  await adminWorkspace(context, {
    extra: async (route, path) => {
      const request = route.request();
      if (path === "/groups" && request.method() === "GET") { await route.fulfill({ status: 200, json: [{ id: "g1", name: "Sales", version: 1, members: [] }] }); return true; }
      if (path !== "/invitations/bulk") return false;
      const body = request.postDataJSON();
      bodies.push(body);
      const invite = (body.emails as string[]).filter((email) => email !== "mika@example.com").map((email) => email.toLowerCase());
      if (!body.dry_run && seats) { await route.fulfill({ status: 409, json: { detail: { reason: "seats_needed", seats_needed: seats } } }); return true; }
      await route.fulfill({ status: 200, json: { invite, skipped: [{ email: "mika@example.com", reason: "member" }], seats_needed: seats, created: body.dry_run ? 0 : invite.length } });
      return true;
    },
  });
  await page.goto(`/organizations/${organizationId}/admin/people`);
  await page.getByText("Invite several people").click();
  const bulk = page.locator(".bulk-invitations");
  await bulk.getByLabel("Email addresses").fill("ann@example.com, Ben@Example.com\nmika@example.com; ann@example.com");
  await bulk.getByRole("group", { name: "Groups to join" }).getByLabel("Sales").check();
  await bulk.getByRole("button", { name: "Preview" }).click();
  const status = bulk.getByRole("status");
  await expect(status).toContainText("2 people will be invited.");
  await expect(status).toContainText("mika@example.com — already a member");
  await expect(status).toContainText("2 more seats are needed before these invitations can be sent. Nothing has been sent.");
  await expect(bulk.getByRole("button", { name: /^Send/ })).toHaveCount(0);
  expect(await new AxeBuilder({ page }).include(".bulk-invitations").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  expect(bodies[0]).toEqual({ emails: ["ann@example.com", "Ben@Example.com", "mika@example.com"], role: "member", group_ids: ["g1"], dry_run: true });

  seats = 0;
  await bulk.getByRole("button", { name: "Preview" }).click();
  await bulk.getByRole("button", { name: "Send 2 invitations" }).click();
  await expect(bulk.getByRole("status")).toHaveText("2 invitations sent.");
  expect(bodies.at(-1)).toMatchObject({ dry_run: false, group_ids: ["g1"] });
});

test("the single invitation offers the same Group choice", async ({ context, page }) => {
  const state = await adminWorkspace(context, {
    extra: async (route, path) => {
      if (path === "/groups" && route.request().method() === "GET") { await route.fulfill({ status: 200, json: [{ id: "g1", name: "Sales", version: 1, members: [] }] }); return true; }
      if (path === "/invitations" && route.request().method() === "POST") { await route.fulfill({ status: 201, json: { id: "i1", email: "new@example.com", role: "member", status: "pending", version: 1, expires_at: "2026-10-02T00:00:00Z" } }); return true; }
      return false;
    },
  });
  await page.goto(`/organizations/${organizationId}/admin/people`);
  const section = page.getByRole("region", { name: "Invite people" });
  await section.getByLabel("Email", { exact: true }).fill("new@example.com");
  await section.getByRole("group", { name: "Groups to join" }).first().getByLabel("Sales").check();
  await section.getByRole("button", { name: "Send invitation" }).click();
  await expect.poll(() => state.requests.find((item) => item.method === "POST" && item.path === "/invitations")?.body).toEqual({ email: "new@example.com", role: "member", group_ids: ["g1"] });
});
