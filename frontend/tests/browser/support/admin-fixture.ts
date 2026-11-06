import type { BrowserContext, Route } from "@playwright/test";

export const apiBase = "http://api.yearclock.test";
export const organizationId = "3ea19a50-62af-446f-a608-c2c3c99cbb92";
export const owner = { id: "6b1f2a9e-0c3d-4b5a-9e8f-1a2b3c4d5e6f", user_account_id: "fc4dbf31-2fd3-43cf-bc95-96642b93b9eb", email: "owner@example.com", display_name: "Olivia Owner", role: "owner", version: 1 };
export const mika = { id: "7c2e3b0f-1d4e-4c6b-8f9a-2b3c4d5e6f70", user_account_id: "0d9c8b7a-6f5e-4d3c-2b1a-0f9e8d7c6b5a", email: "mika@example.com", display_name: "Mika Member", role: "member", version: 1 };
export const sanna = { id: "8d3f4c10-2e5f-4d7c-9a0b-3c4d5e6f7081", user_account_id: "1e0d9c8b-7a6f-4e5d-3c2b-1a0f9e8d7c6b", email: "sanna@example.com", display_name: "Sanna Sales", role: "member", version: 1 };
export const budget = { id: "b0000000-0000-4000-8000-000000000001", name: "Budget", display_order: 0, version: 1, archived_at: null, deleted_at: null, purge_after: null, organization_access: "none", lanes: [{ id: "b1000000-0000-4000-8000-000000000001", name: "General", display_order: 0, version: 1 }] };

export type McpState = { interface_available: boolean; enabled: boolean; platform_blocked: boolean; server_url: string; client_id: string; secret_configured: boolean };
export type AdminState = { yearclocks: Array<typeof budget>; memberships: Array<typeof owner>; mcp: McpState; requests: Array<{ method: string; path: string; body: unknown }> };

/** An Owner's Organization page with Yearclock management, People, and Invitations stubbed; ``extra`` answers new routes first. */
export async function adminWorkspace(context: BrowserContext, { role = "owner", locale = "en", extra, subscription = {} }: { role?: "owner" | "admin" | "member"; locale?: "en" | "fi"; subscription?: Record<string, unknown>; extra?: (route: Route, path: string, state: AdminState) => Promise<boolean> | boolean } = {}): Promise<AdminState> {
  const state: AdminState = { yearclocks: [structuredClone(budget)], memberships: [owner, mika, sanna], mcp: { interface_available: true, enabled: true, platform_blocked: false, server_url: "https://yearclock.example.com/api/mcp", client_id: "yearclock-mcp", secret_configured: true }, requests: [] };
  await context.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 200, json: { user_account: { id: owner.user_account_id, account_class: "customer", email: owner.email, display_name: owner.display_name, locale } } }));
  await context.route(`${apiBase}/api/v1/system/status`, (route) => route.fulfill({ status: 200, json: { status: "ok", database: "ready", schema_revision: "0021" } }));
  await context.route(new RegExp(`${apiBase}/api/v1/organizations/${organizationId}(/.*)?(\\?.*)?$`), async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(`/api/v1/organizations/${organizationId}`, "");
    state.requests.push({ method: request.method(), path, body: request.postData() ? request.postDataJSON() : null });
    if (extra && (await extra(route, path, state))) return;
    if (path === "") return route.fulfill({ status: 200, json: { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null, ...subscription }, yearclocks: state.yearclocks.map((clock) => ({ ...clock, access_role: "editor" })), recent_yearclock_ids: [] } });
    if (path === "/mcp" && request.method() === "GET") return route.fulfill({ status: 200, json: { ...state.mcp } });
    if (path === "/mcp" && request.method() === "PATCH") { state.mcp = { ...state.mcp, enabled: request.postDataJSON().enabled }; return route.fulfill({ status: 200, json: { ...state.mcp } }); }
    if (path === "/mcp/secret") return route.fulfill({ status: 200, json: { client_secret: "shared-secret-for-tests" } });
    if (path === "/billing/seats") return route.fulfill({ status: 200, json: { purchased: 4, occupied: 3, reserved: 0, available: 1, version: 1, pending_change: null } });
    if (path === "/memberships") return route.fulfill({ status: 200, json: state.memberships });
    if (path === "/yearclocks" && request.method() === "GET") return route.fulfill({ status: 200, json: state.yearclocks });
    if (/^\/yearclocks\/[^/]+\/access$/.test(path) && request.method() === "GET") return route.fulfill({ status: 200, json: [] });
    if (/^\/yearclocks\/[^/]+\/group-access$/.test(path) && request.method() === "GET") return route.fulfill({ status: 200, json: [] });
    if (path === "/groups" && request.method() === "GET") return route.fulfill({ status: 200, json: [] });
    if (path === "/me/groups") return route.fulfill({ status: 200, json: [] });
    if (path === "/billing/contact" && request.method() === "GET") return route.fulfill({ status: 200, json: { billing_name: "Northwind", billing_email: "billing@example.com" } });
    if (path === "/notifications/unread-count") return route.fulfill({ status: 200, json: { unread: 0 } });
    if (path === "/notifications") return route.fulfill({ status: 200, json: { items: [], next_cursor: null } });
    if (path === "/audit-events") return route.fulfill({ status: 200, json: { items: [], next_offset: null } });
    return route.fulfill({ status: 200, json: [] });
  });
  return state;
}
