import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, organizationId, plannerApi } from "./support/yearclock-fixture";

test("an Owner confirms deletion explicitly and is returned to the Organization list", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const bodies: string[] = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/deletion`, (route) => {
    bodies.push(route.request().postData() ?? "");
    return route.fulfill({ status: 200, json: { status: "pending_deletion", deletion_requested_at: "2026-09-23T10:00:00Z", purge_after: "2026-10-23T10:00:00Z" } });
  });
  await context.route(`${apiBase}/api/v1/organizations`, (route) => route.fulfill({ status: 200, json: { organizations: [{ id: organizationId, name: "Northwind", role: "owner", status: "pending_deletion", purge_after: "2026-10-23T10:00:00Z" }] } }));
  await page.goto(`/organizations/${organizationId}/admin/settings`);
  const remove = page.getByRole("button", { name: "Delete Organization" });
  await expect(remove).toBeDisabled();
  await page.getByLabel(/I understand that “Northwind” is closed now/).check();
  expect(await new AxeBuilder({ page }).include(".organization-deletion").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await remove.click();
  await expect(page).toHaveURL(/\/$/);
  expect(bodies).toEqual([JSON.stringify({ confirm: true })]);
  await expect(page.getByText("Pending deletion — purged on 23 October 2026")).toBeVisible();
});

test("an Owner restores a Pending Deletion Organization from the list", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await context.route(`${apiBase}/api/v1/organizations`, (route) => route.fulfill({ status: 200, json: { organizations: [{ id: organizationId, name: "Northwind", role: "owner", status: "pending_deletion", purge_after: "2026-10-23T10:00:00Z" }] } }));
  let restored = 0;
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/deletion/restore`, (route) => { restored += 1; return route.fulfill({ status: 200, json: { status: "active", deletion_requested_at: null, purge_after: null } }); });
  await page.goto("/");
  await page.getByRole("button", { name: "Restore: Northwind" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Organization restored." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Northwind" })).toHaveAttribute("href", `/organizations/${organizationId}`);
  expect(restored).toBe(1);
});

test("Admins cannot delete the Organization", async ({ context, page }) => {
  await plannerApi(context, { role: "admin", today: "2026-09-23" });
  await page.goto(`/organizations/${organizationId}`);
  await expect(page.getByRole("heading", { name: "Northwind", exact: true })).toBeVisible();
  await expect(page.getByText("Delete Organization", { exact: true })).toHaveCount(0);
});
