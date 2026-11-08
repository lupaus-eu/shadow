import { expect, test, type Page } from "@playwright/test";

// The Structure canvas layout, against a mocked API (no sign-in): full width, no page scroll, collapsible panels that survive a reload, and the bottom sheet on a phone.
const ORG = "00000000-0000-4000-8000-000000000001";
const MODEL = "00000000-0000-4000-8000-000000000002";
const LINE = "00000000-0000-4000-8000-000000000003";
const EVENT = "00000000-0000-4000-8000-000000000004";
const event = { id: EVENT, line_id: LINE, occurred_on: "2026-01-01", title: "Start", version: 1, planned: false, change_count: 1 };

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const json = (body: unknown) => route.fulfill({ json: body });
    if (path === "/auth/session") return json({ user_account: { id: "u1", account_class: "customer", email: "a@example.test", display_name: "Test Person", locale: "en" } });
    if (path === "/system/status") return json({ database: "ready", schema_revision: "test" });
    if (path === "/organizations") return json({ organizations: [{ id: ORG, name: "Test Org", role: "owner" }] });
    if (path.endsWith("/unread-count")) return json({ unread: 0 });
    if (path === `/organizations/${ORG}`) return json({ organization: { id: ORG, name: "Test Org", time_zone: "UTC" }, membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null } });
    if (path === `/organizations/${ORG}/models`) return json([{ id: MODEL, name: "Test model", description: null, version: 1, nodes: 1 }]);
    if (path === `/organizations/${ORG}/models/${MODEL}/lines`) return json([{ id: LINE, name: "Base line", description: null, kind: "base", parent_line_id: null, branch_event_id: null, version: 1, event_count: 1, latest_event_date: "2026-01-01" }]);
    if (path.endsWith("/events")) return json([event]);
    if (path.endsWith("/state")) return json({ event, node_types: [{ id: "t1", key: "unit", name: "Unit", color: "#cfe3ff", shape: "rectangle", version: 1 }], connection_types: [], allowed_connections: [], nodes: [{ id: "n1", node_type_id: "t1", name: "Sales", description: null, x: 40, y: 40 }], connections: [] });
    return json([]);
  });
}

const structure = `/organizations/${ORG}/models/${MODEL}`;
const canvas = (page: Page) => page.getByRole("group", { name: "Model canvas" });

test.beforeEach(async ({ page }) => { await mockApi(page); });

test("at 1920 px the canvas is wider than the reading column and the page does not scroll; other tabs keep their width", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1000 });
  await page.goto(structure);
  await expect(canvas(page)).toBeVisible();
  // The working area (panels and canvas) is wider than the old max-w-6xl column; with both panels collapsed the canvas itself is.
  expect((await page.locator("#main-content").boundingBox())!.width).toBeGreaterThan(1152);
  await page.getByRole("button", { name: "Collapse the Nodes panel" }).click();
  await page.getByRole("button", { name: "Collapse the Details panel" }).click();
  await expect.poll(async () => (await canvas(page).boundingBox())!.width).toBeGreaterThan(1152);
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight)).toBe(true);
  await page.setViewportSize({ width: 1920, height: 800 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight)).toBe(true);
  await page.goto(`${structure}/types`);
  const main = await page.locator("#main-content").boundingBox();
  expect(main!.width).toBeLessThanOrEqual(1152 + 1);
});

test("a collapsed panel stays collapsed after a reload", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(structure);
  const collapse = page.getByRole("button", { name: "Collapse the Details panel" });
  await expect(collapse).toHaveAttribute("aria-expanded", "true");
  await collapse.click();
  await expect(page.getByRole("button", { name: "Expand the Details panel" })).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("#canvas-panel-right")).toBeHidden();
  await page.reload();
  await expect(page.getByRole("button", { name: "Expand the Details panel" })).toBeVisible();
  await expect(page.locator("#canvas-panel-right")).toBeHidden();
  await page.getByRole("button", { name: "Expand the Details panel" }).click();
  await expect(page.getByRole("button", { name: "Collapse the Details panel" })).toBeVisible();
});

test("with the panel key blocked the canvas still renders and the panels still collapse", async ({ page }) => {
  await page.addInitScript(() => {
    const blocked = (original: (key: string, value?: string) => unknown) => function (this: Storage, key: string, value?: string) { if (key === "shadow.canvas.panels") throw new DOMException("blocked", "SecurityError"); return original.call(this, key, value); };
    Storage.prototype.getItem = blocked(Storage.prototype.getItem) as typeof Storage.prototype.getItem;
    Storage.prototype.setItem = blocked(Storage.prototype.setItem) as typeof Storage.prototype.setItem;
  });
  await page.goto(structure);
  await expect(canvas(page)).toBeVisible();
  await page.getByRole("button", { name: "Collapse the Nodes panel" }).click();
  await expect(page.getByRole("button", { name: "Expand the Nodes panel" })).toBeVisible();
});

test("at 375 px the panels are a bottom sheet and the canvas fills the width", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(structure);
  await expect(canvas(page)).toBeVisible();
  expect((await canvas(page).boundingBox())!.width).toBeGreaterThan(330);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const handle = page.getByRole("button", { name: "Show panels" });
  await expect(handle).toHaveAttribute("aria-expanded", "false");
  await handle.click();
  await expect(page.getByRole("button", { name: "Hide panels" })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("button", { name: "Add", exact: true })).toBeVisible();
});
