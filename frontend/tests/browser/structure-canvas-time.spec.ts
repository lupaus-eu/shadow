import { expect, test, type Page } from "@playwright/test";

// Time control of the canvas against a mocked API (no sign-in): drawing goes into the shown change whichever it is, a chain_broken refusal
// is explained in words and reverted, what the shown change added, changed and removed is marked (removed ones as ghosts that cannot be
// edited), and a Member cannot draw on the Base line.
const ORG = "00000000-0000-4000-8000-000000000001";
const MODEL = "00000000-0000-4000-8000-000000000002";
const BASE = "00000000-0000-4000-8000-000000000003";
const E1 = "00000000-0000-4000-8000-0000000000e1";
const E2 = "00000000-0000-4000-8000-0000000000e2";

const types = [{ id: "t1", key: "unit", name: "Unit", color: "#cfe3ff", shape: "rectangle", version: 1 }];
const sales = { id: "n1", node_type_id: "t1", name: "Sales", description: null, x: 60, y: 60 };
const support = { id: "n2", node_type_id: "t1", name: "Support", description: null, x: 400, y: 60 };
const legacy = { id: "n3", node_type_id: "t1", name: "Legacy desk", description: null, x: 60, y: 260 };

function createApi(role: "owner" | "member" = "owner") {
  const changes = [
    { id: E1, line_id: BASE, occurred_on: "2026-01-01", title: "Initial situation", note: null, version: 3, planned: false, edit_count: 2, edit_counts: { add_node: 2 }, branches: [] },
    { id: E2, line_id: BASE, occurred_on: "2026-02-01", title: "Reorganisation", note: null, version: 1, planned: false, edit_count: 2, edit_counts: { add_node: 1, remove_node: 1 }, branches: [] },
  ];
  const state = { posts: [] as { change: string; body: Record<string, unknown> }[], refuse: false };
  async function mock(page: Page) {
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname.replace("/api/v1", "");
      const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
      if (path === "/auth/session") return json({ user_account: { id: "u1", account_class: "customer", email: "a@example.test", display_name: "Test Person", locale: "en" } });
      if (path === "/system/status") return json({ database: "ready", schema_revision: "test" });
      if (path === "/organizations") return json({ organizations: [{ id: ORG, name: "Test Org", role }] });
      if (path.endsWith("/unread-count")) return json({ unread: 0 });
      if (path === `/organizations/${ORG}`) return json({ organization: { id: ORG, name: "Test Org", time_zone: "UTC" }, membership: { role }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null } });
      const model = `/organizations/${ORG}/models/${MODEL}`;
      if (path === `/organizations/${ORG}/models`) return json([{ id: MODEL, name: "Test model", description: null, version: 1, nodes: 2 }]);
      if (path === `${model}/lines`) return json([{ id: BASE, name: "Base line", description: null, kind: "base", parent_line_id: null, branch_change_id: null, version: 1, change_count: 2, latest_change_date: "2026-02-01", start_changed_at: null, created_by_user_account_id: null }]);
      if (path === `${model}/lines/${BASE}/changes`) return json(changes);
      if (path === `${model}/lines/${BASE}/state`) {
        const id = url.searchParams.get("change_id") ?? E2;
        const change = changes.find((item) => item.id === id)!;
        if (id === E1) return json({ change, node_types: types, connection_types: [], allowed_connections: [], nodes: [sales, legacy], connections: [], added: { nodes: [{ node: sales }, { node: legacy }], connections: [] } });
        return json({ change, node_types: types, connection_types: [], allowed_connections: [], nodes: [sales, support], connections: [], added: { nodes: [{ node: support }], connections: [] }, updated: { nodes: [{ node: { ...sales, name: "Sales" }, previous: { ...sales, name: "Sales team" } }], connections: [] }, removed: { nodes: [{ node: legacy }], connections: [] } });
      }
      const post = new RegExp(`${model}/changes/(${E1}|${E2})/nodes$`).exec(path);
      if (post && request.method() === "POST") {
        state.posts.push({ change: post[1], body: request.postDataJSON() });
        if (state.refuse) {
          return json({ detail: { reason: "chain_broken", change: E2, line: BASE, position: 0, element: "n3", cause: "missing_element", hint: { code: "add_element_before", change_title: "Reorganisation", change_date: "2026-02-01", op: "remove_node", line_name: "Base line", line_kind: "base", scenario_name: null, in_other_line: false, element_kind: "node", element_name: "Legacy desk", type_name: null, source_name: null, target_name: null, branch_change_title: null, branch_change_date: null } } }, 422);
        }
        return json({ id: "n9", change: { ...changes[0], version: 4 }, node: { id: "n9", node_type_id: "t1", name: "Finance", description: null, x: 0, y: 0 } }, 201);
      }
      return json([]);
    });
  }
  return { mock, state };
}

