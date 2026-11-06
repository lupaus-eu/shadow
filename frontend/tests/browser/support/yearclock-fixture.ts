import type { BrowserContext } from "@playwright/test";

export const apiBase = "http://api.yearclock.test";
export const organizationId = "3ea19a50-62af-446f-a608-c2c3c99cbb92";
export const yearclockId = "205fb875-dae5-4cad-ad5f-1c05bc1c745b";
export const yearclockPath = `/organizations/${organizationId}/yearclocks/${yearclockId}`;
export const lanes = [
  { id: "aa466c3d-1dd5-4c3e-99f2-e2bde6011448", name: "Governance", display_order: 0, version: 1 },
  { id: "bb466c3d-1dd5-4c3e-99f2-e2bde6011448", name: "Finance", display_order: 1, version: 1 },
];
export const categories = [
  { id: "c1000000-0000-4000-8000-000000000001", name: "Board", color: "#336699", display_order: 0, version: 1 },
  { id: "c2000000-0000-4000-8000-000000000002", name: "Audit", color: "#aa5500", display_order: 1, version: 1 },
];

type Subscription = { state: "active" | "grace" | "read_only"; writable: boolean; grace_expires_at: string | null; cancel_at_period_end: boolean; current_period_end: string | null };

type EventRow = {
  id: string;
  lane_id: string;
  category_id: string | null;
  title: string;
  description: string | null;
  location: string | null;
  links: Array<{ title: string; url: string }>;
  starts_on: string;
  ends_on: string | null;
  version: number;
  occurrence_id?: string | null;
  series_id?: string | null;
  series_date?: string | null;
  exception?: boolean;
  skipped?: boolean;
};

let counter = 0;
const id = (prefix: string) => `${prefix}${String(++counter).padStart(7, "0")}-0000-4000-8000-000000000000`.slice(0, 36);

export function sampleEvents(): EventRow[] {
  counter = 0;
  const weekly: EventRow[] = Array.from({ length: 20 }, (_, index) => {
    const date = new Date(Date.UTC(2026, 0, 5 + index * 7)).toISOString().slice(0, 10);
    return { id: id("e"), lane_id: lanes[1].id, category_id: null, title: "Weekly finance check", description: null, location: null, links: [], starts_on: date, ends_on: null, version: 1, occurrence_id: id("o"), series_id: "s1000000-0000-4000-8000-000000000001", series_date: date, exception: false, skipped: false };
  });
  weekly[3] = { ...weekly[3], title: "Finance check (moved)", starts_on: "2026-01-28", exception: true };
  return [
    { id: id("e"), lane_id: lanes[0].id, category_id: categories[0].id, title: "Board meeting", description: "Agenda:\nBudget approval\nSee https://example.com/agenda", location: "Room 4", links: [{ title: "Board page", url: "https://example.com/board" }], starts_on: "2026-03-10", ends_on: null, version: 1 },
    { id: id("e"), lane_id: lanes[0].id, category_id: categories[1].id, title: "Audit period", description: null, location: null, links: [], starts_on: "2026-04-01", ends_on: "2026-05-15", version: 1 },
    { id: id("e"), lane_id: lanes[1].id, category_id: null, title: "Year-end close", description: null, location: null, links: [], starts_on: "2026-12-20", ends_on: "2027-01-10", version: 1 },
    ...weekly,
  ];
}

export async function plannerApi(
  context: BrowserContext,
  { role = "owner", accessRole = "editor", events = sampleEvents(), today, subscription = {}, locale = "en" }: { role?: "owner" | "admin" | "member"; accessRole?: "editor" | "viewer"; events?: EventRow[]; today?: string; subscription?: Partial<Subscription>; locale?: "en" | "fi" } = {},
) {
  if (today) {
    await context.addInitScript(`{
      const fixed = new Date("${today}T09:00:00Z").valueOf();
      const RealDate = Date;
      globalThis.Date = class extends RealDate { constructor(...args) { super(...(args.length ? args : [fixed])); } static now() { return fixed; } };
    }`);
  }
  const requests: Array<{ method: string; path: string; search: string; body: unknown }> = [];
  await context.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 200, json: { user_account: { id: "fc4dbf31-2fd3-43cf-bc95-96642b93b9eb", account_class: "customer", email: "owner@example.com", display_name: "Olivia Owner", locale } } }));
  await context.route(`${apiBase}/api/v1/system/status`, (route) => route.fulfill({ status: 200, json: { status: "ok", database: "ready", schema_revision: "0021" } }));
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null, ...subscription }, yearclocks: [{ id: yearclockId, name: "Northwind Yearclock", version: 1, access_role: accessRole, lanes }] } }));
  await context.route(new RegExp(`${apiBase}/api/v1/organizations/${organizationId}/(memberships|invitations|billing/seats|audit-events|support-access|labels|categories|notifications|yearclocks\\?).*`), (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/notifications/unread-count")) return route.fulfill({ status: 200, json: { unread: 0 } });
    if (path.endsWith("/notifications")) return route.fulfill({ status: 200, json: { items: [], next_cursor: null } });
    if (path.endsWith("/billing/seats")) return route.fulfill({ status: 200, json: { purchased: 2, occupied: 1, reserved: 0, available: 1, version: 1, pending_change: null } });
    if (path.endsWith("/audit-events")) return route.fulfill({ status: 200, json: { items: [], next_offset: null } });
    return route.fulfill({ status: 200, json: [] });
  });
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(`/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}`, "");
    if (path === "/visit") return route.fulfill({ status: 204 });
    requests.push({ method: request.method(), path, search: url.search, body: request.postData() ? request.postDataJSON() : null });
    if (path === "/categories" && request.method() === "GET") return route.fulfill({ status: 200, json: categories });
    if (path === "/deleted-events") return route.fulfill({ status: 200, json: [] });
    if (path === "/events" && request.method() === "GET") {
      const start = url.searchParams.get("window_start") ?? "2026-01-01";
      const [year, month] = start.split("-").map(Number);
      const endDate = new Date(Date.UTC(year, month - 1 + Number(url.searchParams.get("months") ?? 12), 0)).toISOString().slice(0, 10);
      return route.fulfill({ status: 200, json: events.filter((event) => event.starts_on <= endDate && (event.ends_on ?? event.starts_on) >= start && (url.searchParams.get("include_skipped") === "true" || !event.skipped)) });
    }
    if (request.method() === "POST" && path === "/events") return route.fulfill({ status: 201, json: { id: "e9999999-0000-4000-8000-000000000000", version: 1, ...request.postDataJSON() } });
    if (request.method() === "POST" && path === "/series") return route.fulfill({ status: 201, json: { id: "s9999999-0000-4000-8000-000000000000" } });
    return route.fulfill({ status: 200, json: {} });
  });
  return requests;
}
