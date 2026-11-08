import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Drawing on the Structure canvas against a stateful mocked API that checks `expected_version` like the real routes: a new node named in
// place at the centre of the view, both connect gestures, the three refusals, delete with a confirmation, several nodes moved together,
// undo and redo, and a second session that changes things behind the first one's back.
import { ORG, MODEL, createApi } from "./canvas-mock-api";

const canvas = (page: Page) => page.getByRole("group", { name: "Model canvas" });
const node = (page: Page, name: string) => canvas(page).locator(`g.djs-element.djs-shape[aria-label^="${name} ("]`);
const body = (page: Page, name: string) => node(page, name).locator(".shadow-node-body");
const connections = (page: Page) => canvas(page).locator(".djs-connection");
const alert = (page: Page) => page.getByRole("alert");
/** The name field drawn over a node (not the details panel's field of the same name). */
const editor = (page: Page) => canvas(page).getByRole("textbox", { name: "Node name" });
async function position(page: Page, name: string) {
  const match = /matrix\(([-\d.]+) 0 0 ([-\d.]+) ([-\d.]+) ([-\d.]+)\)/.exec((await node(page, name).getAttribute("transform")) ?? "");
  return { x: Number(match?.[3]), y: Number(match?.[4]) };
}
async function open(page: Page, writable = true) {
  const api = createApi(writable);
  await api.mock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/organizations/${ORG}/models/${MODEL}`);
  await expect(node(page, "Sales")).toBeVisible();
  return api;
}
async function centreOf(page: Page, locator: ReturnType<Page["locator"]>) {
  const box = (await locator.boundingBox())!;
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}
async function drag(page: Page, name: string, dx: number, dy: number) {
  const from = await centreOf(page, body(page, name));
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + dx / 2, from.y + dy / 2, { steps: 4 });
  await page.mouse.move(from.x + dx, from.y + dy, { steps: 4 });
  await page.mouse.up();
}
async function connectByClicks(page: Page, from: string, to: string) {
  await body(page, from).click();
  await page.getByRole("button", { name: "Connect nodes (click the first node, then the second)" }).click();
  await body(page, from).click();
  await body(page, to).click();
}
const undo = (page: Page) => page.getByRole("button", { name: "Undo", exact: true });
const redo = (page: Page) => page.getByRole("button", { name: "Redo", exact: true });
const confirmDelete = (page: Page) => page.getByRole("button", { name: "Delete", exact: true }).last();

test("a new node opens for naming at the centre of the view, at a zoom and pan that are not the default", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Zoom in" }).click();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(canvas(page)).toHaveAttribute("data-zoom", "156");
  await canvas(page).focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: "Add a Unit node" }).click();
  const field = editor(page);
  await expect(editor(page)).toBeFocused();
  const area = (await canvas(page).boundingBox())!;
  const at = await centreOf(page, editor(page));
  expect(Math.abs(at.x - (area.x + area.width / 2))).toBeLessThan(3);
  expect(Math.abs(at.y - (area.y + area.height / 2))).toBeLessThan(3);
  expect(api.state.writes).toEqual([]);
  await editor(page).fill("Finance");
  await page.keyboard.press("Enter");
  await expect(node(page, "Finance")).toBeVisible();
  expect(api.state.bodies[0]).toMatchObject({ name: "Finance", node_type_id: "t1" });
  const saved = api.state.nodes.at(-1)!;
  // The node is redrawn when the server's answer is loaded, so measure it once it is there (this used to fail about one run in three).
  await expect.poll(async () => { const box = await body(page, "Finance").boundingBox(); return box ? Math.abs(box.x + box.width / 2 - (area.x + area.width / 2)) : 999; }).toBeLessThan(3);
  expect(saved.name).toBe("Finance");
});

test("Esc cancels a node that is being named: nothing is sent and nothing stays", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Add a Unit node" }).click();
  await editor(page).fill("Draft");
  await page.keyboard.press("Escape");
  await expect(editor(page)).toHaveCount(0);
  await expect(canvas(page).locator(".djs-shape")).toHaveCount(3);
  expect(api.state.writes).toEqual([]);
});

test("a node is renamed in place by a double-click, and F2", async ({ page }) => {
  const api = await open(page);
  await body(page, "Sales").dblclick();
  const field = editor(page);
  await expect(field).toHaveValue("Sales");
  await field.fill("Revenue");
  await page.keyboard.press("Enter");
  await expect(node(page, "Revenue")).toBeVisible();
  await body(page, "Support").click();
  await page.keyboard.press("F2");
  await expect(editor(page)).toHaveValue("Support");
  await page.keyboard.press("Escape");
  expect(api.state.writes).toEqual(["PATCH nodes/n1"]);
});

test("connect by the context pad (drag) and by the Connect button with two clicks give the same connection", async ({ page }) => {
  const api = await open(page);
  await body(page, "Sales").click();
  const pad = page.getByRole("button", { name: "Connect to another node" });
  await expect(pad).toBeVisible();
  const from = await centreOf(page, pad);
  const to = await centreOf(page, body(page, "Support"));
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move((from.x + to.x) / 2, (from.y + to.y) / 2, { steps: 5 });
  await page.mouse.move(to.x, to.y, { steps: 5 });
  await page.mouse.up();
  // Reports to and Supports both fit Unit to Unit, so the person is asked which.
  await expect(page.getByRole("dialog", { name: "Choose the connection" })).toBeVisible();
  await page.getByRole("button", { name: "Reports to" }).click();
  await expect(connections(page)).toHaveCount(1);
  const dragBody = api.state.bodies.at(-1);
  expect(dragBody).toMatchObject({ connection_type_id: "c1", source_node_id: "n1", target_node_id: "n2" });

  // Undo, then the same through the toolbar: C, the first node, the second.
  await undo(page).click();
  await expect(connections(page)).toHaveCount(0);
  await connectByClicks(page, "Sales", "Support");
  await page.getByRole("button", { name: "Reports to" }).click();
  await expect(connections(page)).toHaveCount(1);
  expect(api.state.bodies.at(-1)).toMatchObject({ connection_type_id: "c1", source_node_id: "n1", target_node_id: "n2" });
});

test("the C key starts connect mode from the canvas and Esc leaves it", async ({ page }) => {
  await open(page);
  await node(page, "Sales").focus();
  await page.keyboard.press("c");
  await expect(page.getByRole("button", { name: /^Connect nodes/ })).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: /^Connect nodes/ })).toHaveAttribute("aria-pressed", "false");
});

test("self-connection, a duplicate and a type the Metamodel does not allow each get their own message and are never sent", async ({ page }) => {
  const api = await open(page);
  await connectByClicks(page, "Lead", "Sales");
  await expect(alert(page)).toHaveText("The model does not allow a connection from a Role node to a Unit node.");
  await connectByClicks(page, "Sales", "Sales");
  await expect(alert(page)).toHaveText("A node cannot be connected to itself.");
  expect(api.state.writes).toEqual([]);
  // Two types fit Unit to Unit; connect with the panel's single type until both exist, then the duplicate message appears.
  api.state.connections.push({ id: "k1", connection_type_id: "c1", source_node_id: "n1", target_node_id: "n2" }, { id: "k2", connection_type_id: "c2", source_node_id: "n1", target_node_id: "n2" });
  await page.reload();
  await expect(connections(page)).toHaveCount(2);
  await connectByClicks(page, "Sales", "Support");
  await expect(alert(page)).toHaveText("These two nodes are already connected in this direction with this connection.");
  expect(api.state.writes).toEqual([]);
});

test("Delete asks first, names the connections that go with the node, and Cancel keeps everything", async ({ page }) => {
  const api = await open(page);
  api.state.connections.push({ id: "k1", connection_type_id: "c1", source_node_id: "n1", target_node_id: "n2" });
  await page.reload();
  await expect(connections(page)).toHaveCount(1);
  await body(page, "Sales").click();
  await page.keyboard.press("Delete");
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("Delete the node “Sales”? Its connection will also be deleted: Sales → Support (Reports to). You can undo this.");
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(node(page, "Sales")).toBeVisible();
  expect(api.state.writes).toEqual([]);
  await canvas(page).locator(`g[data-element-id="n1"]`).focus();
  await page.keyboard.press("Backspace");
  await confirmDelete(page).click();
  await expect(node(page, "Sales")).toHaveCount(0);
  await expect(connections(page)).toHaveCount(0);
});

test("shift-click selects several nodes and a drag moves them together with one positions write", async ({ page }) => {
  const api = await open(page);
  await body(page, "Sales").click();
  await body(page, "Support").click({ modifiers: ["Shift"] });
  await expect(canvas(page).locator(".djs-shape.selected")).toHaveCount(2);
  await expect(page.getByRole("heading", { name: "2 elements selected" })).toBeVisible();
  await drag(page, "Sales", 100, 80);
  await expect.poll(() => api.state.positionWrites.length).toBe(1);
  expect(api.state.positionWrites[0]).toEqual([{ node_id: "n1", x: 160, y: 140 }, { node_id: "n2", x: 500, y: 140 }]);
  expect(await position(page, "Support")).toEqual({ x: 500, y: 140 });
  // One undo puts both back.
  await undo(page).click();
  await expect.poll(() => api.state.positionWrites.length).toBe(2);
  expect(api.state.positionWrites[1]).toEqual([{ node_id: "n1", x: 60, y: 60 }, { node_id: "n2", x: 400, y: 60 }]);
  await expect.poll(async () => (await position(page, "Sales")).x).toBe(60);
  await expect(undo(page)).toBeDisabled();
  await expect(redo(page)).toBeEnabled();
});

test("the lasso toggle selects what the rectangle encloses, and the selection is deleted as a set", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Select several nodes (drag a rectangle)" }).click();
  const area = (await canvas(page).boundingBox())!;
  const a = await centreOf(page, body(page, "Sales"));
  const b = await centreOf(page, body(page, "Support"));
  await page.mouse.move(a.x - 120, a.y - 70);
  await page.mouse.down();
  await page.mouse.move(b.x + 120, b.y + 60, { steps: 8 });
  await page.mouse.up();
  await expect(canvas(page).locator(".djs-shape.selected")).toHaveCount(2);
  expect(area.width).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect(page.getByRole("alertdialog")).toContainText("Delete 2 nodes (Sales, Support)?");
  await confirmDelete(page).click();
  await expect(canvas(page).locator(".djs-shape")).toHaveCount(1);
  await expect.poll(() => api.state.writes).toEqual(["DELETE nodes/n1", "DELETE nodes/n2"]);
  // One undo step brings both back, with their names and places.
  await undo(page).click();
  await expect(node(page, "Sales")).toBeVisible();
  await expect(node(page, "Support")).toBeVisible();
  expect(await position(page, "Sales")).toEqual({ x: 60, y: 60 });
  expect(await position(page, "Support")).toEqual({ x: 400, y: 60 });
  await expect(undo(page)).toBeDisabled();
});

test("add, rename, delete, then undo three times and redo once; shortcuts work and the buttons follow the history", async ({ page }) => {
  const api = await open(page);
  await expect(undo(page)).toBeDisabled();
  await expect(redo(page)).toBeDisabled();
  await page.getByRole("button", { name: "Add a Unit node" }).click();
  await editor(page).fill("Finance");
  await page.keyboard.press("Enter");
  await expect(node(page, "Finance")).toBeVisible();
  await body(page, "Finance").dblclick();
  await editor(page).fill("Treasury");
  await page.keyboard.press("Enter");
  await expect(node(page, "Treasury")).toBeVisible();
  await body(page, "Treasury").click();
  await page.keyboard.press("Delete");
  await confirmDelete(page).click();
  await expect(node(page, "Treasury")).toHaveCount(0);
  await expect(undo(page)).toBeEnabled();

  await undo(page).click(); // the delete: back with the same name and type
  await expect(node(page, "Treasury")).toBeVisible();
  await expect(node(page, "Treasury")).toHaveAttribute("aria-label", "Treasury (Unit)");
  await canvas(page).locator(`g[data-element-id="${api.state.nodes.at(-1)!.id}"]`).focus();
  await page.keyboard.press("Control+z"); // the rename
  await expect(node(page, "Finance")).toBeVisible();
  await canvas(page).locator(`g[data-element-id="${api.state.nodes.at(-1)!.id}"]`).focus();
  await page.keyboard.press("Control+z"); // the creation
  await expect(node(page, "Finance")).toHaveCount(0);
  await expect(undo(page)).toBeDisabled();
  await expect(redo(page)).toBeEnabled();
  await redo(page).click();
  await expect(node(page, "Finance")).toBeVisible();
  await expect(node(page, "Finance")).toHaveAttribute("aria-label", "Finance (Unit)");
  await node(page, "Finance").focus();
  await page.keyboard.press("Control+Shift+z");
  await expect(node(page, "Treasury")).toBeVisible();
  // The shortcuts are left alone in a text field.
  const search = page.getByRole("searchbox", { name: "Search nodes" });
  await search.focus();
  await search.fill("abc");
  const writes = api.state.writes.length;
  await page.keyboard.press("Control+z");
  await page.waitForTimeout(300);
  expect(api.state.writes.length).toBe(writes);
  await expect(node(page, "Treasury")).toBeVisible();
});

test("a node recreated by an undo keeps its connection, and undoing an older step still finds it", async ({ page }) => {
  const api = await open(page);
  await connectByClicks(page, "Sales", "Lead");
  await expect(connections(page)).toHaveCount(1);
  await body(page, "Sales").dblclick();
  await editor(page).fill("Revenue");
  await page.keyboard.press("Enter");
  await expect(node(page, "Revenue")).toBeVisible();
  await body(page, "Revenue").click();
  await page.keyboard.press("Delete");
  await confirmDelete(page).click();
  await expect(connections(page)).toHaveCount(0);
  await undo(page).click();
  await expect(node(page, "Revenue")).toBeVisible();
  await expect(connections(page)).toHaveCount(1);
  await undo(page).click(); // the rename of the node that now has another id
  await expect(node(page, "Sales")).toBeVisible();
  await undo(page).click(); // the connection
  await expect(connections(page)).toHaveCount(0);
  expect(api.state.connections).toHaveLength(0);
});

test("a stale edit is reverted with the existing notice and the same edit then goes through", async ({ page }) => {
  const api = await open(page);
  api.state.refuseNext = "stale";
  await connectByClicks(page, "Sales", "Lead");
  await expect(alert(page)).toContainText("Someone changed this just now. The model was reloaded.");
  await expect(connections(page)).toHaveCount(0);
  await expect(undo(page)).toBeDisabled();
  await connectByClicks(page, "Sales", "Lead");
  await expect(connections(page)).toHaveCount(1);
});

test("an undo is refused with a readable notice when another session changed the element, and the history stays usable", async ({ page }) => {
  const api = await open(page);
  await body(page, "Support").dblclick();
  await editor(page).fill("Help");
  await page.keyboard.press("Enter");
  await expect(node(page, "Help")).toBeVisible();
  await body(page, "Sales").dblclick();
  await editor(page).fill("Revenue");
  await page.keyboard.press("Enter");
  await expect(node(page, "Revenue")).toBeVisible();
  // A second session renames Sales behind our back.
  api.state.nodes.find((item) => item.id === "n1")!.name = "Theirs";
  api.state.version++;
  const writes = api.state.writes.length;
  await undo(page).click();
  await expect(alert(page)).toContainText("Someone changed this since, so the step could not be undone. It was removed from your history.");
  expect(api.state.writes.length).toBe(writes);
  await expect(node(page, "Theirs")).toBeVisible();
  // The older step is still there and still works (with the version read afresh).
  await undo(page).click();
  await expect(node(page, "Support")).toBeVisible();
  await expect(undo(page)).toBeDisabled();
});

test("an undo the server refuses (stale or chain broken) drops the step and explains", async ({ page }) => {
  const api = await open(page);
  await body(page, "Sales").dblclick();
  await editor(page).fill("Revenue");
  await page.keyboard.press("Enter");
  await expect(node(page, "Revenue")).toBeVisible();
  api.state.refuseNext = "chain";
  await undo(page).click();
  await expect(alert(page)).toContainText("would break a later event or scenario");
  await expect(undo(page)).toBeDisabled();
  await expect(node(page, "Revenue")).toBeVisible();
});

test("a connection can be re-routed from the details panel and the move is undone", async ({ page }) => {
  const api = await open(page);
  api.state.connections.push({ id: "k1", connection_type_id: "c1", source_node_id: "n1", target_node_id: "n2" });
  await page.reload();
  await expect(connections(page)).toHaveCount(1);
  await canvas(page).locator(".djs-connection .djs-hit").first().click({ force: true });
  await page.getByLabel("To", { exact: true }).selectOption({ label: "Lead" });
  await page.getByRole("button", { name: "Move connection" }).click();
  await expect.poll(() => api.state.connections[0].target_node_id).toBe("n3");
  await undo(page).click();
  await expect.poll(() => api.state.connections[0].target_node_id).toBe("n2");
});

test("a read-only subscription has no undo, redo, connect, pad or add controls, and Delete does nothing", async ({ page }) => {
  const api = await open(page, false);
  await expect(undo(page)).toHaveCount(0);
  await expect(redo(page)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Connect nodes/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add a Unit node" })).toHaveCount(0);
  await body(page, "Sales").click();
  await expect(page.getByRole("button", { name: "Connect to another node" })).toHaveCount(0);
  await page.keyboard.press("Delete");
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await body(page, "Sales").dblclick();
  await expect(page.getByRole("textbox", { name: "Node name" }).filter({ visible: true })).toHaveCount(1); // the details field, disabled
  await expect(page.getByRole("button", { name: "Select several nodes (drag a rectangle)" })).toBeVisible();
  expect(api.state.writes).toEqual([]);
});

test("the drawing controls have no automatically detectable accessibility violations", async ({ page }) => {
  await open(page);
  await body(page, "Sales").click();
  await expect(page.getByRole("button", { name: "Connect to another node" })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.map((item) => `${item.id}: ${item.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});
