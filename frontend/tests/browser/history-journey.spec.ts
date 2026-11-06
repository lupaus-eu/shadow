import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";

const yearclockApi = `${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}`;

test("Yearclock V2 history journey: marks since the last visit, history, restore, change notice", async ({ context, page }) => {
  const events = sampleEvents();
  const board = events[0];
  await plannerApi(context, { events });
  await page.clock.install({ time: new Date("2026-09-25T09:00:00Z") });
  const actor = { kind: "member", name: "Eddie Editor" };
  let othersChanged = 0;
  await context.route(`${yearclockApi}/visit`, (route) => route.fulfill({ status: 200, json: { previous_visited_at: "2026-09-20T08:00:00Z" } }));
  await context.route(`${yearclockApi}/changes**`, (route) => {
    const limit = new URL(route.request().url()).searchParams.get("limit");
    if (limit === "1") return route.fulfill({ status: 200, json: { items: [], total: othersChanged, more: false, latest_at: null } });
    return route.fulfill({ status: 200, json: { items: [{ event_id: board.id, series_id: null, title: board.title, kind: "changed", at: "2026-09-24T09:00:00Z", actor, count: 1 }], total: 1, more: false, latest_at: "2026-09-24T09:00:00Z" } });
  });
  await context.route(`${yearclockApi}/events/${board.id}/history?**`, (route) => route.fulfill({ status: 200, json: { next_offset: null, items: [
    { id: "h2", kind: "updated", reason: "bulk", reason_detail: {}, actor, changes: [{ field: "category_id", before: { id: "c1", name: "Board" }, after: { id: "c2", name: "Audit" } }], created_at: "2026-09-24T09:00:00Z" },
    { id: "h1", kind: "created", reason: "edit", reason_detail: {}, actor: { kind: "member", name: "Olivia Owner" }, changes: [], created_at: "2026-09-01T09:00:00Z" },
  ] } }));
  await context.route(`${yearclockApi}/events/${board.id}/history/h1/restore-preview`, (route) => route.fulfill({ status: 200, json: { changes: [{ field: "category_id", before: { id: "c2", name: "Audit" }, after: { id: "c1", name: "Board" } }], category_removed: false, labels_removed: 0, lane_missing: false } }));
  let restored = false;
  await context.route(`${yearclockApi}/events/${board.id}/history/h1/restore`, (route) => { restored = true; return route.fulfill({ status: 200, json: { ...board, version: 2 } }); });

  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  const changes = page.getByRole("region", { name: "Changes since your last visit (1)" });
  await expect(changes).toContainText("Board meeting — Changed");
  const marker = page.getByRole("button", { name: /^Board meeting, Changed,/ });
  await marker.click();
  const history = page.locator(".yc-history");
  await history.locator("summary").click();
  await expect(history).toContainText("Changed with Bulk Edit");
  await expect(history).toContainText("Category: Board → Audit");
  await history.getByRole("button", { name: /^Restore the version from/ }).click();
  await history.locator(".yc-restore").getByRole("button", { name: "Restore", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Earlier version restored." })).toBeVisible();
  expect(restored).toBe(true);
  await page.getByRole("button", { name: "Mark as seen" }).click();
  await expect(changes).toHaveCount(0);

  othersChanged = 1;
  await page.clock.fastForward(61_000);
  await expect(page.getByRole("status").filter({ hasText: "This Yearclock has been changed by others since you opened it." })).toBeVisible();
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
});
