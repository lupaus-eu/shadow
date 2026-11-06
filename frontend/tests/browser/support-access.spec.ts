import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, organizationId, plannerApi } from "./support/yearclock-fixture";

const pending = { id: "5a000000-0000-4000-8000-000000000001", organization_id: organizationId, case_reference: "CASE-42", scope: "write", status: "pending", requested_hours: 4, requested_by: "Sanna Support", created_at: "2026-09-23T08:00:00Z", decided_at: null, expires_at: null };

test("Owners approve a shorter Support Access grant and revoke it", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  let current = { ...pending };
  const decisions: Array<{ path: string; body: string | null }> = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/support-access**`, (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "GET") return route.fulfill({ status: 200, json: [current] });
    decisions.push({ path: path.split("/").pop() ?? "", body: request.postData() });
    current = path.endsWith("/approve") ? { ...current, status: "approved", expires_at: "2026-09-23T10:00:00Z" } : { ...current, status: "revoked" };
    return route.fulfill({ status: 200, json: current });
  });
  await page.goto(`/organizations/${organizationId}/admin/support`);
  const panel = page.getByRole("region", { name: "Support Access" });
  await expect(panel).toContainText("Case CASE-42 · read and edit Events · waiting for a decision");
  await expect(panel).toContainText(organizationId);
  expect(await new AxeBuilder({ page }).include(".support-access").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await panel.getByLabel("Approve for hours").fill("2");
  await panel.getByRole("button", { name: "Approve" }).click();
  await expect(panel).toContainText("active until");
  await panel.getByRole("button", { name: "Revoke now" }).click();
  await expect(panel).toContainText("revoked");
  expect(decisions).toEqual([{ path: "approve", body: JSON.stringify({ hours: 2 }) }, { path: "revoke", body: null }]);
});

test("Members never see Support Access requests", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-23" });
  let requests = 0;
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/support-access**`, (route) => { requests += 1; return route.fulfill({ status: 403, json: {} }); });
  await page.goto(`/organizations/${organizationId}`);
  await expect(page.getByRole("heading", { name: "Northwind", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Support Access" })).toHaveCount(0);
  expect(requests).toBe(0);
});

test("a Support Agent requests access and reads approved content", async ({ context, page }) => {
  const grants = [{ ...pending, scope: "read", status: "approved", requested_hours: 1, expires_at: "2026-09-23T10:00:00Z" }];
  const calls: string[] = [];
  await context.route(`${apiBase}/api/v1/platform/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1/platform", "");
    calls.push(`${request.method()} ${path}`);
    if (path === "/session") return route.fulfill({ status: 200, json: { id: "p2", email: "agent@example.com", display_name: "Sanna Support", locale: "en", roles: ["support_agent"] } });
    if (path === "/health") return route.fulfill({ status: 200, json: { database: "ready", email: {}, jobs: {}, webhooks: {}, organizations: {} } });
    if (path === "/jobs") return route.fulfill({ status: 200, json: [] });
    if (path === "/support-access" && request.method() === "POST") {
      const created = { ...pending, ...JSON.parse(request.postData() ?? "{}"), id: "5a000000-0000-4000-8000-000000000002", status: "pending", requested_hours: 3 };
      grants.unshift(created);
      return route.fulfill({ status: 201, json: created });
    }
    if (path === "/support-access") return route.fulfill({ status: 200, json: grants });
    if (path.endsWith("/yearclocks")) return route.fulfill({ status: 200, json: [{ id: "c1", name: "Board year", lanes: [{ id: "l1", name: "Board", position: 0 }], categories: [] }] });
    if (path.endsWith("/events")) return route.fulfill({ status: 200, json: [{ id: "e1", lane_id: "l1", category_id: null, title: "Budget review", starts_on: "2026-10-01", ends_on: null, version: 1 }] });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto("/platform/support");
  const section = page.getByRole("region", { name: "Support Access" });
  await section.getByLabel("Organization ID").fill(organizationId);
  await section.getByLabel("Support case reference").fill("CASE-77");
  await section.getByLabel("Hours (1–24)").fill("3");
  await section.getByRole("button", { name: "Send request" }).click();
  await expect(section.getByRole("status")).toHaveText(/must approve it/);
  await expect(section.getByRole("listitem").filter({ hasText: "CASE-77" })).toContainText("waiting for approval");
  await section.getByRole("button", { name: "Open content" }).click();
  await expect(section.getByText("2026-10-01 · Budget review")).toBeVisible();
  await expect(section.getByText(/recorded in the customer's Activity/)).toBeVisible();
  expect(calls).toContain("POST /support-access");
  expect(calls).toContain(`GET /support-access/${pending.id}/yearclocks/c1/events`);
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
});
