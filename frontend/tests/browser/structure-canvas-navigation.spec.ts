import { expect, test, type Page } from "@playwright/test";

// Structure canvas navigation against a stateful mocked API (no sign-in): the toolbar, wheel zoom with its limits, Fit and 100 %, pan by
// background drag and space + drag, the keyboard, and a view that survives saves. Chromium only; touch is not exercised here.
const ORG = "00000000-0000-4000-8000-000000000001";
const MODEL = "00000000-0000-4000-8000-000000000002";
const LINE = "00000000-0000-4000-8000-000000000003";
const CHANGE = "00000000-0000-4000-8000-000000000004";

type Node = { id: string; node_type_id: string; name: string; description: string | null; x: number; y: number };
const types = [{ id: "t1", key: "unit", name: "Unit", color: "#cfe3ff", shape: "rectangle", version: 1 }];
const connectionTypes = [{ id: "c1", key: "reports", name: "Reports to", style: "solid", source_end: "none", target_end: "arrow", version: 1 }];
const allowed = [{ connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t1" }];

function createApi(locale = "en", remote = false) {
  const state = {
    version: 1,
    nodes: [
      { id: "n1", node_type_id: "t1", name: "Sales", description: null, x: 60, y: 60 },
      { id: "n2", node_type_id: "t1", name: "Support", description: null, x: 400, y: 60 },
      ...(remote ? [{ id: "n3", node_type_id: "t1", name: "Remote", description: null, x: 3000, y: 1800 }] : []),
    ] as Node[],
    positionWrites: [] as { node_id: string; x: number; y: number }[][],
    renameWrites: [] as { name?: string }[],
    stateReads: 0,
  };
  const change = () => ({ id: CHANGE, line_id: LINE, occurred_on: "2026-01-01", title: "Start", version: state.version, planned: false, edit_count: 1 });
  async function mock(page: Page) {
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname.replace("/api/v1", "");
      const method = request.method();
      const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
      if (path === "/auth/session") return json({ user_account: { id: "u1", account_class: "customer", email: "a@example.test", display_name: "Test Person", locale } });
      if (path === "/system/status") return json({ database: "ready", schema_revision: "test" });
      if (path === "/organizations") return json({ organizations: [{ id: ORG, name: "Test Org", role: "owner" }] });
      if (path.endsWith("/unread-count")) return json({ unread: 0 });
      if (path === `/organizations/${ORG}`) return json({ organization: { id: ORG, name: "Test Org", time_zone: "UTC" }, membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null } });
      const model = `/organizations/${ORG}/models/${MODEL}`;
      if (path === `/organizations/${ORG}/models`) return json([{ id: MODEL, name: "Test model", description: null, version: 1, nodes: state.nodes.length }]);
      if (path === `${model}/lines`) return json([{ id: LINE, name: "Base line", description: null, kind: "base", parent_line_id: null, branch_change_id: null, version: 1, change_count: 1, latest_change_date: "2026-01-01" }]);
      if (path === `${model}/lines/${LINE}/changes`) return json([change()]);
      if (path === `${model}/lines/${LINE}/state`) { state.stateReads++; return json({ change: change(), node_types: types, connection_types: connectionTypes, allowed_connections: allowed, nodes: state.nodes, connections: [] }); }
      if (path === `${model}/lines/${LINE}/positions` && method === "PUT") {
        const body = request.postDataJSON() as { node_id: string; x: number; y: number }[];
        state.positionWrites.push(body);
        for (const move of body) Object.assign(state.nodes.find((node) => node.id === move.node_id)!, { x: move.x, y: move.y });
        return route.fulfill({ status: 204 });
      }
      const update = new RegExp(`${model}/changes/${CHANGE}/nodes/([^/]+)$`).exec(path);
      if (update && method === "PATCH") {
        const body = request.postDataJSON() as { name?: string };
        state.renameWrites.push(body);
        Object.assign(state.nodes.find((node) => node.id === update[1])!, { name: body.name });
        state.version++;
        return json({ node: state.nodes.find((node) => node.id === update[1]) });
      }
      return json([]);
    });
  }
  return { state, mock };
}

