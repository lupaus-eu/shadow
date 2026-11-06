import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";

const yearclockApi = `${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}`;

test("changes by others since the last visit are marked and listed until marked as seen", async ({ context, page }) => {
  const events = sampleEvents();
  const requests = await plannerApi(context, { today: "2026-09-25", events });
  const actor = { kind: "member", name: "Eddie Editor" };
  const since: string[] = [];
  await context.route(`${yearclockApi}/visit`, (route) => route.fulfill({ status: 200, json: { previous_visited_at: "2026-09-20T08:00:00Z" } }));
  await context.route(`${yearclockApi}/deleted-events`, (route) => route.fulfill({ status: 200, json: [{ ...events[2], id: "d1000000-0000-4000-8000-000000000001", title: "Old workshop", deleted_at: "2026-09-22T10:00:00Z", purge_after: "2026-10-22T10:00:00Z" }] }));
  await context.route(`${yearclockApi}/changes**`, (route) => {
    since.push(new URL(route.request().url()).searchParams.get("since") ?? "");
    return route.fulfill({ status: 200, json: { total: 4, more: false, latest_at: "2026-09-24T09:00:00Z", items: [
      { event_id: events[0].id, series_id: null, title: "Board meeting", kind: "changed", at: "2026-09-24T09:00:00Z", actor, count: 1 },
      { event_id: events[1].id, series_id: null, title: "Audit period", kind: "new", at: "2026-09-23T09:00:00Z", actor, count: 1 },
      { event_id: "d1000000-0000-4000-8000-000000000001", series_id: null, title: "Old workshop", kind: "deleted", at: "2026-09-22T10:00:00Z", actor, count: 1 },
      { event_id: null, series_id: events[3].series_id, title: "Weekly finance check", kind: "series_changed", at: "2026-09-21T10:00:00Z", actor, count: 20 },
    ] } });
  });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  const panel = page.getByRole("region", { name: "Changes since your last visit (4)" });
  await expect(panel.getByRole("listitem")).toHaveCount(4);
  await expect(panel.getByRole("listitem").nth(3)).toContainText("Weekly finance check — Series changed (20 occurrences)");
  await expect(page.getByRole("button", { name: /^Board meeting, Changed,/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Audit period, New,/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Weekly finance check, Changed,/ }).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ }).locator(".yc-mark")).toHaveText("Changed");
  expect(since).toEqual(["2026-09-20T08:00:00Z"]);
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);

  await panel.getByRole("button", { name: "Restore" }).click();
  await expect.poll(() => requests.some((item) => item.method === "POST" && item.path === "/events/d1000000-0000-4000-8000-000000000001/restore")).toBe(true);
  await page.getByRole("button", { name: "Mark as seen" }).click();
  await expect(page.getByRole("region", { name: /^Changes since your last visit/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Board meeting, 10 Mar 2026,/ })).toBeVisible();
  await expect(page.locator(".yc-mark")).toHaveCount(0);
});

test("a first visit shows no marks and Viewers get no restore", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-25", role: "member", accessRole: "viewer" });
  let asked = false;
  await context.route(`${yearclockApi}/changes**`, (route) => { asked = true; return route.fulfill({ status: 200, json: { total: 0, more: false, latest_at: null, items: [] } }); });
  await page.goto(yearclockPath);
  await expect(page.getByRole("heading", { name: "Events in this window" })).toBeVisible();
  await expect(page.getByRole("region", { name: /^Changes since your last visit/ })).toHaveCount(0);
  expect(asked).toBe(false);
});
