import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { MODEL, ORG, createApi } from "./canvas-mock-api";

// The Structure canvas without a mouse, as text, with reduced motion and on a phone, against the stateful mocked API (no sign-in, Chromium
// only; a screen reader and a real touch device were not used).
const canvas = (page: Page) => page.getByRole("group", { name: "Model canvas" });
const node = (page: Page, name: string) => canvas(page).locator(`g.djs-element.djs-shape[aria-label^="${name} ("]`);
const live = (page: Page) => page.locator("[role=status][aria-live=polite].sr-only");
const focusedLabel = (page: Page) => page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? "");

async function open(page: Page, size = { width: 1440, height: 900 }) {
  const api = createApi();
  await api.mock(page);
  await page.setViewportSize(size);
  await page.goto(`/organizations/${ORG}/models/${MODEL}`);
  await expect(node(page, "Sales")).toBeVisible();
  return api;
}
/** Presses Tab until the node is focused (nodes are in the tab order of the page). */
async function tabTo(page: Page, name: string, key = "Tab") {
  for (let step = 0; step < 80; step++) {
    if ((await focusedLabel(page)).startsWith(`${name} (`)) return;
    await page.keyboard.press(key);
  }
  throw new Error(`${name} is not reachable by ${key}`);
}
const insideCanvas = (page: Page) => page.evaluate(() => !!document.activeElement?.closest("[aria-label='Model canvas']"));

test("keyboard only: Tab to a node, select, move, connect with C, delete with confirmation, undo; each step is announced", async ({ page }) => {
  const api = await open(page);
  await tabTo(page, "Sales");
  expect(await focusedLabel(page)).toBe("Sales (Unit)");
  await page.keyboard.press("Enter");
  await expect(live(page)).toContainText("Selected Sales, Unit.");

  // Arrows move the selected node: one positions write after the quiet time.
  const before = api.state.nodes.find((item) => item.id === "n1")!.x;
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => api.state.nodes.find((item) => item.id === "n1")!.x).toBeGreaterThan(before);

  // C starts connect mode; Enter on the first node, Tab to the second, Enter; a dialog asks which of the two allowed connections.
  await page.keyboard.press("c");
  await expect(live(page)).toContainText("Connect mode on");
  await page.keyboard.press("Enter");
  await expect(live(page)).toContainText("Connecting from Sales");
  await tabTo(page, "Support");
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await page.getByRole("button", { name: "Reports to", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(canvas(page).locator(".djs-connection")).toHaveCount(1);
  await expect.poll(() => api.state.connections.length).toBe(1);
  await expect.poll(() => insideCanvas(page)).toBe(true);

  // The connection can be selected from the node's list of connections (no pointer needed) and focus moves to its details.
  await tabTo(page, "Sales");
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "outgoing Reports to: Support", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(live(page)).toContainText("Selected the connection Reports to from Sales to Support.");
  await expect.poll(() => page.evaluate(() => document.activeElement?.id)).toBe("canvas-connection-title");

  // Delete a node with confirmation; focus comes back to the canvas.
  await tabTo(page, "Lead");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Delete");
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Delete", exact: true }).last().focus();
  await page.keyboard.press("Enter");
  await expect(node(page, "Lead")).toHaveCount(0);
  await expect.poll(() => insideCanvas(page)).toBe(true);

  // Undo brings it back, and says so.
  await page.keyboard.press("Control+z");
  await expect(node(page, "Lead")).toBeVisible();
  await expect(live(page)).toContainText(/Undone|Undid|undone/i);
});

test("a refused connection is announced and Esc leaves connect mode with a spoken message", async ({ page }) => {
  await open(page);
  await tabTo(page, "Sales");
  await page.keyboard.press("c");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter"); // the same node again: a node cannot connect to itself
  await expect(live(page)).toContainText("A node cannot be connected to itself.");
  await expect(page.getByRole("alert")).toContainText("A node cannot be connected to itself.");
  await page.keyboard.press("c");
  await page.keyboard.press("Escape");
  await expect(live(page)).toContainText("Connect mode off.");
});

test("the node list is the text alternative: every node with type, description and connections, and a row selects the node", async ({ page }) => {
  const api = await open(page);
  api.state.connections.push({ id: "k1", connection_type_id: "c1", source_node_id: "n1", target_node_id: "n2" });
  api.state.nodes[0].description = "Takes orders";
  await page.reload();
  const list = page.getByRole("complementary", { name: "Nodes" });
  const row = list.getByRole("button", { name: /^Sales/ });
  await expect(row).toContainText("Takes orders");
  await expect(row).toContainText("Type: Unit.");
  await expect(row).toContainText("outgoing Reports to: Support");
  await expect(list.getByRole("button", { name: /^Support/ })).toContainText("incoming Reports to: Sales");
  await expect(list.getByRole("button", { name: /^Lead/ })).toContainText("Type: Role.");
  await expect(canvas(page)).toHaveAttribute("aria-describedby", /.+/);
  await row.focus();
  await page.keyboard.press("Enter");
  await expect(node(page, "Sales")).toHaveClass(/selected/);
  await expect(live(page)).toContainText("Selected Sales, Unit.");
});

test("under reduced motion nothing on the canvas page transitions or animates", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page);
  await node(page, "Sales").hover();
  const styles = await page.evaluate(() => {
    const probe = (element: Element | null) => (element ? { transition: getComputedStyle(element).transitionDuration, animation: getComputedStyle(element).animationName } : null);
    return [probe(document.querySelector("[role=toolbar] button")), probe(document.querySelector("[role=toolbar]")), probe(document.querySelector(".shadow-canvas")), probe(document.querySelector("aside button"))];
  });
  for (const style of styles) expect(style).not.toBeNull();
  for (const style of styles) { expect(style!.transition.split(",").every((value) => parseFloat(value) === 0)).toBe(true); expect(style!.animation).toBe("none"); }
});

