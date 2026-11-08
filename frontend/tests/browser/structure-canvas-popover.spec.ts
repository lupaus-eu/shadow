import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Hover and focus popovers, shortened labels and the metrics of a selected node on the Structure canvas, against a mocked API (no sign-in).
const ORG = "00000000-0000-4000-8000-000000000001";
const MODEL = "00000000-0000-4000-8000-000000000002";
const LINE = "00000000-0000-4000-8000-000000000003";
const EVENT = "00000000-0000-4000-8000-000000000004";

const LONG = "abcdefghij".repeat(8); // 80 characters
type Node = { id: string; node_type_id: string; name: string; description: string | null; x: number; y: number };
const types = [{ id: "t1", key: "unit", name: "Unit", color: "#cfe3ff", shape: "rectangle", version: 1 }];
const connectionTypes = [
  { id: "c1", key: "reports", name: "Reports to", style: "solid", source_end: "none", target_end: "arrow", version: 1 },
  { id: "c2", key: "supports", name: "Supports", style: "dashed", source_end: "none", target_end: "arrow", version: 1 },
];
const allowed = [{ connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t1" }];
const metric = (id: string, name: string, unit: string | null, node_id: string | null, values: number) => ({ id, key: id, name, unit, node_id, formula: null, derived: false, version: 1, values });
const metrics = [metric("m1", "Revenue", "EUR", "n1", 3), metric("m2", "Headcount", null, "n1", 0), metric("m3", "Elsewhere", "kg", "n2", 1)];
const series: Record<string, { period: string; value: number | null }[]> = {
  m1: [{ period: "2026-01-01", value: 100 }, { period: "2026-03-01", value: 1234.5 }, { period: "2026-02-01", value: 200 }],
  m2: [],
  m3: [{ period: "2026-01-01", value: 5 }],
};

function createApi(options: { locale?: string } = {}) {
  const state = {
    nodes: [
      { id: "n1", node_type_id: "t1", name: "Sales", description: "Sells the products to customers.", x: 40, y: 200 },
      { id: "n2", node_type_id: "t1", name: "Support", description: null, x: 360, y: 40 },
      { id: "n3", node_type_id: "t1", name: LONG, description: "A node with a very long name.", x: 360, y: 360 },
      { id: "n4", node_type_id: "t1", name: "Far right", description: "Near the right edge of the drawing.", x: 1400, y: 200 },
    ] as Node[],
    connections: [
      { id: "k1", connection_type_id: "c1", source_node_id: "n1", target_node_id: "n2" },
      { id: "k2", connection_type_id: "c2", source_node_id: "n2", target_node_id: "n1" },
    ],
    metricLists: 0,
    seriesReads: [] as string[],
    failMetrics: false,
  };
  const event = () => ({ id: EVENT, line_id: LINE, occurred_on: "2026-01-01", title: "Start", version: 1, planned: false, change_count: 1 });
  async function mock(page: Page) {
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname.replace("/api/v1", "");
      const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
      if (path === "/auth/session") return json({ user_account: { id: "u1", account_class: "customer", email: "a@example.test", display_name: "Test Person", locale: options.locale ?? "en" } });
      if (path === "/system/status") return json({ database: "ready", schema_revision: "test" });
      if (path === "/organizations") return json({ organizations: [{ id: ORG, name: "Test Org", role: "owner" }] });
      if (path.endsWith("/unread-count")) return json({ unread: 0 });
      if (path === `/organizations/${ORG}`) return json({ organization: { id: ORG, name: "Test Org", time_zone: "UTC" }, membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null } });
      const model = `/organizations/${ORG}/models/${MODEL}`;
      if (path === `/organizations/${ORG}/models`) return json([{ id: MODEL, name: "Test model", description: null, version: 1, nodes: state.nodes.length }]);
      if (path === `${model}`) return json({ id: MODEL, name: "Test model", description: null, version: 1, nodes: state.nodes.length });
      if (path === `${model}/lines`) return json([{ id: LINE, name: "Base line", description: null, kind: "base", parent_line_id: null, branch_event_id: null, version: 1, event_count: 1, latest_event_date: "2026-01-01" }]);
      if (path === `${model}/lines/${LINE}/events`) return json([event()]);
      if (path === `${model}/lines/${LINE}/state`) return json({ event: event(), node_types: types, connection_types: connectionTypes, allowed_connections: allowed, nodes: state.nodes, connections: state.connections });
      if (path === `${model}/lines/${LINE}/metrics`) {
        state.metricLists++;
        if (state.failMetrics) return json({ detail: "boom" }, 500);
        return json(metrics);
      }
      const read = new RegExp(`${model}/lines/${LINE}/metrics/([^/]+)/series$`).exec(path);
      if (read) { state.seriesReads.push(read[1]); return json({ metric: metrics.find((item) => item.id === read[1]), points: series[read[1]] ?? [] }); }
      return json([]);
    });
  }
  return { state, mock };
}

