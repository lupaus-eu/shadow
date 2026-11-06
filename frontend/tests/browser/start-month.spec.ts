import { expect, test, type BrowserContext } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";

async function workspace(context: BrowserContext, startMonth: number, role: "owner" | "member" = "owner") {
  const requests = await plannerApi(context, { today: "2026-09-25", role, accessRole: role === "member" ? "viewer" : "editor" });
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: [{ id: yearclockId, name: "School year", version: 4, access_role: role === "member" ? "viewer" : "editor", lanes, start_month: startMonth }] } }));
  return requests;
}

test("a Yearclock that starts in August opens on August to July for everyone", async ({ context, page }) => {
  await workspace(context, 8, "member");
  await page.goto(yearclockPath);
  await expect(page.getByText("Showing 1 Aug 2026 to 31 Jul 2027")).toBeVisible();
  await page.getByRole("group", { name: "Planning Window" }).getByRole("button", { name: "Next month" }).click();
  await page.getByRole("group", { name: "Planning Window" }).getByRole("button", { name: "Current period" }).click();
  await expect(page.getByText("Showing 1 Aug 2026 to 31 Jul 2027")).toBeVisible();
  await expect(page.getByRole("link", { name: "Yearclock settings" })).toHaveCount(0);
});

test("an Editor sets the start month and a stale change explains the conflict", async ({ context, page }) => {
  await workspace(context, 1);
  const bodies: unknown[] = [];
  let conflict = false;
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/layout`, (route) => {
    bodies.push(route.request().postDataJSON());
    if (conflict) return route.fulfill({ status: 409, json: { detail: { latest_version: 6 } } });
    conflict = true;
    return route.fulfill({ status: 200, json: { id: yearclockId, version: 5, start_month: 8 } });
  });
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const layout = page.getByRole("region", { name: "Layout" });
  await expect(layout.getByRole("button", { name: "Save layout" })).toBeDisabled();
  await layout.getByLabel("Year starts in").selectOption({ label: "August" });
  await layout.getByRole("button", { name: "Save layout" }).click();
  await expect(layout.getByRole("status")).toHaveText("Layout saved.");
  await layout.getByLabel("Year starts in").selectOption({ label: "September" });
  await layout.getByRole("button", { name: "Save layout" }).click();
  await expect(layout.getByRole("alert")).toContainText("Someone else changed");
  expect(bodies).toEqual([{ start_month: 8, show_week_ring: false, show_quarter_ring: false, expected_version: 4 }, { start_month: 9, show_week_ring: false, show_quarter_ring: false, expected_version: 4 }]);
});
