import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// The Structure canvas drawn by diagram-js, against a stateful mocked API (no sign-in): shapes from the node type, select, drag with a
// debounced save and a reload that keeps the position, connect, delete, a refused write that is reverted and explained, and read-only.
const ORG = "00000000-0000-4000-8000-000000000001";
const MODEL = "00000000-0000-4000-8000-000000000002";
const LINE = "00000000-0000-4000-8000-000000000003";
const EVENT = "00000000-0000-4000-8000-000000000004";

type Node = { id: string; node_type_id: string; name: string; description: string | null; x: number; y: number };
type Connection = { id: string; connection_type_id: string; source_node_id: string; target_node_id: string };

const types = [
  { id: "t1", key: "unit", name: "Unit", color: "#cfe3ff", shape: "rectangle", version: 1 },
  { id: "t2", key: "role", name: "Role", color: "#ffe2b8", shape: "ellipse", version: 1 },
];
const connectionTypes = [{ id: "c1", key: "reports", name: "Reports to", style: "dashed", source_end: "none", target_end: "arrow", version: 1 }];
const allowed = [{ connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t1" }];

function createApi(writable = true) {
  const state = {
    version: 1,
    nodes: [
      { id: "n1", node_type_id: "t1", name: "Sales", description: null, x: 60, y: 60 },
      { id: "n2", node_type_id: "t1", name: "Support", description: null, x: 400, y: 60 },
      { id: "n3", node_type_id: "t2", name: "Lead", description: null, x: 60, y: 260 },
    ] as Node[],
    connections: [] as Connection[],
    positionWrites: [] as { node_id: string; x: number; y: number }[][],
    connectionWrites: 0,
    deleteWrites: [] as string[],
    refuseNext: false as false | "chain" | "stale",
    nextConnection: 1,
  };
  const event = () => ({ id: EVENT, line_id: LINE, occurred_on: "2026-01-01", title: "Start", version: state.version, planned: false, change_count: 1 });
  async function mock(page: Page) {
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname.replace("/api/v1", "");
      const method = request.method();
      const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
      if (path === "/auth/session") return json({ user_account: { id: "u1", account_class: "customer", email: "a@example.test", display_name: "Test Person", locale: "en" } });
      if (path === "/system/status") return json({ database: "ready", schema_revision: "test" });
      if (path === "/organizations") return json({ organizations: [{ id: ORG, name: "Test Org", role: "owner" }] });
      if (path.endsWith("/unread-count")) return json({ unread: 0 });
      if (path === `/organizations/${ORG}`) return json({ organization: { id: ORG, name: "Test Org", time_zone: "UTC" }, membership: { role: "owner" }, subscription: { state: writable ? "active" : "read_only", writable, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null } });
      const model = `/organizations/${ORG}/models/${MODEL}`;
      if (path === `/organizations/${ORG}/models`) return json([{ id: MODEL, name: "Test model", description: null, version: 1, nodes: state.nodes.length }]);
      if (path === `${model}/lines`) return json([{ id: LINE, name: "Base line", description: null, kind: "base", parent_line_id: null, branch_event_id: null, version: 1, event_count: 1, latest_event_date: "2026-01-01" }]);
      if (path === `${model}/lines/${LINE}/events`) return json([event()]);
      if (path === `${model}/lines/${LINE}/state`) return json({ event: event(), node_types: types, connection_types: connectionTypes, allowed_connections: allowed, nodes: state.nodes, connections: state.connections });
      if (path === `${model}/lines/${LINE}/positions` && method === "PUT") {
        const body = request.postDataJSON() as { node_id: string; x: number; y: number }[];
        state.positionWrites.push(body);
        for (const move of body) Object.assign(state.nodes.find((node) => node.id === move.node_id)!, { x: move.x, y: move.y });
        return route.fulfill({ status: 204 });
      }
      if (path === `${model}/events/${EVENT}/connections` && method === "POST") {
        state.connectionWrites++;
        if (state.refuseNext) {
          const stale = state.refuseNext === "stale";
          state.refuseNext = false;
          return stale ? json({ detail: { latest_version: state.version + 1 } }, 409) : json({ detail: { reason: "chain_broken", cause: "test" } }, 422);
        }
        const body = request.postDataJSON() as Omit<Connection, "id">;
        state.connections.push({ id: `cx${state.nextConnection++}`, connection_type_id: body.connection_type_id, source_node_id: body.source_node_id, target_node_id: body.target_node_id });
        state.version++;
        return json({ connection: state.connections.at(-1) });
      }
      const removal = new RegExp(`${model}/events/${EVENT}/nodes/([^/]+)$`).exec(path);
      if (removal && method === "DELETE") {
        state.deleteWrites.push(removal[1]);
        state.nodes = state.nodes.filter((node) => node.id !== removal[1]);
        state.connections = state.connections.filter((item) => item.source_node_id !== removal[1] && item.target_node_id !== removal[1]);
        state.version++;
        return route.fulfill({ status: 204 });
      }
      return json([]);
    });
  }
  return { state, mock };
}

