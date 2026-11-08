import type { Page } from "@playwright/test";

// A stateful mocked API for the Structure canvas specs that edit (checks `expected_version` like the real routes); no sign-in.
export const ORG = "00000000-0000-4000-8000-000000000001";
export const MODEL = "00000000-0000-4000-8000-000000000002";
export const LINE = "00000000-0000-4000-8000-000000000003";
export const CHANGE = "00000000-0000-4000-8000-000000000004";

export type Node = { id: string; node_type_id: string; name: string; description: string | null; x: number; y: number };
export type Connection = { id: string; connection_type_id: string; source_node_id: string; target_node_id: string };

export const types = [
  { id: "t1", key: "unit", name: "Unit", color: "#cfe3ff", shape: "rectangle", version: 1 },
  { id: "t2", key: "role", name: "Role", color: "#ffe2b8", shape: "ellipse", version: 1 },
];
export const connectionTypes = [
  { id: "c1", key: "reports", name: "Reports to", style: "dashed", source_end: "none", target_end: "arrow", version: 1 },
  { id: "c2", key: "supports", name: "Supports", style: "solid", source_end: "none", target_end: "arrow", version: 1 },
];
export const allowed = [
  { connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t1" },
  { connection_type_id: "c2", source_node_type_id: "t1", target_node_type_id: "t1" },
  { connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t2" },
];

export function createApi(writable = true) {
  const state = {
    version: 1,
    counter: 10,
    nodes: [
      { id: "n1", node_type_id: "t1", name: "Sales", description: null, x: 60, y: 60 },
      { id: "n2", node_type_id: "t1", name: "Support", description: null, x: 400, y: 60 },
      { id: "n3", node_type_id: "t2", name: "Lead", description: null, x: 60, y: 260 },
    ] as Node[],
    connections: [] as Connection[],
    positionWrites: [] as { node_id: string; x: number; y: number }[][],
    writes: [] as string[],
    bodies: [] as unknown[],
    refuseNext: false as false | "chain" | "stale",
  };
  const change = () => ({ id: CHANGE, line_id: LINE, occurred_on: "2026-01-01", title: "Start", version: state.version, planned: false, edit_count: 1 });
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
      if (path === `${model}/lines`) return json([{ id: LINE, name: "Base line", description: null, kind: "base", parent_line_id: null, branch_change_id: null, version: 1, change_count: 1, latest_change_date: "2026-01-01" }]);
      if (path === `${model}/lines/${LINE}/changes`) return json([change()]);
      if (path === `${model}/lines/${LINE}/state`) return json({ change: change(), node_types: types, connection_types: connectionTypes, allowed_connections: allowed, nodes: state.nodes, connections: state.connections });
      if (path === `${model}/lines/${LINE}/positions` && method === "PUT") {
        const body = request.postDataJSON() as { node_id: string; x: number; y: number }[];
        state.positionWrites.push(body);
        state.writes.push("positions");
        for (const move of body) Object.assign(state.nodes.find((node) => node.id === move.node_id)!, { x: move.x, y: move.y });
        return route.fulfill({ status: 204 });
      }
      const edit = new RegExp(`${model}/changes/${CHANGE}/(nodes|connections)(?:/([^/]+))?$`).exec(path);
      if (edit && ["POST", "PATCH", "DELETE"].includes(method)) {
        const body = method === "DELETE" ? null : (request.postDataJSON() as Record<string, unknown>);
        const sent = method === "DELETE" ? Number(url.searchParams.get("expected_version")) : (body!.expected_version as number | undefined);
        state.writes.push(`${method} ${edit[1]}${edit[2] ? `/${edit[2]}` : ""}`);
        state.bodies.push(body);
        if (state.refuseNext) {
          const stale = state.refuseNext === "stale";
          state.refuseNext = false;
          return stale ? json({ detail: { latest_version: state.version + 1 } }, 409) : json({ detail: { reason: "chain_broken", cause: "test" } }, 422);
        }
        if (sent !== undefined && sent !== state.version) return json({ detail: { latest_version: state.version } }, 409);
        state.version++;
        if (edit[1] === "nodes") {
          if (method === "POST") {
            const node: Node = { id: `n${++state.counter}`, node_type_id: body!.node_type_id as string, name: body!.name as string, description: (body!.description as string | null) ?? null, x: body!.x as number, y: body!.y as number };
            state.nodes.push(node);
            return json({ id: node.id, node, change: change() }, 201);
          }
          if (method === "PATCH") { Object.assign(state.nodes.find((node) => node.id === edit[2])!, { name: body!.name, description: body!.description ?? null }); return json({ id: edit[2], change: change() }); }
          state.nodes = state.nodes.filter((node) => node.id !== edit[2]);
          state.connections = state.connections.filter((item) => item.source_node_id !== edit[2] && item.target_node_id !== edit[2]);
          return route.fulfill({ status: 204 });
        }
        if (method === "POST") {
          const connection: Connection = { id: `cx${++state.counter}`, connection_type_id: body!.connection_type_id as string, source_node_id: body!.source_node_id as string, target_node_id: body!.target_node_id as string };
          state.connections.push(connection);
          return json({ id: connection.id, connection, change: change() }, 201);
        }
        if (method === "PATCH") { Object.assign(state.connections.find((item) => item.id === edit[2])!, { source_node_id: body!.source_node_id, target_node_id: body!.target_node_id }); return json({ id: edit[2], change: change() }); }
        state.connections = state.connections.filter((item) => item.id !== edit[2]);
        return route.fulfill({ status: 204 });
      }
      return json([]);
    });
  }
  return { state, mock };
}

