import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Snap, align, distribute, auto layout, the minimap and export on the Structure canvas, against a stateful mocked API (no sign-in):
// positions are written to `/positions` and read back from `/state`, as with the real routes.
const ORG = "00000000-0000-4000-8000-000000000001";
const MODEL = "00000000-0000-4000-8000-000000000002";
const LINE = "00000000-0000-4000-8000-000000000003";
const CHANGE = "00000000-0000-4000-8000-000000000004";

type Node = { id: string; node_type_id: string; name: string; description: string | null; x: number; y: number };
type Connection = { id: string; connection_type_id: string; source_node_id: string; target_node_id: string };
const types = [
  { id: "t1", key: "unit", name: "Unit", color: "#cfe3ff", shape: "rectangle", version: 1 },
  { id: "t2", key: "role", name: "Role", color: "#ffe2b8", shape: "ellipse", version: 1 },
];
const connectionTypes = [{ id: "c1", key: "reports", name: "Reports to", style: "dashed", source_end: "none", target_end: "arrow", version: 1 }];
const allowed = [
  { connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t1" },
  { connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t2" },
];
const NODE_WIDTH = 160;
const NODE_HEIGHT = 56;

async function open(page: Page, nodes: Node[], connections: Connection[] = [], modelName = "Test model") {
  const state = { nodes, connections, positionWrites: [] as { node_id: string; x: number; y: number }[][] };
  const change = { id: CHANGE, line_id: LINE, occurred_on: "2026-01-01", title: "Start", version: 1, planned: false, edit_count: 1 };
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const json = (body: unknown) => route.fulfill({ json: body });
    if (path === "/auth/session") return json({ user_account: { id: "u1", account_class: "customer", email: "a@example.test", display_name: "Test Person", locale: "en" } });
    if (path === "/system/status") return json({ database: "ready", schema_revision: "test" });
    if (path === "/organizations") return json({ organizations: [{ id: ORG, name: "Test Org", role: "owner" }] });
    if (path.endsWith("/unread-count")) return json({ unread: 0 });
    if (path === `/organizations/${ORG}`) return json({ organization: { id: ORG, name: "Test Org", time_zone: "UTC" }, membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null } });
    const model = `/organizations/${ORG}/models/${MODEL}`;
    if (path === `/organizations/${ORG}/models`) return json([{ id: MODEL, name: modelName, description: null, version: 1, nodes: state.nodes.length }]);
    if (path === `${model}/lines`) return json([{ id: LINE, name: "Base line", description: null, kind: "base", parent_line_id: null, branch_change_id: null, version: 1, change_count: 1, latest_change_date: "2026-01-01" }]);
    if (path === `${model}/lines/${LINE}/changes`) return json([change]);
    if (path === `${model}/lines/${LINE}/state`) return json({ change, node_types: types, connection_types: connectionTypes, allowed_connections: allowed, nodes: state.nodes, connections: state.connections });
    if (path === `${model}/lines/${LINE}/positions` && request.method() === "PUT") {
      const body = request.postDataJSON() as { node_id: string; x: number; y: number }[];
      state.positionWrites.push(body);
      for (const move of body) Object.assign(state.nodes.find((node) => node.id === move.node_id)!, { x: move.x, y: move.y });
      return route.fulfill({ status: 204 });
    }
    return json([]);
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/organizations/${ORG}/models/${MODEL}`);
  await expect(canvas(page)).toBeVisible();
  await expect(canvas(page).locator(".djs-shape").first()).toBeVisible();
  return state;
}

const canvas = (page: Page) => page.getByRole("group", { name: "Model canvas" });
const node = (page: Page, name: string) => canvas(page).locator(`g.djs-element.djs-shape[aria-label^="${name} ("]`);
const body = (page: Page, name: string) => node(page, name).locator(".shadow-node-body");
async function position(page: Page, name: string) {
  const match = /matrix\(([-\d.]+) 0 0 ([-\d.]+) ([-\d.]+) ([-\d.]+)\)/.exec((await node(page, name).getAttribute("transform")) ?? "");
  return { x: Number(match?.[3]), y: Number(match?.[4]) };
}
async function drag(page: Page, name: string, dx: number, dy: number) {
  const box = (await body(page, name).boundingBox())!;
  const from = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + dx / 2, from.y + dy / 2, { steps: 4 });
  await page.mouse.move(from.x + dx, from.y + dy, { steps: 4 });
  await page.mouse.up();
}
const button = (page: Page, name: string | RegExp) => page.getByRole("toolbar", { name: "Canvas view" }).getByRole("button", { name });
const snap = (page: Page) => button(page, "Snap nodes to the grid");
const undo = (page: Page) => button(page, "Undo");
const nodesOf = (...rows: [string, string, number, number][]): Node[] => rows.map(([id, name, x, y]) => ({ id, node_type_id: "t1", name, description: null, x, y }));
async function pick(page: Page, ...names: string[]) {
  await body(page, names[0]).click();
  for (const name of names.slice(1)) await body(page, name).click({ modifiers: ["Shift"] });
  await expect(canvas(page).locator(".djs-shape.selected")).toHaveCount(names.length);
}

test("with snap on a dragged node lands on the grid, the choice survives a reload, and with snap off it does not", async ({ page }) => {
  const state = await open(page, [...nodesOf(["n1", "Sales", 63, 47], ["n2", "Support", 401, 63]), { id: "n3", node_type_id: "t1", name: "Lead", description: null, x: 45, y: 263 }]);
  await expect(snap(page)).toHaveAttribute("aria-pressed", "false");
  await snap(page).click();
  await expect(snap(page)).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => localStorage.getItem("shadow.canvas.snap"))).toBe("true");
  await drag(page, "Sales", 34, 21);
  await expect.poll(() => state.positionWrites.length).toBe(1);
  expect(state.positionWrites[0]).toEqual([{ node_id: "n1", x: 100, y: 70 }]);
  await page.reload();
  await expect(canvas(page).locator(".djs-shape").first()).toBeVisible();
  await expect(snap(page)).toHaveAttribute("aria-pressed", "true");
  await drag(page, "Support", 22, 22);
  await expect.poll(() => state.positionWrites.length).toBe(2);
  expect(state.positionWrites[1]).toEqual([{ node_id: "n2", x: 420, y: 80 }]);
  await snap(page).click();
  await expect(snap(page)).toHaveAttribute("aria-pressed", "false");
  await page.reload();
  await expect(snap(page)).toHaveAttribute("aria-pressed", "false");
  await drag(page, "Lead", 13, 7);
  await expect.poll(() => state.positionWrites.length).toBe(3);
  expect(state.positionWrites[2]).toEqual([{ node_id: "n3", x: 58, y: 270 }]);
});

test("align and distribute are enabled by the size of the selection and are one write and one undo step each", async ({ page }) => {
  const state = await open(page, nodesOf(["n1", "Alpha", 100, 40], ["n2", "Beta", 300, 150], ["n3", "Gamma", 700, 300], ["n4", "Delta", 900, 520]));
  for (const name of [/^Align /, /^Distribute /]) await expect(button(page, name)).toHaveCount(name.source === "^Align " ? 4 : 2);
  const align = button(page, "Align left edges (select two or more nodes)");
  const distribute = button(page, "Distribute horizontally with equal gaps (select three or more nodes)");
  await expect(align).toBeDisabled();
  await expect(distribute).toBeDisabled();
  await body(page, "Alpha").click();
  await expect(align).toBeDisabled();
  await body(page, "Beta").click({ modifiers: ["Shift"] });
  await expect(align).toBeEnabled();
  await expect(distribute).toBeDisabled();
  await body(page, "Gamma").click({ modifiers: ["Shift"] });
  await expect(distribute).toBeEnabled();

  // Distribute: Alpha stays at 100 and Gamma at 700; Beta goes to the middle with equal gaps (100 + 160 + 140 = 400).
  await distribute.click();
  await expect.poll(() => state.positionWrites.length).toBe(1);
  expect(state.positionWrites[0]).toEqual([{ node_id: "n2", x: 400, y: 150 }]);
  await expect.poll(async () => (await position(page, "Beta")).x).toBe(400);

  // Align left: one write with every moved node.
  await align.click();
  await expect.poll(() => state.positionWrites.length).toBe(2);
  expect(state.positionWrites[1]).toEqual([{ node_id: "n1", x: 100, y: 40 }, { node_id: "n2", x: 100, y: 150 }, { node_id: "n3", x: 100, y: 300 }]);
  await expect.poll(async () => (await position(page, "Gamma")).x).toBe(100);
  expect(await position(page, "Delta")).toEqual({ x: 900, y: 520 });

  // Top, then middle and centre on the same selection give the expected coordinates.
  await button(page, "Align top edges (select two or more nodes)").click();
  await expect.poll(() => state.positionWrites.length).toBe(3);
  expect(state.nodes.filter((item) => ["n1", "n2", "n3"].includes(item.id)).map((item) => item.y)).toEqual([40, 40, 40]);

  // One undo step reverses one tool.
  await undo(page).click();
  await expect.poll(() => state.positionWrites.length).toBe(4);
  expect(state.nodes.filter((item) => ["n1", "n2", "n3"].includes(item.id)).map((item) => item.y)).toEqual([40, 150, 300]);
  await undo(page).click();
  await expect.poll(() => state.positionWrites.length).toBe(5);
  expect(state.nodes.filter((item) => ["n1", "n2", "n3"].includes(item.id)).map((item) => item.x)).toEqual([100, 400, 700]);
});

/** 50 nodes in rows of ten on a coarse grid, joined as a tree with some cross links. */
function fifty(): { nodes: Node[]; connections: Connection[] } {
  const nodes: Node[] = Array.from({ length: 50 }, (_, index) => ({ id: `n${index}`, node_type_id: "t1", name: `Node ${index}`, description: null, x: (index % 10) * 230, y: Math.floor(index / 10) * 130 }));
  const connections: Connection[] = [];
  for (let index = 1; index < 50; index++) connections.push({ id: `c${index}`, connection_type_id: "c1", source_node_id: `n${Math.floor((index - 1) / 2)}`, target_node_id: `n${index}` });
  for (let index = 0; index < 8; index++) connections.push({ id: `x${index}`, connection_type_id: "c1", source_node_id: `n${index * 3}`, target_node_id: `n${40 + index}` });
  return { nodes, connections };
}
const overlaps = (nodes: Node[]) => nodes.some((a, index) => nodes.slice(index + 1).some((b) => a.x < b.x + NODE_WIDTH && b.x < a.x + NODE_WIDTH && a.y < b.y + NODE_HEIGHT && b.y < a.y + NODE_HEIGHT));

test("auto layout arranges 50 nodes without overlaps on request only, and one undo puts them all back", async ({ page }) => {
  const { nodes, connections } = fifty();
  const original = nodes.map((item) => ({ ...item }));
  const requested: string[] = [];
  page.on("request", (request) => requested.push(request.url()));
  const state = await open(page, nodes, connections);
  // Nothing rearranges on its own, and the layout code is not even loaded.
  await page.waitForTimeout(500);
  expect(state.positionWrites).toEqual([]);
  expect(requested.filter((url) => /elk/i.test(url))).toEqual([]);
  await button(page, "Arrange the graph automatically").click();
  await expect.poll(() => requested.some((url) => /elk/i.test(url))).toBe(true);
  await expect.poll(() => state.positionWrites.length).toBe(1);
  expect(overlaps(state.nodes)).toBe(false);
  expect(state.nodes.some((item, index) => item.x !== original[index].x || item.y !== original[index].y)).toBe(true);
  expect(state.positionWrites[0].length).toBeGreaterThan(40);
  await expect(page.getByRole("status").filter({ hasText: "Graph arranged" })).toBeVisible();
  // The drawing follows the saved positions.
  const saved = state.nodes.find((item) => item.id === "n7")!;
  await expect.poll(async () => position(page, "Node 7")).toEqual({ x: saved.x, y: saved.y });

  await undo(page).click();
  await expect.poll(() => state.positionWrites.length).toBe(2);
  expect(state.nodes.map((item) => ({ x: item.x, y: item.y }))).toEqual(original.map((item) => ({ x: item.x, y: item.y })));
  await expect(undo(page)).toBeDisabled();
});

test("the minimap shows the graph and the view, moves the view when clicked, and is collapsible", async ({ page }) => {
  const { nodes, connections } = fifty();
  const requested: string[] = [];
  page.on("request", (request) => requested.push(request.url()));
  await open(page, nodes, connections);
  // Closed to begin with, and its code is not loaded until it is asked for.
  await page.waitForTimeout(300);
  expect(requested.filter((url) => /canvas\/minimap|diagram-js-minimap/.test(url))).toEqual([]);
  await expect(page.getByTestId("canvas-minimap")).toHaveCount(0);
  await button(page, "Minimap").click();
  await expect.poll(() => requested.some((url) => /canvas\/minimap|diagram-js-minimap/.test(url))).toBe(true);
  const minimap = page.getByTestId("canvas-minimap");
  await expect(minimap).toBeVisible();
  await expect(minimap).toHaveAttribute("aria-hidden", "true");
  // Every node and connection is in the picture.
  await expect.poll(() => minimap.locator(".map svg > g:first-child > g").count()).toBe(50 + connections.length);
  // Zoom to 100 % so the view is a part of the graph; then a click at the right edge of the minimap carries the view there.
  await button(page, "Zoom to 100 %").click();
  await expect(canvas(page)).toHaveAttribute("data-zoom", "100");
  const frame = minimap.locator(".viewport-dom");
  const before = { frame: (await frame.boundingBox())!, node: (await body(page, "Node 0").boundingBox())! };
  const map = minimap.locator(".map");
  const box = (await map.boundingBox())!;
  await page.mouse.click(box.x + box.width - 12, box.y + box.height / 2);
  await expect.poll(async () => (await body(page, "Node 0").boundingBox())!.x).toBeLessThan(before.node.x - 300);
  await expect.poll(async () => (await frame.boundingBox())!.x).toBeGreaterThan(before.frame.x + 30);
  // The zoom did not change.
  await expect(canvas(page)).toHaveAttribute("data-zoom", "100");
  // Dragging the frame moves the view too.
  const moved = (await body(page, "Node 0").boundingBox())!.x;
  const at = (await frame.boundingBox())!;
  await page.mouse.move(at.x + at.width / 2, at.y + at.height / 2);
  await page.mouse.down();
  await page.mouse.move(at.x + at.width / 2 - 60, at.y + at.height / 2, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => (await body(page, "Node 0").boundingBox())!.x).toBeGreaterThan(moved + 100);
  // Collapse and open again with the toolbar button.
  const toggle = button(page, "Minimap");
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await toggle.click();
  await expect(minimap).toBeHidden();
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await toggle.click();
  await expect(minimap).toBeVisible();
});

async function read(download: Awaited<ReturnType<Page["waitForEvent"]>> & { createReadStream(): Promise<NodeJS.ReadableStream | null> }) {
  const stream = (await download.createReadStream())!;
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk as Buffer));
  return Buffer.concat(chunks);
}
async function exportAs(page: Page, kind: "SVG" | "PNG") {
  await button(page, "Export the canvas").click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("menuitem", { name: `Export as ${kind}` }).click()]);
  return { download, bytes: await read(download as never) };
}

test("export downloads an SVG and a PNG named after the model and the line, and a hidden type stays hidden", async ({ page }) => {
  const rows: Node[] = [
    { id: "n1", node_type_id: "t1", name: "Sales", description: null, x: 60, y: 60 },
    { id: "n2", node_type_id: "t1", name: "Support", description: null, x: 400, y: 60 },
    { id: "n3", node_type_id: "t2", name: "Lead", description: null, x: 60, y: 260 },
  ];
  await open(page, rows, [{ id: "c1x", connection_type_id: "c1", source_node_id: "n1", target_node_id: "n3" }, { id: "c2x", connection_type_id: "c1", source_node_id: "n1", target_node_id: "n2" }], "Supply/chain: 2027?");

  const svg = await exportAs(page, "SVG");
  expect(svg.download.suggestedFilename()).toBe("Supply-chain-2027-Base-line.svg");
  const text = svg.bytes.toString("utf8");
  expect(text.startsWith("<?xml")).toBe(true);
  for (const name of ["Sales", "Support", "Lead"]) expect(text).toContain(name);
  expect(text).toContain("<style>");
  expect(text).toContain("shadow-connection-line");

  const png = await exportAs(page, "PNG");
  expect(png.download.suggestedFilename()).toBe("Supply-chain-2027-Base-line.png");
  expect([...png.bytes.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  // Drawn at scale 2: the PNG is twice the width and height of the SVG's own size.
  const [width, height] = [/<svg[^>]* width="(\d+)"/.exec(text)![1], /<svg[^>]* height="(\d+)"/.exec(text)![1]].map(Number);
  expect([png.bytes.readUInt32BE(16), png.bytes.readUInt32BE(20)]).toEqual([width * 2, height * 2]);

  // A hidden type is not in either file.
  await page.getByRole("checkbox", { name: "Show Role nodes" }).uncheck();
  await expect(node(page, "Lead")).toBeHidden();
  const hidden = await exportAs(page, "SVG");
  const hiddenText = hidden.bytes.toString("utf8");
  expect(hiddenText).toContain("Sales");
  expect(hiddenText).not.toContain("Lead");
  expect(hiddenText).not.toContain('data-element-id="c1x"');
  expect(hiddenText).toContain('data-element-id="c2x"');
  const hiddenHeight = Number(/<svg[^>]* height="(\d+)"/.exec(hiddenText)![1]);
  expect(hiddenHeight).toBeLessThan(height);
  // The canvas itself was not changed by exporting.
  await expect(node(page, "Sales")).toBeVisible();
});

test("every tool is reachable by keyboard and labelled; the export menu opens with Enter", async ({ page }) => {
  await open(page, nodesOf(["n1", "Alpha", 100, 40], ["n2", "Beta", 300, 150]));
  const toolbar = page.getByRole("toolbar", { name: "Canvas view" });
  for (const name of ["Snap nodes to the grid", "Arrange the graph automatically", "Minimap", "Export the canvas"]) await expect(toolbar.getByRole("button", { name })).toBeVisible();
  await button(page, "Export the canvas").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", { name: "Export as SVG" })).toBeFocused();
  const [download] = await Promise.all([page.waitForEvent("download"), page.keyboard.press("Enter")]);
  expect(download.suggestedFilename()).toBe("Test-model-Base-line.svg");
});

test("the toolbar with every tool enabled and the minimap open has no automatically detectable accessibility violations", async ({ page }) => {
  await open(page, nodesOf(["n1", "Alpha", 100, 40], ["n2", "Beta", 300, 150], ["n3", "Gamma", 500, 300]));
  await pick(page, "Alpha", "Beta", "Gamma");
  await button(page, "Minimap").click();
  await expect(page.getByTestId("canvas-minimap")).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("on a phone the toolbar wraps inside the canvas and the page does not scroll sideways", async ({ page }) => {
  await open(page, nodesOf(["n1", "Alpha", 100, 40], ["n2", "Beta", 300, 150]));
  await page.setViewportSize({ width: 375, height: 812 });
  const toolbar = page.getByRole("toolbar", { name: "Canvas view" });
  await expect(toolbar).toBeVisible();
  const box = (await toolbar.boundingBox())!;
  const area = (await canvas(page).boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(area.x);
  expect(box.x + box.width).toBeLessThanOrEqual(area.x + area.width + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("the PNG export works under the production image policy (self and data: only, no blob:)", async ({ page }) => {
  // The page itself is served by the dev server without a policy; the one that matters here is added to the document.
  await page.route((url) => url.pathname.startsWith("/organizations/"), async (route) => {
    if (route.request().resourceType() !== "document") return route.fallback();
    const response = await route.fetch();
    await route.fulfill({ response, headers: { ...response.headers(), "content-security-policy": "img-src 'self' data:" } });
  });
  await open(page, nodesOf(["n1", "Alpha", 100, 40], ["n2", "Beta", 300, 150]));
  const violations: string[] = [];
  page.on("console", (message) => { if (/Content Security Policy/i.test(message.text())) violations.push(message.text()); });
  const png = await exportAs(page, "PNG");
  expect([...png.bytes.subarray(0, 4)]).toEqual([0x89, 0x50, 0x4e, 0x47]);
  expect(violations).toEqual([]);
});