const structure = `/organizations/${ORG}/models/${MODEL}`;
const canvas = (page: Page) => page.getByRole("group", { name: "Model canvas" });
/** Where a node is, in canvas units (the diagram is at 100 %), read from the shape's own transform. */
async function position(page: Page, name: string) {
  const match = /matrix\(1 0 0 1 ([-\d.]+) ([-\d.]+)\)/.exec((await node(page, name).getAttribute("transform")) ?? "");
  return { x: Number(match?.[1]), y: Number(match?.[2]) };
}
const node = (page: Page, name: string) => canvas(page).locator(`g.djs-element.djs-shape[aria-label^="${name} ("]`);

async function open(page: Page, writable = true) {
  const api = createApi(writable);
  await api.mock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(structure);
  await expect(node(page, "Sales")).toBeVisible();
  return api;
}

async function drag(page: Page, name: string, dx: number, dy: number) {
  const box = (await node(page, name).locator(".shadow-node-body").boundingBox())!;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx / 2, y + dy / 2, { steps: 4 });
  await page.mouse.move(x + dx, y + dy, { steps: 4 });
  await page.mouse.up();
}

async function connectSalesToSupport(page: Page) {
  await node(page, "Sales").locator(".shadow-node-body").click();
  await page.getByRole("button", { name: "Connect from this node" }).click();
  await expect(page.getByText("Choose the node to connect to.")).toBeVisible();
  await node(page, "Support").locator(".shadow-node-body").click();
}

test("draws nodes with the shape and colour of their type and labels them for assistive technology", async ({ page }) => {
  await open(page);
  await expect(node(page, "Sales").locator("rect.shadow-node-body")).toHaveCount(1);
  await expect(node(page, "Lead").locator("ellipse.shadow-node-body")).toHaveCount(1);
  await expect(node(page, "Sales").locator(".shadow-node-body")).toHaveCSS("fill", "rgb(207, 227, 255)");
  await expect(node(page, "Lead").locator(".shadow-node-body")).toHaveCSS("fill", "rgb(255, 226, 184)");
  await expect(page.getByRole("button", { name: "Lead (Role)" })).toBeVisible();
});

test("a click selects a node and shows it in the details panel; the background clears it", async ({ page }) => {
  await open(page);
  await node(page, "Sales").locator(".shadow-node-body").click();
  await expect(page.getByRole("heading", { name: "Selected" })).toBeVisible();
  await expect(page.getByLabel("Node name").last()).toHaveValue("Sales");
  await expect(node(page, "Sales")).toHaveClass(/selected/);
  const box = (await canvas(page).boundingBox())!;
  await page.mouse.click(box.x + box.width - 40, box.y + box.height - 40);
  await expect(page.getByText("Select a node to edit it or connect it to another node.")).toBeVisible();
  await expect(node(page, "Sales")).not.toHaveClass(/selected/);
});

test("Enter on a focused node selects it, like a click", async ({ page }) => {
  await open(page);
  await node(page, "Support").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Node name").last()).toHaveValue("Support");
});

test("a list row selects the node on the canvas", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: /^Lead/ }).first().click();
  await expect(node(page, "Lead")).toHaveClass(/selected/);
});

test("a dragged node is saved once after a quiet moment, and keeps its place after a reload", async ({ page }) => {
  const api = await open(page);
  expect(await position(page, "Sales")).toEqual({ x: 60, y: 60 });
  await drag(page, "Sales", 120, 90);
  await drag(page, "Sales", 30, 10);
  expect(await position(page, "Sales")).toEqual({ x: 210, y: 160 });
  await expect.poll(() => api.state.positionWrites.length).toBe(1);
  expect(api.state.positionWrites[0]).toEqual([{ node_id: "n1", x: 210, y: 160 }]);
  await page.reload();
  await expect(node(page, "Sales")).toBeVisible();
  expect(await position(page, "Sales")).toEqual({ x: 210, y: 160 });
});