test("375 px: the panels are a bottom sheet, the toolbar wraps, a node is created from the sheet, nothing scrolls sideways", async ({ page }) => {
  const api = await open(page, { width: 375, height: 812 });
  await expect(page.getByRole("complementary")).toHaveCount(0);
  const toolbar = page.getByRole("toolbar", { name: "Canvas view" });
  const box = (await toolbar.boundingBox())!;
  const area = (await canvas(page).boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(area.x);
  expect(box.x + box.width).toBeLessThanOrEqual(area.x + area.width + 1);
  const handle = page.getByRole("button", { name: "Show panels" });
  await expect(handle).toHaveAttribute("aria-expanded", "false");
  await handle.click();
  await expect(page.getByRole("button", { name: "Hide panels" })).toHaveAttribute("aria-expanded", "true");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "Add a Unit node" }).click();
  // The sheet closes so the node being named is not covered by it.
  await expect(page.getByRole("button", { name: "Show panels" })).toBeVisible();
  const name = canvas(page).getByRole("textbox", { name: "Node name" });
  await expect(name).toBeVisible();
  const field = (await name.boundingBox())!;
  expect(field.y + field.height).toBeLessThanOrEqual(812 - 48);
  await name.fill("Finance");
  await page.keyboard.press("Enter");
  await expect(node(page, "Finance")).toBeVisible();
  await expect.poll(() => api.state.nodes.some((item) => item.name === "Finance")).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("the canvas page with a selected node and its connection list has no automatically detectable accessibility violations", async ({ page }) => {
  const api = await open(page);
  api.state.connections.push({ id: "k1", connection_type_id: "c1", source_node_id: "n1", target_node_id: "n2" });
  await page.reload();
  await expect(node(page, "Sales")).toBeVisible();
  await node(page, "Sales").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "outgoing Reports to: Support", exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