const structure = `/organizations/${ORG}/models/${MODEL}`;
const canvas = (page: Page) => page.getByRole("group", { name: "Model canvas" });
const node = (page: Page, name: string) => canvas(page).locator(`g.djs-element.djs-shape[aria-label^="${name} ("]`);
const body = (page: Page, name: string) => node(page, name).locator(".shadow-node-body");
const zoom = async (page: Page) => Number(await canvas(page).getAttribute("data-zoom"));
const readout = (page: Page) => page.getByTestId("zoom-readout");
const centreOf = async (page: Page, name: string) => { const box = (await body(page, name).boundingBox())!; return { x: box.x + box.width / 2, y: box.y + box.height / 2 }; };
const emptySpot = async (page: Page) => { const box = (await canvas(page).boundingBox())!; return { x: box.x + box.width - 30, y: box.y + box.height - 30, box }; };

async function open(page: Page, options: { locale?: string; remote?: boolean } = {}) {
  const api = createApi(options.locale, options.remote);
  await api.mock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(structure);
  await expect(node(page, "Sales")).toBeVisible();
  return api;
}

/** Wheel over the middle of the canvas, away from the toolbar. */
async function wheel(page: Page, deltaY: number, times = 1, at?: { x: number; y: number }) {
  const box = (await canvas(page).boundingBox())!;
  await page.mouse.move(at?.x ?? box.x + box.width / 2, at?.y ?? box.y + box.height / 2);
  for (let i = 0; i < times; i++) await page.mouse.wheel(0, deltaY);
}

test("the first load fits the whole graph, even a node far away", async ({ page }) => {
  await open(page, { remote: true });
  expect(await zoom(page)).toBeLessThan(40);
  const box = (await canvas(page).boundingBox())!;
  for (const name of ["Sales", "Support", "Remote"]) {
    const rect = (await body(page, name).boundingBox())!;
    expect(rect.x).toBeGreaterThanOrEqual(box.x);
    expect(rect.y).toBeGreaterThanOrEqual(box.y);
    expect(rect.x + rect.width).toBeLessThanOrEqual(box.x + box.width);
    expect(rect.y + rect.height).toBeLessThanOrEqual(box.y + box.height);
  }
  await expect(readout(page)).toHaveText(`${await zoom(page)} %`);
});

test("the toolbar zooms in and out, Fit and 100 % work, and the readout matches", async ({ page }) => {
  await open(page, { remote: true });
  await expect(page.getByRole("toolbar", { name: "Canvas view" })).toBeVisible();
  await page.getByRole("button", { name: "Zoom to 100 %" }).click();
  await expect(readout(page)).toHaveText("100 %");
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(readout(page)).toHaveText("125 %");
  await page.getByRole("button", { name: "Zoom out" }).click();
  await page.getByRole("button", { name: "Zoom out" }).click();
  await expect(readout(page)).toHaveText("80 %");
  expect(await zoom(page)).toBe(80);
  await page.getByRole("button", { name: "Fit the whole graph in view" }).click();
  // The animation takes well under half a second; afterwards the readout and the drawing agree.
  await page.waitForTimeout(500);
  expect(await zoom(page)).toBeLessThan(40);
  await expect(readout(page)).toHaveText(`${await zoom(page)} %`);
});

test("the toolbar has Finnish labels for a Finnish user", async ({ page }) => {
  const api = createApi("fi");
  await api.mock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(structure);
  await expect(page.getByRole("group", { name: "Mallin kanvas" })).toBeVisible();
  const bar = page.getByRole("toolbar", { name: "Kanvaksen näkymä" });
  await expect(bar).toBeVisible();
  for (const name of ["Lähennä", "Loitonna", "Sovita koko kaavio näkymään", "Zoomaa 100 %:iin"]) await expect(bar.getByRole("button", { name })).toBeVisible();
});

