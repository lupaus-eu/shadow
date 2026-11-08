import { expect, test, type Page } from "@playwright/test";

// The Structure canvas type panel against a stateful mocked API (no sign-in): hide and restore a type, Select all and Deselect all, search
// with Enter, a row click that centres the node, collapse that survives a reload (and works with the key blocked), and the "+" button.
const ORG = "00000000-0000-4000-8000-000000000001";
const MODEL = "00000000-0000-4000-8000-000000000002";
const LINE = "00000000-0000-4000-8000-000000000003";
const CHANGE = "00000000-0000-4000-8000-000000000004";

type Node = { id: string; node_type_id: string; name: string; description: string | null; x: number; y: number };
const types = [
  { id: "t1", key: "unit", name: "Unit", color: "#cfe3ff", shape: "rectangle", version: 1 },
  { id: "t2", key: "team", name: "Team", color: "#ffe3cf", shape: "rectangle", version: 1 },
  { id: "t3", key: "role", name: "Role", color: "#d9f2d9", shape: "rectangle", version: 1 },
];
const connectionTypes = [{ id: "c1", key: "reports", name: "Reports to", style: "solid", source_end: "none", target_end: "arrow", version: 1 }];
const allowed = [{ connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t2" }];

function createApi(options: { writable?: boolean } = {}) {
  const state = {
    nodes: [
      { id: "n1", node_type_id: "t1", name: "Sales", description: "Sells the products to customers and keeps the accounts that bring most of the revenue in the north.", x: 60, y: 60 },
      { id: "n2", node_type_id: "t2", name: "Support", description: null, x: 400, y: 60 },
      { id: "n3", node_type_id: "t1", name: "Finance", description: null, x: 3000, y: 1800 },
    ] as Node[],
    created: [] as { node_type_id: string; name: string }[],
  };
  const connections = [{ id: "k1", connection_type_id: "c1", source_node_id: "n1", target_node_id: "n2" }];
  const change = () => ({ id: CHANGE, line_id: LINE, occurred_on: "2026-01-01", title: "Start", version: 1, planned: false, edit_count: 1 });
  async function mock(page: Page) {
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname.replace("/api/v1", "");
      const method = request.method();
      const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
      if (path === "/auth/session") return json({ user_account: { id: "u1", account_class: "customer", email: "a@example.test", display_name: "Test Person", locale: "en" } });
      if (path === "/system/status") return json({ database: "ready", schema_revision: "test" });
      if (path === "/organizations") return json({ organizations: [{ id: ORG, name: "Test Org", role: "owner" }] });
      if (path.endsWith("/unread-count")) return json({ unread: 0 });
      if (path === `/organizations/${ORG}`) return json({ organization: { id: ORG, name: "Test Org", time_zone: "UTC" }, membership: { role: "owner" }, subscription: { state: options.writable === false ? "read_only" : "active", writable: options.writable !== false, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null } });
      const model = `/organizations/${ORG}/models/${MODEL}`;
      if (path === `/organizations/${ORG}/models`) return json([{ id: MODEL, name: "Test model", description: null, version: 1, nodes: state.nodes.length }]);
      if (path === `${model}/lines`) return json([{ id: LINE, name: "Base line", description: null, kind: "base", parent_line_id: null, branch_change_id: null, version: 1, change_count: 1, latest_change_date: "2026-01-01" }]);
      if (path === `${model}/lines/${LINE}/changes`) return json([change()]);
      if (path === `${model}/lines/${LINE}/state`) return json({ change: change(), node_types: types, connection_types: connectionTypes, allowed_connections: allowed, nodes: state.nodes, connections });
      if (path === `${model}/changes/${CHANGE}/nodes` && method === "POST") {
        const body = request.postDataJSON() as { node_type_id: string; name: string; x: number; y: number };
        state.created.push({ node_type_id: body.node_type_id, name: body.name });
        const created = { id: `n${state.nodes.length + 1}`, description: null, ...body };
        state.nodes.push(created);
        return json({ node: created });
      }
      return json([]);
    });
  }
  return { state, mock };
}