const canvas = (page: Page) => page.getByRole("group", { name: "Model canvas" });
const node = (page: Page, name: string) => canvas(page).locator(`g.djs-element.djs-shape[aria-label^="${name} ("]`);

async function open(page: Page, role: "owner" | "member" = "owner", query = "") {
  const api = createApi(role);
  await api.mock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/organizations/${ORG}/models/${MODEL}${query}`);
  await expect(node(page, "Sales")).toBeVisible();
  return api;
}

async function drawFinance(page: Page) {
  await page.getByRole("button", { name: "Add a Unit node" }).click();
  await canvas(page).getByRole("textbox", { name: "Node name" }).fill("Finance");
  await page.keyboard.press("Enter");
}

test("drawing while an earlier change is shown sends the edit to that change with its own version", async ({ page }) => {
  const api = await open(page, "owner", `?change=${E1}`);
  await expect(page.getByTestId("canvas-caption")).toContainText("Initial situation");
  await drawFinance(page);
  await expect.poll(() => api.state.posts.length).toBe(1);
  expect(api.state.posts[0].change).toBe(E1);
  expect(api.state.posts[0].body).toMatchObject({ name: "Finance", expected_version: 3 });
});

test("a chain_broken refusal says which change and element and what to do first, and the drawn node goes away", async ({ page }) => {
  const api = await open(page, "owner", `?change=${E1}`);
  api.state.refuse = true;
  await drawFinance(page);
  const alert = page.getByRole("alert").filter({ hasText: "Reorganisation" });
  await expect(alert).toContainText("Legacy desk");
  await expect(alert).toContainText("Add it in an earlier change first");
  await expect(node(page, "Finance")).toHaveCount(0);
  await expect(node(page, "Sales")).toBeVisible();
});

test("marks what the shown change added, changed and removed; removed elements are outlines that cannot be selected", async ({ page }) => {
  await open(page);
  await expect(node(page, "Support").locator(".shadow-change-badge[data-change='added']")).toContainText("+");
  await expect(node(page, "Sales").locator(".shadow-change-badge[data-change='updated']")).toContainText("~");
  const ghost = canvas(page).locator("[data-ghost='node']");
  await expect(ghost).toHaveCount(1);
  await expect(ghost.locator(".shadow-change-badge[data-change='removed']")).toContainText("−");
  await expect(page.getByTestId("canvas-legend")).toContainText("1 removed");
  await expect(page.getByTestId("ghost-list")).toContainText("Legacy desk");
  // A ghost is not a diagram element: clicking where it is selects nothing and shows no editing controls.
  await ghost.dispatchEvent("click");
  await expect(page.getByText("Select a node to edit", { exact: false })).toBeVisible();
  await expect(canvas(page).locator("g.djs-element[aria-label^='Legacy desk']")).toHaveCount(0);
});

test("a Member cannot draw on the Base line", async ({ page }) => {
  await open(page, "member");
  await expect(page.getByRole("button", { name: "Add a Unit node" })).toHaveCount(0);
});