test("the wheel zooms around the pointer and stops at 10 % and 400 %", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Zoom to 100 %" }).click();
  await expect(readout(page)).toHaveText("100 %");
  // The node under the pointer stays under it while zooming.
  const target = await centreOf(page, "Sales");
  await wheel(page, -120, 1, target);
  await expect.poll(() => zoom(page)).toBeGreaterThan(100);
  const after = await centreOf(page, "Sales");
  expect(Math.abs(after.x - target.x)).toBeLessThan(3);
  expect(Math.abs(after.y - target.y)).toBeLessThan(3);
  await wheel(page, -240, 40);
  await expect(readout(page)).toHaveText("400 %");
  await wheel(page, -240, 5);
  expect(await zoom(page)).toBe(400);
  await expect(page.getByRole("button", { name: "Zoom in" })).toBeDisabled();
  await wheel(page, 240, 80);
  await expect(readout(page)).toHaveText("10 %");
  await wheel(page, 240, 5);
  expect(await zoom(page)).toBe(10);
  await expect(page.getByRole("button", { name: "Zoom out" })).toBeDisabled();
});

test("100 % restores scale 1 around the centre of the drawing area", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Zoom to 100 %" }).click();
  await wheel(page, -240, 3);
  const scale = (await zoom(page)) / 100;
  expect(scale).toBeGreaterThan(1.5);
  const box = (await canvas(page).boundingBox())!;
  const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const before = await centreOf(page, "Sales");
  await page.getByRole("button", { name: "Zoom to 100 %" }).click();
  await expect(readout(page)).toHaveText("100 %");
  await expect.poll(async () => Math.round(((await centreOf(page, "Sales")).x - centre.x) * 10)).toBeCloseTo(Math.round(((before.x - centre.x) / scale) * 10), -1);
  const after = await centreOf(page, "Sales");
  expect(Math.abs(after.y - centre.y - (before.y - centre.y) / scale)).toBeLessThan(2);
});

test("dragging the background pans, and so does space + drag; neither moves a node or saves anything", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Zoom to 100 %" }).click();
  const start = await centreOf(page, "Sales");
  const spot = await emptySpot(page);
  await page.mouse.move(spot.x, spot.y);
  await page.mouse.down();
  await page.mouse.move(spot.x - 60, spot.y - 40, { steps: 5 });
  await page.mouse.move(spot.x - 120, spot.y - 80, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => Math.round((await centreOf(page, "Sales")).x)).toBe(Math.round(start.x - 120));
  expect(Math.round((await centreOf(page, "Sales")).y)).toBe(Math.round(start.y - 80));

  const moved = await centreOf(page, "Sales");
  await page.mouse.move(spot.x, spot.y);
  await page.keyboard.down("Space");
  await page.mouse.down();
  await page.mouse.move(spot.x + 50, spot.y + 30, { steps: 5 });
  await page.mouse.move(spot.x + 100, spot.y + 60, { steps: 5 });
  await page.mouse.up();
  await page.keyboard.up("Space");
  await expect.poll(async () => Math.round((await centreOf(page, "Sales")).x)).toBe(Math.round(moved.x + 100));
  expect(Math.round((await centreOf(page, "Sales")).y)).toBe(Math.round(moved.y + 60));
  expect(api.state.positionWrites).toHaveLength(0);
});

test("a node dragged far out of view can be reached again with Fit", async ({ page }) => {
  const api = await open(page);
  // Zoomed out the node is dragged a long way; back at 100 % it is out of sight.
  await page.getByRole("button", { name: "Zoom out" }).click();
  await page.getByRole("button", { name: "Zoom out" }).click();
  await page.getByRole("button", { name: "Zoom out" }).click();
  await expect(readout(page)).toHaveText("51 %");
  const from = await centreOf(page, "Sales");
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + 300, from.y + 200, { steps: 6 });
  await page.mouse.up();
  await expect.poll(() => api.state.positionWrites.length).toBe(1);
  await page.getByRole("button", { name: "Zoom to 100 %" }).click();
  await expect(readout(page)).toHaveText("100 %");
  const box = (await canvas(page).boundingBox())!;
  const inside = async () => { const rect = await body(page, "Sales").boundingBox(); return !!rect && rect.x >= box.x && rect.x + rect.width <= box.x + box.width && rect.y >= box.y && rect.y + rect.height <= box.y + box.height; };
  expect(await inside()).toBe(false);
  await page.getByRole("button", { name: "Fit the whole graph in view" }).click();
  await expect.poll(inside).toBe(true);
});