const structure = `/organizations/${ORG}/models/${MODEL}`;
const canvas = (page: Page) => page.getByRole("group", { name: "Model canvas" });
const node = (page: Page, name: string) => canvas(page).locator(`g.djs-element.djs-shape[aria-label^="${name} ("]`);
const connection = (page: Page) => canvas(page).locator("g.djs-element.djs-connection");
const show = (page: Page, type: string) => page.getByRole("checkbox", { name: `Show ${type} nodes` });
const panel = (page: Page) => page.getByRole("complementary", { name: "Nodes" });
const row = (page: Page, name: string) => panel(page).getByRole("button", { name: new RegExp(`^${name}( |$)`) });
const centreOf = async (page: Page, name: string) => { const box = (await node(page, name).locator(".shadow-node-body").boundingBox())!; return { x: box.x + box.width / 2, y: box.y + box.height / 2 }; };

async function open(page: Page, options: { writable?: boolean } = {}) {
  const api = createApi(options);
  await api.mock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(structure);
  await expect(node(page, "Sales")).toBeVisible();
  return api;
}

test("the panel groups nodes by type with counts; a type without nodes starts collapsed", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("checkbox")).toHaveCount(3);
  for (const [type, count] of [["Unit", 2], ["Team", 1], ["Role", 0]] as const) await expect(page.locator("label", { has: show(page, type) })).toContainText(`(${count})`);
  const order = await page.locator("label:has(input[type=checkbox])").allInnerTexts();
  expect(order.map((text) => text.split("\n")[0])).toEqual(["Role", "Team", "Unit"]);
  await expect(page.getByRole("button", { name: "Expand Role" })).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("button", { name: "Collapse Unit" })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByLabel("Search nodes")).toBeVisible();
});

test("hiding a type removes its nodes and touching connections from the drawing, restoring brings them back", async ({ page }) => {
  await open(page);
  await expect(connection(page)).toHaveCount(1);
  await expect(connection(page)).toBeVisible();
  await show(page, "Team").uncheck();
  await expect(node(page, "Support")).toBeHidden();
  await expect(connection(page)).toBeHidden();
  await expect(node(page, "Sales")).toBeVisible();
  await expect(row(page, "Support")).toBeDisabled();
  await show(page, "Team").check();
  await expect(node(page, "Support")).toBeVisible();
  await expect(connection(page)).toBeVisible();
  await expect(row(page, "Support")).toBeEnabled();
});

test("Deselect all hides every node, Select all brings them back", async ({ page }) => {
  await open(page);
  await panel(page).getByRole("button", { name: "Deselect all" }).click();
  for (const name of ["Sales", "Support", "Finance"]) await expect(node(page, name)).toBeHidden();
  await expect(connection(page)).toBeHidden();
  await expect(show(page, "Unit")).not.toBeChecked();
  await expect(panel(page).getByRole("button", { name: "Deselect all" })).toBeDisabled();
  await panel(page).getByRole("button", { name: "Select all", exact: true }).click();
  for (const name of ["Sales", "Support", "Finance"]) await expect(node(page, name)).toBeVisible();
  await expect(show(page, "Role")).toBeChecked();
});

test("search dims what does not match, Enter centres the first match, clearing restores", async ({ page }) => {
  await open(page);
  const search = page.getByLabel("Search nodes");
  await search.fill("fin");
  await expect(node(page, "Finance")).not.toHaveClass(/shadow-dim/);
  await expect(node(page, "Finance")).toHaveClass(/shadow-match/);
  await expect(node(page, "Sales")).toHaveClass(/shadow-dim/);
  await expect(node(page, "Support")).toHaveClass(/shadow-dim/);
  await expect(node(page, "Sales")).toHaveCSS("opacity", "0.3");
  await search.press("Enter");
  const box = (await canvas(page).boundingBox())!;
  await expect.poll(async () => {
    const at = await centreOf(page, "Finance");
    return Math.hypot(at.x - (box.x + box.width / 2), at.y - (box.y + box.height / 2));
  }).toBeLessThan(4);
  await search.fill("zzz");
  await expect(page.getByText("No node matches.")).toBeVisible();
  await search.fill("");
  await expect(canvas(page).locator(".shadow-dim, .shadow-match")).toHaveCount(0);
});

