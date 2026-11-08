import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// The line picker, the event list and the event editor of the model page against a stateful mocked API (no sign-in): Planned marks and
// the Now divider, choosing an event redraws that state read-only, a Scenario started from a past event appears under its parent,
// and a refused date change is explained in words from the structured hint while the form keeps what was typed.
const ORG = "00000000-0000-4000-8000-000000000001";
const MODEL = "00000000-0000-4000-8000-000000000002";
const BASE = "00000000-0000-4000-8000-000000000003";
const E1 = "00000000-0000-4000-8000-0000000000e1";
const E2 = "00000000-0000-4000-8000-0000000000e2";
const E3 = "00000000-0000-4000-8000-0000000000e3";
const SCENARIO = "00000000-0000-4000-8000-0000000000s1";

const types = [{ id: "t1", key: "unit", name: "Unit", color: "#cfe3ff", shape: "rectangle", version: 1 }];
const sales = { id: "n1", node_type_id: "t1", name: "Sales", description: null, x: 60, y: 60 };
const support = { id: "n2", node_type_id: "t1", name: "Support", description: null, x: 400, y: 60 };
const growth = { id: "n3", node_type_id: "t1", name: "Growth", description: null, x: 60, y: 260 };

function createApi() {
  const events = [
    { id: E1, line_id: BASE, occurred_on: "2026-01-01", title: "Initial situation", note: null, version: 1, planned: false, change_count: 1, change_counts: { add_node: 1 }, branches: [] as { line_id: string; name: string }[] },
    { id: E2, line_id: BASE, occurred_on: "2026-02-01", title: "Support team", note: null, version: 1, planned: false, change_count: 1, change_counts: { add_node: 1 }, branches: [] as { line_id: string; name: string }[] },
    { id: E3, line_id: BASE, occurred_on: "2099-01-01", title: "Expansion", note: "Next year", version: 1, planned: true, change_count: 1, change_counts: { add_node: 1 }, branches: [] as { line_id: string; name: string }[] },
  ];
  const nodesAfter: Record<string, typeof sales[]> = { [E1]: [sales], [E2]: [sales, support], [E3]: [sales, support, growth] };
  const lines = [{ id: BASE, name: "Base line", description: null, kind: "base", parent_line_id: null, branch_event_id: null, version: 1, event_count: 3, latest_event_date: "2099-01-01", start_changed_at: null, created_by_user_account_id: null }] as Record<string, unknown>[];
  const state = { patches: [] as unknown[], created: [] as unknown[] };
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
      if (path === `/organizations/${ORG}`) return json({ organization: { id: ORG, name: "Test Org", time_zone: "UTC" }, membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null } });
      const model = `/organizations/${ORG}/models/${MODEL}`;
      if (path === `/organizations/${ORG}/models`) return json([{ id: MODEL, name: "Test model", description: null, version: 1, nodes: 3 }]);
      if (path === `${model}/lines` && method === "GET") return json(lines);
      if (path === `${model}/lines` && method === "POST") {
        const body = request.postDataJSON() as { name: string; branch_event_id: string };
        state.created.push(body);
        const created = { id: SCENARIO, name: body.name, description: null, kind: "scenario", parent_line_id: BASE, branch_event_id: body.branch_event_id, version: 1, event_count: 0, latest_event_date: null, start_changed_at: null, created_by_user_account_id: "u1" };
        lines.push(created);
        events.find((event) => event.id === body.branch_event_id)!.branches.push({ line_id: SCENARIO, name: body.name });
        return json(created, 201);
      }
      if (path === `${model}/lines/${BASE}/events`) return json(events);
      if (path === `${model}/lines/${SCENARIO}/events`) return json([]);
      const stateMatch = new RegExp(`${model}/lines/(${BASE}|${SCENARIO})/state`).exec(path);
      if (stateMatch) {
        const id = url.searchParams.get("event_id") ?? E3;
        const event = events.find((item) => item.id === id) ?? null;
        return json({ event, node_types: types, connection_types: [], allowed_connections: [], nodes: nodesAfter[id] ?? [sales, support], connections: [] });
      }
      const eventMatch = new RegExp(`${model}/events/(${E1}|${E2}|${E3})$`).exec(path);
      if (eventMatch && method === "GET") {
        const event = events.find((item) => item.id === eventMatch[1])!;
        return json({ ...event, changes: [{ position: 0, op: "add_node", element_id: event.id === E2 ? "n2" : "n1", payload: { name: event.id === E2 ? "Support" : "Sales", node_type_id: "t1", x: 0, y: 0 } }] });
      }
      if (eventMatch && method === "PATCH") {
        const body = request.postDataJSON() as { occurred_on: string; title: string };
        state.patches.push(body);
        if (body.occurred_on < "2026-01-01") {
          return json({ detail: { reason: "chain_broken", event: E2, line: BASE, position: 0, element: "n2", cause: "missing_element", hint: { code: "add_element_before", event_title: "Support team", event_date: body.occurred_on, op: "add_node", line_name: "Base line", line_kind: "base", scenario_name: null, in_other_line: false, element_kind: "node", element_name: "Support", type_name: null, source_name: null, target_name: null, branch_event_title: null, branch_event_date: null } } }, 422);
        }
        const event = events.find((item) => item.id === eventMatch[1])!;
        Object.assign(event, body, { version: event.version + 1 });
        return json(event);
      }
      return json([]);
    });
  }
  return { mock, state };
}

