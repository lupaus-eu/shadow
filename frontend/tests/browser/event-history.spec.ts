import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";

const entry = (index: number, extra: Record<string, unknown> = {}) => ({ id: `h${index}`, kind: "updated", reason: "edit", reason_detail: {}, actor: { kind: "member", name: "Olivia Owner" }, changes: [{ field: "title", before: `Edit ${index - 1}`, after: `Edit ${index}` }], created_at: `2026-09-${String(10 + (index % 15)).padStart(2, "0")}T08:30:00Z`, ...extra });

test("Event details show history with old and new values, reasons, and actors", async ({ context, page }) => {
  const events = sampleEvents();
  await plannerApi(context, { today: "2026-09-25", events, role: "member", accessRole: "viewer" });
  const offsets: string[] = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/${events[0].id}/history**`, (route) => {
    const offset = new URL(route.request().url()).searchParams.get("offset") ?? "0";
    offsets.push(offset);
    const first = [
      entry(3, { reason: "category_deleted", reason_detail: { name: "Audit" }, actor: { kind: "member", name: "Olivia Owner" }, changes: [{ field: "category_id", before: { id: "c", name: null }, after: null }] }),
      entry(2, { actor: { kind: "member", name: null }, changes: [{ field: "starts_on", before: "2026-03-03", after: "2026-03-10" }, { field: "description" }] }),
    ];
    return route.fulfill({ status: 200, json: offset === "0" ? { items: first, next_offset: 2 } : { items: [{ ...entry(1), kind: "created", reason: "baseline", actor: { kind: "system", name: null }, changes: [] }], next_offset: null } });
  });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  const details = page.getByRole("complementary", { name: "Event details" });
  const history = details.locator(".yc-history");
  await history.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(history.getByRole("listitem").filter({ hasText: "Category Audit deleted" })).toContainText("Category: (removed) → none");
  const moved = history.getByRole("listitem").filter({ hasText: "Former member" }).first();
  await expect(moved).toContainText("Start: 3 Mar 2026 → 10 Mar 2026");
  await expect(moved).toContainText("Description changed");
  expect(await new AxeBuilder({ page }).include(".yc-history").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await history.getByRole("button", { name: "Show older changes" }).click();
  await expect(history.getByText("State when history began")).toBeVisible();
  await expect(history.getByText(/· Yearclock$/)).toBeVisible();
  await expect(history.getByRole("button", { name: "Show older changes" })).toHaveCount(0);
  expect(offsets).toEqual(["0", "2"]);
});

test("history is in Finnish and says when it cannot be loaded", async ({ context, page }) => {
  const events = sampleEvents();
  await plannerApi(context, { today: "2026-09-25", events, locale: "fi" });
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/*/history**`, (route) => route.fulfill({ status: 500, json: {} }));
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await page.locator(".yc-history summary").click();
  await expect(page.locator(".yc-history").getByRole("status")).toHaveText("Historiaa ei voitu ladata.");
});
