import { expect, test } from "@playwright/test";

import { apiBase, organizationId, plannerApi } from "./support/yearclock-fixture";

const item = (index: number, action: string, actor: string | null = "owner@example.com") => ({ id: `a${String(index).padStart(7, "0")}-0000-4000-8000-000000000000`, actor, support_access_id: null, action, target_type: "event", target_id: "e0000000-0000-4000-8000-000000000000", occurred_at: `2026-09-${String(20 - index).padStart(2, "0")}T10:00:00Z`, change_summary: {} });

test("Owners browse, filter, and page through Organization activity", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const queries: string[] = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/audit-events**`, (route) => {
    const url = new URL(route.request().url());
    queries.push(url.search);
    const prefix = url.searchParams.get("prefix");
    const offset = Number(url.searchParams.get("offset"));
    if (prefix === "event") return route.fulfill({ status: 200, json: { items: [item(9, "event.deleted")], next_offset: null } });
    return route.fulfill({ status: 200, json: offset === 0 ? { items: [item(1, "event.created"), item(2, "organization.membership_role_changed", "admin@example.com")], next_offset: 25 } : { items: [item(3, "yearclock.created", null)], next_offset: null } });
  });
  await page.goto(`/organizations/${organizationId}/admin/activity`);
  const log = page.getByRole("list", { name: "Activity" });
  await expect(log.getByRole("listitem")).toHaveCount(2);
  await expect(log.getByText("organization.membership_role_changed")).toBeVisible();
  await expect(log.getByText(/admin@example.com/)).toBeVisible();
  await page.getByRole("button", { name: "Load more" }).click();
  await expect(log.getByRole("listitem")).toHaveCount(3);
  await expect(log.getByText(/yearclock.created · system/)).toBeVisible();
  await page.getByLabel("Area").selectOption("event");
  await expect(log.getByRole("listitem")).toHaveCount(1);
  await expect(log.getByText("event.deleted")).toBeVisible();
  expect(queries).toContain("?offset=0&limit=25&prefix=event");
});

test("Members do not see Organization activity", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-23" });
  let requests = 0;
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/audit-events**`, (route) => { requests += 1; return route.fulfill({ status: 403, json: {} }); });
  await page.goto(`/organizations/${organizationId}`);
  await expect(page.getByRole("heading", { name: "Northwind", exact: true })).toBeVisible();
  await expect(page.getByText("Activity", { exact: true })).toHaveCount(0);
  expect(requests).toBe(0);
});