const structure = `/organizations/${ORG}/models/${MODEL}`;
const canvas = (page: Page) => page.getByRole("group", { name: "Model canvas" });
const node = (page: Page, name: string) => canvas(page).locator(`g.djs-element.djs-shape[aria-label^="${name} ("]`);
const list = (page: Page) => page.getByRole("list", { name: "Events of Base line" });

async function open(page: Page) {
  const api = createApi();
  await api.mock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(structure);
  await expect(node(page, "Growth")).toBeVisible();
  // The list opens by itself only on a wide screen; here it is opened with its button.
  await page.getByRole("button", { name: /^Events \(3\)/ }).click();
  await expect(list(page)).toBeVisible();
  return api;
}

test("marks planned events with a label and a frame and puts the Now divider before the first of them", async ({ page }) => {
  await open(page);
  const items = list(page).getByRole("listitem");
  await expect(items).toHaveCount(4);
  await expect(items.nth(0)).toContainText("Initial situation");
  await expect(items.nth(2)).toHaveText("Now");
  await expect(items.nth(3)).toContainText("Expansion");
  await expect(items.nth(3)).toContainText("Planned");
  await expect(items.nth(3)).toHaveAttribute("data-planned", "true");
  await expect(items.nth(1)).toHaveAttribute("data-planned", "false");
  await expect(items.nth(1)).not.toContainText("Planned");
  await expect(page.getByText("This event is planned", { exact: false })).toBeVisible();
});

test("choosing an earlier event redraws that state and keeps the canvas read-only", async ({ page }) => {
  await open(page);
  await list(page).getByRole("button", { name: /^\d{4}-\d\d-\d\d Initial situation/ }).click();
  await expect(page).toHaveURL(new RegExp(`event=${E1}`));
  await expect(node(page, "Sales")).toBeVisible();
  await expect(node(page, "Support")).toHaveCount(0);
  await expect(page.getByText("It is read-only", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add node" })).toHaveCount(0);
  await page.getByRole("button", { name: "Show the latest event" }).click();
  await expect(node(page, "Growth")).toBeVisible();
  await expect(page).not.toHaveURL(/event=/);
});

test("starts a scenario from a past event and lists it under its parent with a Scenario label", async ({ page }) => {
  const api = await open(page);
  await list(page).getByRole("button", { name: /^\d{4}-\d\d-\d\d Initial situation/ }).click();
  await page.getByRole("button", { name: "New scenario from here" }).click();
  const dialog = page.getByRole("dialog", { name: "New scenario" });
  await expect(dialog).toContainText("Initial situation");
  await dialog.getByLabel("Scenario name").fill("Plan B");
  await dialog.getByRole("button", { name: "Create scenario" }).click();
  await expect(dialog).toBeHidden();
  expect(api.state.created).toEqual([{ name: "Plan B", branch_event_id: E1 }]);
  await expect(page).toHaveURL(new RegExp(`line=${SCENARIO}`));
  const picker = page.getByLabel("Line", { exact: true });
  await expect(picker.locator("option")).toHaveText(["Base line (Base line)", "  ↳ Plan B (Scenario)"]);
  await expect(page.locator("[data-line-kind=scenario]")).toContainText("Scenario");
});

test("a refused date change says which event and element in words and keeps the typed input", async ({ page }) => {
  const api = await open(page);
  await page.getByRole("button", { name: "Edit the event Support team" }).click();
  const dialog = page.getByRole("dialog", { name: "Event" });
  await expect(dialog.getByRole("list").getByRole("listitem")).toHaveText('Add the node "Support" (Unit)');
  await dialog.getByLabel("Change date").fill("2025-12-01");
  await dialog.getByLabel("Title").fill("Support team moved");
  await dialog.getByRole("button", { name: "Save" }).click();
  const alert = dialog.getByRole("alert");
  await expect(alert).toContainText('"Support team"');
  await expect(alert).toContainText('"Support"');
  await expect(alert).toContainText("Add it in an earlier event first");
  await expect(alert).not.toContainText("chain_broken");
  await expect(dialog.getByLabel("Change date")).toHaveValue("2025-12-01");
  await expect(dialog.getByLabel("Title")).toHaveValue("Support team moved");
  await dialog.getByLabel("Change date").fill("2026-02-15");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  expect(api.state.patches).toHaveLength(2);
  await expect(list(page)).toContainText("2026-02-15");
});

test("the line bar, event list and event dialog have no automatically detectable accessibility violations", async ({ page }) => {
  await open(page);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "Edit the event Support team" }).click();
  await expect(page.getByRole("dialog", { name: "Event" }).getByRole("list")).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