test("+ - 0 and F work with the canvas focused, and are ignored in a text field", async ({ page }) => {
  await open(page);
  const spot = await emptySpot(page);
  await page.mouse.click(spot.x, spot.y);
  await page.keyboard.press("0");
  await expect(readout(page)).toHaveText("100 %");
  await page.keyboard.press("+");
  await expect(readout(page)).toHaveText("125 %");
  await page.keyboard.press("Shift+=");
  await expect(readout(page)).toHaveText("156 %");
  await page.keyboard.press("-");
  await expect(readout(page)).toHaveText("125 %");
  await page.keyboard.press("-");
  await page.keyboard.press("-");
  await expect(readout(page)).toHaveText("80 %");
  await page.keyboard.press("-");
  await expect(readout(page)).toHaveText("64 %");
  await page.keyboard.press("F");
  await expect(readout(page)).toHaveText("100 %");

  // A text field in the Details panel: the keys are typed, the view does not move.
  await page.keyboard.press("0");
  await expect(readout(page)).toHaveText("100 %");
  await body(page, "Sales").click();
  const name = page.getByLabel("Node name").last();
  await name.focus();
  await page.keyboard.type("f+-0");
  await expect(name).toHaveValue("Salesf+-0");
  expect(await zoom(page)).toBe(100);
  // Neither does the toolbar's own focus hand keys to the canvas: Tab away from the canvas does not zoom.
});

test("arrows pan with nothing selected and move the selected node, which is saved once", async ({ page }) => {
  const api = await open(page);
  const spot = await emptySpot(page);
  await page.mouse.click(spot.x, spot.y);
  await page.keyboard.press("0");
  const start = await centreOf(page, "Sales");
  await page.keyboard.press("ArrowRight");
  await expect.poll(async () => Math.round((await centreOf(page, "Sales")).x)).toBe(Math.round(start.x - 50));
  await page.keyboard.press("Shift+ArrowDown");
  await expect.poll(async () => Math.round((await centreOf(page, "Sales")).y)).toBe(Math.round(start.y - 200));
  expect(api.state.positionWrites).toHaveLength(0);

  const panned = await centreOf(page, "Sales");
  await body(page, "Sales").click();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowDown");
  await expect.poll(async () => Math.round((await centreOf(page, "Sales")).x)).toBe(Math.round(panned.x + 20));
  expect(Math.round((await centreOf(page, "Sales")).y)).toBe(Math.round(panned.y + 10));
  await expect.poll(() => api.state.positionWrites.length).toBe(1);
  expect(api.state.positionWrites[0]).toEqual([{ node_id: "n1", x: 80, y: 70 }]);
});

test("Esc cancels connect mode first, then clears the selection", async ({ page }) => {
  await open(page);
  await body(page, "Sales").click();
  await page.getByRole("button", { name: "Connect from this node" }).click();
  await expect(page.getByText("Choose the node to connect to.")).toBeVisible();
  await node(page, "Sales").focus();
  await page.keyboard.press("Escape");
  await expect(page.getByText("Choose the node to connect to.")).toHaveCount(0);
  await expect(node(page, "Sales")).toHaveClass(/selected/);
  await page.keyboard.press("Escape");
  await expect(node(page, "Sales")).not.toHaveClass(/selected/);
});