test("/ focuses the search box from the drawing without typing a slash", async ({ page }) => {
  await open(page);
  const box = (await canvas(page).boundingBox())!;
  await page.mouse.click(box.x + box.width - 30, box.y + box.height - 30);
  await page.keyboard.press("/");
  await expect(page.getByLabel("Search nodes")).toBeFocused();
  await expect(page.getByLabel("Search nodes")).toHaveValue("");
});

test("a row click selects the node, centres it and zooms in to at least 100 %", async ({ page }) => {
  await open(page);
  await expect(canvas(page)).toHaveAttribute("data-zoom", /^(?!100$)\d+$/);
  await row(page, "Finance").click();
  await expect(row(page, "Finance")).toHaveAttribute("aria-pressed", "true");
  await expect(node(page, "Finance")).toHaveClass(/selected/);
  const box = (await canvas(page).boundingBox())!;
  await expect.poll(async () => {
    const at = await centreOf(page, "Finance");
    return Math.hypot(at.x - (box.x + box.width / 2), at.y - (box.y + box.height / 2));
  }).toBeLessThan(4);
  expect(Number(await canvas(page).getAttribute("data-zoom"))).toBeGreaterThanOrEqual(100);
});

test("rows show a clamped description", async ({ page }) => {
  await open(page);
  const description = page.getByText(/^Sells the products/);
  await expect(description).toBeVisible();
  await expect(description).toHaveCSS("-webkit-line-clamp", "2");
});

test("collapse survives a reload and is kept per model", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Collapse Unit" }).click();
  await page.getByRole("button", { name: "Expand Role" }).click();
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("shadow.canvas.typeCollapse")!))).toEqual({ [MODEL]: { t1: true, t3: false } });
  await page.reload();
  await expect(node(page, "Sales")).toBeVisible();
  await expect(page.getByRole("button", { name: "Expand Unit" })).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("button", { name: "Collapse Role" })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("button", { name: "Collapse Team" })).toHaveAttribute("aria-expanded", "true");
});

test("with the collapse key blocked the panel still collapses", async ({ page }) => {
  await page.addInitScript(() => {
    const blocked = (original: (key: string, value?: string) => unknown) => function (this: Storage, key: string, value?: string) { if (key === "shadow.canvas.typeCollapse") throw new DOMException("blocked", "SecurityError"); return original.call(this, key, value); };
    Storage.prototype.getItem = blocked(Storage.prototype.getItem) as typeof Storage.prototype.getItem;
    Storage.prototype.setItem = blocked(Storage.prototype.setItem) as typeof Storage.prototype.setItem;
  });
  await open(page);
  await page.getByRole("button", { name: "Collapse Unit" }).click();
  await expect(page.getByRole("button", { name: "Expand Unit" })).toHaveAttribute("aria-expanded", "false");
});

test("the + of a type opens a node of that type for naming, and Enter saves it", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Add a Team node" }).click();
  await page.getByRole("textbox", { name: "Node name" }).last().fill("Platform");
  await page.keyboard.press("Enter");
  await expect.poll(() => api.state.created.map((item) => ({ node_type_id: item.node_type_id, name: item.name }))).toEqual([{ node_type_id: "t2", name: "Platform" }]);
  await expect(node(page, "Platform")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Show Team nodes" }).locator("xpath=ancestor::label")).toContainText("(2)");
});

test("a read-only model has no + buttons", async ({ page }) => {
  await open(page, { writable: false });
  await expect(page.getByRole("button", { name: /^Add a .* node$/ })).toHaveCount(0);
  await expect(page.getByRole("checkbox")).toHaveCount(3);
});