test("a node can be dragged far beyond the old 1400 x 800 area", async ({ page }) => {
  const api = await open(page);
  await page.setViewportSize({ width: 1920, height: 1000 });
  await page.getByRole("button", { name: "Collapse the Nodes panel" }).click();
  await page.getByRole("button", { name: "Collapse the Details panel" }).click();
  await drag(page, "Sales", 1500, 250);
  await expect.poll(() => api.state.positionWrites.length).toBe(1);
  expect(api.state.positionWrites[0][0].x).toBeGreaterThan(1400);
});

test("connect from the panel: pick the second node, a dashed connection with an arrow appears", async ({ page }) => {
  const api = await open(page);
  await connectSalesToSupport(page);
  await expect.poll(() => api.state.connectionWrites).toBe(1);
  const line = canvas(page).locator(".djs-connection .shadow-connection-line");
  await expect(line).toHaveCount(1);
  await expect(line).toHaveCSS("stroke-dasharray", "6px, 4px");
  await expect(canvas(page).locator(".djs-connection .shadow-connection-arrow")).toHaveCount(1);
  await expect(canvas(page).locator(".djs-connection .shadow-connection-label")).toHaveText("Reports to");
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("a connection the Metamodel does not allow is explained and never sent", async ({ page }) => {
  const api = await open(page);
  await node(page, "Sales").locator(".shadow-node-body").click();
  await page.getByRole("button", { name: "Connect from this node" }).click();
  await node(page, "Lead").locator(".shadow-node-body").click();
  await expect(page.getByRole("alert")).toContainText("not allowed");
  expect(api.state.connectionWrites).toBe(0);
  await expect(canvas(page).locator(".djs-connection")).toHaveCount(0);
});

test("a write the server refuses is reverted on the canvas and explained", async ({ page }) => {
  const api = await open(page);
  api.state.refuseNext = "chain";
  await connectSalesToSupport(page);
  await expect(page.getByRole("alert")).toContainText("would break a later event or scenario");
  expect(api.state.connectionWrites).toBe(1);
  await expect(canvas(page).locator(".djs-connection")).toHaveCount(0);
});

test("a stale version is reverted and the person is told the model was reloaded", async ({ page }) => {
  const api = await open(page);
  api.state.refuseNext = "stale";
  await connectSalesToSupport(page);
  await expect(page.getByRole("alert")).toContainText("Someone changed this just now. The model was reloaded.");
  await expect(canvas(page).locator(".djs-connection")).toHaveCount(0);
  // Nothing is stuck: the same edit now goes through.
  await connectSalesToSupport(page);
  await expect(canvas(page).locator(".djs-connection")).toHaveCount(1);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("delete removes the node and its connections", async ({ page }) => {
  const api = await open(page);
  await connectSalesToSupport(page);
  await expect(canvas(page).locator(".djs-connection")).toHaveCount(1);
  await node(page, "Sales").locator(".shadow-node-body").click();
  await page.getByRole("button", { name: "Delete node" }).click();
  await expect(node(page, "Sales")).toHaveCount(0);
  await expect(canvas(page).locator(".djs-connection")).toHaveCount(0);
  await expect.poll(() => api.state.deleteWrites).toEqual(["n1"]);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("a read-only subscription can select but not drag, and says so", async ({ page }) => {
  const api = await open(page, false);
  await expect(page.getByText("The subscription is read-only, so the model cannot be changed.")).toBeVisible();
  await node(page, "Sales").locator(".shadow-node-body").click();
  await expect(page.getByLabel("Node name").last()).toBeDisabled();
  await expect(page.getByRole("button", { name: "Delete node" })).toHaveCount(0);
  await drag(page, "Sales", 100, 100);
  await page.waitForTimeout(700);
  expect(await position(page, "Sales")).toEqual({ x: 60, y: 60 });
  expect(api.state.positionWrites).toHaveLength(0);
});

test("the diagram is created once: selecting and reloading data keep the same canvas element", async ({ page }) => {
  await open(page);
  await page.evaluate(() => { (window as unknown as { __svg: Element | null }).__svg = document.querySelector(".djs-container svg"); });
  await node(page, "Sales").locator(".shadow-node-body").click();
  await node(page, "Support").locator(".shadow-node-body").click();
  await page.getByRole("button", { name: "Collapse the Nodes panel" }).click();
  expect(await page.evaluate(() => (window as unknown as { __svg: Element | null }).__svg === document.querySelector(".djs-container svg"))).toBe(true);
  expect(await page.locator(".djs-container").count()).toBe(1);
});

test("the canvas page has no automatically detectable accessibility violations", async ({ page }) => {
  await open(page);
  await connectSalesToSupport(page);
  await expect(canvas(page).locator(".djs-connection")).toHaveCount(1);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.map((item) => `${item.id}: ${item.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});