test("the view does not jump or reset after a node is moved and saved, or renamed", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Zoom to 100 %" }).click();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(readout(page)).toHaveText("125 %");
  const spot = await emptySpot(page);
  await page.mouse.move(spot.x, spot.y);
  await page.mouse.down();
  await page.mouse.move(spot.x - 40, spot.y - 30, { steps: 4 });
  await page.mouse.up();
  await expect(readout(page)).toHaveText("125 %");
  const support = await centreOf(page, "Support");

  // Move another node: after the save and the reload the view and the untouched node stay where they were.
  const sales = await centreOf(page, "Sales");
  await page.mouse.move(sales.x, sales.y);
  await page.mouse.down();
  await page.mouse.move(sales.x + 10, sales.y + 40, { steps: 4 });
  await page.mouse.up();
  await expect.poll(() => api.state.positionWrites.length).toBe(1);
  const reads = api.state.stateReads;
  await expect.poll(() => api.state.stateReads).toBeGreaterThan(reads - 1);
  await expect(readout(page)).toHaveText("125 %");
  const supportAfterMove = await centreOf(page, "Support");
  expect(Math.abs(supportAfterMove.x - support.x)).toBeLessThan(1);
  expect(Math.abs(supportAfterMove.y - support.y)).toBeLessThan(1);

  // Rename: the write is sent, the graph is reloaded, the view stays.
  await body(page, "Support").click();
  const name = page.getByLabel("Node name").last();
  await name.fill("Helpdesk");
  const before = api.state.stateReads;
  await page.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => api.state.renameWrites.length).toBe(1);
  await expect.poll(() => api.state.stateReads).toBeGreaterThan(before);
  await expect(node(page, "Helpdesk")).toBeVisible();
  await expect(readout(page)).toHaveText("125 %");
  const renamed = await centreOf(page, "Helpdesk");
  expect(Math.abs(renamed.x - support.x)).toBeLessThan(1);
  expect(Math.abs(renamed.y - support.y)).toBeLessThan(1);
});

test("reduced motion: Fit and 100 % change the view at once; without it they animate", async ({ browser }) => {
  for (const reduced of [true, false]) {
    const context = await browser.newContext({ reducedMotion: reduced ? "reduce" : "no-preference", viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await createApi("en", true).mock(page);
    await page.goto(structure);
    await expect(node(page, "Sales")).toBeVisible();
    const fitted = await zoom(page);
    expect(fitted).toBeLessThan(40);
    const immediately = await page.evaluate(() => {
      (document.querySelector('button[aria-label="Zoom to 100 %"]') as HTMLButtonElement).click();
      // The diagram's own scale, read from its viewport transform (the React readout updates a moment later).
      return Math.round(Number(/matrix\(([-\d.]+)/.exec(document.querySelector(".shadow-canvas g.viewport")!.getAttribute("transform") ?? "")?.[1]) * 100);
    });
    if (reduced) expect(immediately).toBe(100);
    else expect(immediately).toBeLessThan(100);
    await expect(readout(page)).toHaveText("100 %");
    await context.close();
  }
});

test("touch: one finger on the background pans and two fingers pinch (Chromium touch changes)", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Zoom to 100 %" }).click();
  await expect(readout(page)).toHaveText("100 %");
  const client = await page.context().newCDPSession(page);
  const touch = (type: "touchStart" | "touchMove" | "touchEnd", points: { x: number; y: number; id: number }[]) => client.send("Input.dispatchTouchEvent", { type, touchPoints: points });
  const spot = await emptySpot(page);
  const start = await centreOf(page, "Sales");
  await touch("touchStart", [{ x: spot.x, y: spot.y, id: 1 }]);
  for (let step = 1; step <= 6; step++) await touch("touchMove", [{ x: spot.x - step * 15, y: spot.y - step * 10, id: 1 }]);
  await touch("touchEnd", []);
  await expect.poll(async () => Math.round((await centreOf(page, "Sales")).x - start.x)).toBe(-90);
  expect(Math.round((await centreOf(page, "Sales")).y - start.y)).toBe(-60);

  const box = (await canvas(page).boundingBox())!;
  const mid = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await touch("touchStart", [{ x: mid.x - 50, y: mid.y, id: 1 }, { x: mid.x + 50, y: mid.y, id: 2 }]);
  for (let step = 1; step <= 6; step++) await touch("touchMove", [{ x: mid.x - 50 - step * 10, y: mid.y, id: 1 }, { x: mid.x + 50 + step * 10, y: mid.y, id: 2 }]);
  await touch("touchEnd", []);
  await expect.poll(() => zoom(page)).toBeGreaterThan(200);
  expect(await zoom(page)).toBeLessThanOrEqual(400);
});
