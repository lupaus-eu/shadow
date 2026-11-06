import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";

const items = [
  { id: "h2", kind: "updated", reason: "bulk", reason_detail: {}, actor: { kind: "member", name: "Eddie Editor" }, changes: [{ field: "title", before: "Board meeting", after: "Board meeting!" }], created_at: "2026-09-20T10:00:00Z" },
  { id: "h1", kind: "created", reason: "edit", reason_detail: {}, actor: { kind: "member", name: "Olivia Owner" }, changes: [], created_at: "2026-09-01T09:00:00Z" },
];

async function open(context: BrowserContext, preview: Record<string, unknown>, reply: { status: number; json: unknown }, options: { role?: "owner" | "member"; accessRole?: "editor" | "viewer" } = {}) {
  const events = sampleEvents();
  await plannerApi(context, { today: "2026-09-25", events, ...options });
  const history = `${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/${events[0].id}/history`;
  const bodies: unknown[] = [];
  await context.route(`${history}?**`, (route) => route.fulfill({ status: 200, json: { items, next_offset: null } }));
  await context.route(`${history}/h1/restore-preview`, (route) => route.fulfill({ status: 200, json: preview }));
  await context.route(`${history}/h1/restore`, (route) => { bodies.push(route.request().postDataJSON()); return route.fulfill(reply); });
  return { events, bodies };
}

test("an Editor previews and restores an earlier version", async ({ context, page }) => {
  const { events, bodies } = await open(context, { changes: [{ field: "title", before: "Board meeting!", after: "Board meeting" }], category_removed: true, labels_removed: 2, lane_missing: false }, { status: 200, json: { ...sampleEvents()[0], version: 3 } });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await page.locator(".yc-history summary").click();
  const history = page.locator(".yc-history");
  await expect(history.getByRole("button", { name: /^Restore the version from/ })).toHaveCount(1);
  await history.getByRole("button", { name: /^Restore the version from 1 Sept? 2026/ }).click();
  const panel = history.getByRole("group", { name: /^Restore the version from/ });
  await expect(panel).toContainText("Title: Board meeting! → Board meeting");
  await expect(panel).toContainText("Its Category no longer exists and will be left out.");
  await expect(panel).toContainText("2 of its Labels no longer exist and will be left out.");
  expect(await new AxeBuilder({ page }).include(".yc-history").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await panel.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Earlier version restored. It is now the latest version." })).toBeVisible();
  expect(bodies).toEqual([{ expected_version: events[0].version }]);
});

test("a missing Lane is chosen, and a conflict explains itself", async ({ context, page }) => {
  const { bodies } = await open(context, { changes: [], category_removed: false, labels_removed: 0, lane_missing: true }, { status: 409, json: { detail: { latest_version: 4 } } });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await page.locator(".yc-history summary").click();
  await page.locator(".yc-history").getByRole("button", { name: /^Restore the version from/ }).click();
  const panel = page.locator(".yc-restore");
  await panel.getByLabel("Its Lane no longer exists. Choose a Lane").selectOption({ label: "Finance" });
  await panel.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Someone else changed this Event. The latest version is shown; review the history and try again.");
  expect(bodies).toEqual([{ expected_version: 1, lane_id: lanes[1].id }]);
});

test("Viewers see history without restore", async ({ context, page }) => {
  await open(context, {}, { status: 200, json: {} }, { role: "member", accessRole: "viewer" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await page.locator(".yc-history summary").click();
  await expect(page.locator(".yc-history").getByText("Changed with Bulk Edit")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Restore the version/ })).toHaveCount(0);
});