const canvas = (page: Page) => page.getByRole("group", { name: "Model canvas" });
const node = (page: Page, name: string) => canvas(page).locator(`g.djs-element.djs-shape[aria-label^="${name} ("]`);
const body = (page: Page, name: string) => node(page, name).locator(".shadow-node-body");
const popover = (page: Page) => page.locator(".shadow-popover");
const details = (page: Page) => page.getByRole("complementary", { name: "Details" });

async function open(page: Page, options: { locale?: string } = {}) {
  const api = createApi(options);
  await api.mock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/organizations/${ORG}/models/${MODEL}`);
  // The group's own name is translated, the nodes' names are data.
  await expect(page.locator('g.djs-element.djs-shape[aria-label^="Sales ("]')).toBeVisible();
  return api;
}
async function away(page: Page) {
  const box = (await canvas(page).boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height - 10);
}

test("hovering a node shows its name, type and description, and leaving hides them", async ({ page }) => {
  await open(page);
  await body(page, "Sales").hover();
  await expect(popover(page)).toBeVisible();
  await expect(popover(page).locator(".shadow-popover-name")).toHaveText("Sales");
  await expect(popover(page).locator(".shadow-popover-type")).toHaveText("Unit");
  await expect(popover(page).locator(".shadow-popover-description")).toHaveText("Sells the products to customers.");
  await expect(popover(page)).toHaveAttribute("role", "tooltip");
  await away(page);
  await expect(popover(page)).toHaveCount(0);
});

test("the popover stays inside the canvas, also for a node at its edge", async ({ page }) => {
  await open(page);
  for (const name of ["Far right", "Sales", LONG]) {
    await body(page, name).hover();
    await expect(popover(page)).toBeVisible();
    const box = (await popover(page).boundingBox())!;
    const area = (await canvas(page).boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(area.x);
    expect(box.y).toBeGreaterThanOrEqual(area.y);
    expect(box.x + box.width).toBeLessThanOrEqual(area.x + area.width);
    expect(box.y + box.height).toBeLessThanOrEqual(area.y + area.height);
    await away(page);
    await expect(popover(page)).toHaveCount(0);
  }
});

test("the popover is dropped when the drawing is panned", async ({ page }) => {
  await open(page);
  await body(page, "Sales").hover();
  await expect(popover(page)).toBeVisible();
  const area = (await canvas(page).boundingBox())!;
  const x = area.x + area.width - 80;
  const y = area.y + area.height - 60;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x - 40, y - 20, { steps: 4 });
  await page.mouse.up();
  await expect(popover(page)).toHaveCount(0);
});

test("a node with keyboard focus shows its popover, which Esc dismisses and moving focus away removes", async ({ page }) => {
  await open(page);
  await node(page, "Support").focus();
  await expect(popover(page)).toBeVisible();
  await expect(popover(page).locator(".shadow-popover-name")).toHaveText("Support");
  const id = await popover(page).getAttribute("id");
  await expect(node(page, "Support")).toHaveAttribute("aria-describedby", id!);
  await page.keyboard.press("Escape");
  await expect(popover(page)).toHaveCount(0);
  await node(page, "Support").blur();
  await node(page, "Sales").focus();
  await expect(popover(page).locator(".shadow-popover-name")).toHaveText("Sales");
  await page.keyboard.press("Tab");
  await expect(popover(page).locator(".shadow-popover-name")).not.toHaveText("Sales");
});

test("a node being named gets no popover", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Add a Unit node" }).click();
  await expect(canvas(page).getByRole("textbox", { name: "Node name" })).toBeVisible();
  await body(page, "Support").hover();
  await page.waitForTimeout(500);
  await expect(popover(page)).toHaveCount(0);
});

test("the popover does not animate when reduced motion is asked for", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page);
  await node(page, "Sales").focus();
  await expect(popover(page)).toBeVisible();
  expect(await popover(page).evaluate((element) => getComputedStyle(element).animationName)).toBe("none");
});

test("an 80 character name is shortened to 59 characters and an ellipsis on the canvas and in the list, and shown whole in the popover and details", async ({ page }) => {
  await open(page);
  const shortened = `${LONG.slice(0, 59)}…`;
  const labelled = node(page, LONG);
  await expect(labelled).toBeVisible();
  const lines = await labelled.locator(".shadow-node-name").allTextContents();
  expect(lines.join("")).toBe(shortened);
  expect(Array.from(lines.join(""))).toHaveLength(60);
  const list = page.getByRole("complementary", { name: "Nodes" });
  await expect(list.getByRole("button", { name: shortened })).toBeVisible();
  await body(page, LONG).hover();
  await expect(popover(page).locator(".shadow-popover-name")).toHaveText(LONG);
  await body(page, LONG).click();
  await expect(details(page).getByRole("textbox", { name: "Node name" })).toHaveValue(LONG);
});

test("connections between the same two nodes are drawn apart", async ({ page }) => {
  await open(page);
  const lines = canvas(page).locator(".shadow-connection-line");
  await expect(lines).toHaveCount(2);
  const points = await lines.evaluateAll((all) => all.map((line) => (line.getAttribute("points") ?? "").split(" ").map((pair) => pair.split(",").map(Number))));
  const [a, b] = points;
  // Same two nodes, so the lines are parallel, but not on top of each other.
  const slope = (line: number[][]) => (line[1][1] - line[0][1]) / (line[1][0] - line[0][0]);
  expect(slope(a)).toBeCloseTo(slope(b), 1);
  const gap = Math.abs((a[0][1] - b[0][1]) - slope(a) * (a[0][0] - b[0][0]));
  expect(gap).toBeGreaterThan(10);
});

test("the details of a node list its metrics with the latest value and unit, read only when a node is selected, and link to the Metrics tab", async ({ page }) => {
  const api = await open(page);
  expect(api.state.metricLists).toBe(0);
  await body(page, "Sales").click();
  const items = details(page).getByTestId("node-metric");
  await expect(items).toHaveCount(2);
  await expect(items.filter({ hasText: "Revenue" })).toContainText("1,234.5 EUR");
  await expect(items.filter({ hasText: "Revenue" })).toContainText("2026-03");
  await expect(items.filter({ hasText: "Headcount" })).toContainText("No values yet");
  expect(api.state.metricLists).toBe(1);
  expect([...api.state.seriesReads].sort()).toEqual(["m1", "m2"]);
  // Another node and back: cached.
  await body(page, "Support").click();
  await expect(details(page).getByTestId("node-metric")).toHaveCount(1);
  await body(page, "Sales").click();
  await expect(items).toHaveCount(2);
  expect(api.state.metricLists).toBe(1);
  expect(api.state.seriesReads.filter((id) => id === "m1")).toHaveLength(1);
  const link = details(page).getByRole("link", { name: "Open the Metrics tab" });
  await expect(link).toHaveAttribute("href", `/organizations/${ORG}/models/${MODEL}/metrics?line=${LINE}`);
  const results = await new AxeBuilder({ page }).include('aside[aria-label="Details"]').analyze();
  expect(results.violations).toEqual([]);
  await link.click();
  await expect(page).toHaveURL(new RegExp(`/models/${MODEL}/metrics\\?line=${LINE}$`));
  await expect(page.getByRole("heading", { name: "Metrics", level: 2 })).toBeVisible();
});

test("a node without metrics says so", async ({ page }) => {
  await open(page);
  await body(page, "Far right").click();
  await expect(details(page).getByText("No metrics are attached to this node.")).toBeVisible();
  await expect(details(page).getByTestId("node-metric")).toHaveCount(0);
  await expect(details(page).getByRole("link", { name: "Open the Metrics tab" })).toBeVisible();
});

test("a failed metrics read shows a readable message and Try again reads it again", async ({ page }) => {
  const api = await open(page);
  api.state.failMetrics = true;
  await body(page, "Sales").click();
  await expect(details(page).getByRole("alert")).toHaveText("The metrics could not be loaded.");
  api.state.failMetrics = false;
  await details(page).getByRole("button", { name: "Try again" }).click();
  await expect(details(page).getByTestId("node-metric")).toHaveCount(2);
});

test("the metrics texts come in Finnish", async ({ page }) => {
  await open(page, { locale: "fi" });
  await page.locator('g.djs-element.djs-shape[aria-label^="Far right ("] .shadow-node-body').click();
  const panel = page.getByRole("complementary", { name: "Tiedot" });
  await expect(panel.getByRole("heading", { name: "Mittarit" })).toBeVisible();
  await expect(panel.getByText("Tähän nodeen ei ole liitetty mittareita.")).toBeVisible();
  await expect(panel.getByRole("link", { name: "Avaa Mittarit-välilehti" })).toBeVisible();
});
