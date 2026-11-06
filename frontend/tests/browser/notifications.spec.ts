import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { adminWorkspace, organizationId } from "./support/admin-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const yearclockId = "b0000000-0000-4000-8000-000000000001";
const items = [
  { id: "n1", type: "access_changed", params: { yearclock_id: yearclockId, yearclock_name: "Budget", from_role: "none", to_role: "editor" }, created_at: "2026-10-05T08:00:00Z", read_at: null },
  { id: "n2", type: "role_changed", params: { from_role: "member", to_role: "admin" }, created_at: "2026-10-04T08:00:00Z", read_at: "2026-10-04T09:00:00Z" },
  { id: "n3", type: "access_changed", params: { yearclock_id: yearclockId, yearclock_name: "Budget", from_role: "viewer", to_role: "none" }, created_at: "2026-10-03T08:00:00Z", read_at: null },
];

async function inbox(context: Parameters<typeof adminWorkspace>[0], locale: "en" | "fi" = "en") {
  const read = new Set<string>();
  const state = await adminWorkspace(context, {
    locale,
    extra: async (route, path) => {
      const method = route.request().method();
      if (path === "/notifications/unread-count") { await route.fulfill({ status: 200, json: { unread: items.filter((item) => !item.read_at && !read.has(item.id)).length } }); return true; }
      if (path === "/notifications" && method === "GET") {
        const unreadOnly = new URL(route.request().url()).searchParams.get("unread") === "true";
        const shown = items.map((item) => (read.has(item.id) ? { ...item, read_at: "2026-10-05T10:00:00Z" } : item)).filter((item) => !unreadOnly || !item.read_at);
        await route.fulfill({ status: 200, json: { items: shown, next_cursor: null } });
        return true;
      }
      if (path === "/notifications/read-all") { items.forEach((item) => read.add(item.id)); await route.fulfill({ status: 200, json: { updated: 2 } }); return true; }
      const single = /^\/notifications\/([^/]+)\/read$/.exec(path);
      if (single) { read.add(single[1]); await route.fulfill({ status: 204 }); return true; }
      return false;
    },
  });
  return state;
}

test("the bell shows the unread count and the inbox lists notifications in plain words", async ({ context, page }) => {
  await inbox(context);
  await page.goto(`/organizations/${organizationId}`);
  const bell = page.getByRole("link", { name: "Notifications, 2 unread" });
  await expect(bell).toBeVisible();
  await bell.click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Notifications");
  const list = page.getByRole("list", { name: "Notifications" });
  await expect(list.getByText("You can now edit Budget.")).toBeVisible();
  await expect(list.getByText("Your role in the Organization changed from Member to Administrator.")).toBeVisible();
  await expect(list.getByText("You no longer have access to Budget.")).toBeVisible();
  await expect(list.getByRole("link", { name: "Open" })).toHaveCount(1);
  expect(await axe(page)).toEqual([]);
});

test("marking one or all as read updates the list and the bell", async ({ context, page }) => {
  const state = await inbox(context);
  await page.goto(`/organizations/${organizationId}/notifications`);
  await page.getByRole("button", { name: "Mark as read" }).first().click();
  await expect(page.getByRole("link", { name: "Notifications, 1 unread" })).toBeVisible();
  expect(state.requests.some((request) => request.method === "POST" && request.path === "/notifications/n1/read")).toBe(true);
  await page.getByRole("button", { name: "Mark all as read" }).click();
  await expect(page.getByRole("link", { name: "Notifications", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mark as read" })).toHaveCount(0);
});

test("the unread filter asks the server and the inbox is in Finnish", async ({ context, page }) => {
  await inbox(context, "fi");
  await page.goto(`/organizations/${organizationId}/notifications`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ilmoitukset");
  await expect(page.getByText("Voit nyt muokata vuosikelloa Budget.")).toBeVisible();
  await page.getByLabel("Vain lukemattomat").check();
  await expect(page.getByText("Roolisi organisaatiossa muuttui: Jäsen → Ylläpitäjä.")).toHaveCount(0);
  await expect(page.getByText("Pääsysi")).toHaveCount(0);
});

test("notification settings list the kinds a person can switch, save them, and show Organization notices to managers", async ({ context, page }) => {
  let saved: unknown = null;
  const base = [
    { key: "access_changed", audience: "everyone", in_app: true, email: false },
    { key: "access_removed", audience: "everyone", in_app: true, email: true },
    { key: "support_access", audience: "managers", in_app: true, email: true },
  ];
  await adminWorkspace(context, {
    extra: async (route, path) => {
      if (path !== "/notification-settings") return false;
      if (route.request().method() === "PUT") { saved = route.request().postDataJSON(); await route.fulfill({ status: 200, json: { items: base.map((item) => (item.key === "access_changed" ? { ...item, email: true } : item)), summary: { frequency: "off", yearclock_ids: null } } }); return true; }
      await route.fulfill({ status: 200, json: { items: base, summary: { frequency: "off", yearclock_ids: null } } });
      return true;
    },
  });
  await page.goto(`/organizations/${organizationId}/notification-settings`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Notification settings");
  await expect(page.getByRole("group", { name: "Organization notices" })).toBeVisible();
  const row = page.getByRole("listitem").filter({ hasText: "Access to a Yearclock changed" });
  await expect(row.getByLabel("By email")).not.toBeChecked();
  expect(await axe(page)).toEqual([]);
  await row.getByLabel("By email").check();
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible();
  expect(saved).toEqual({ settings: { access_changed: { in_app: true, email: true }, access_removed: { in_app: true, email: true }, support_access: { in_app: true, email: true } }, summary: { frequency: "off", yearclock_ids: null } });
});

test("the settings page is in Finnish and the inbox links to it", async ({ context, page }) => {
  await adminWorkspace(context, { locale: "fi", extra: async (route, path) => { if (path !== "/notification-settings") return false; await route.fulfill({ status: 200, json: { items: [{ key: "role_changed", audience: "everyone", in_app: true, email: false }], summary: { frequency: "off", yearclock_ids: null } } }); return true; } });
  await page.goto(`/organizations/${organizationId}/notifications`);
  await page.getByRole("main").getByRole("link", { name: "Asetukset", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ilmoitusasetukset");
  await expect(page.getByText("Roolisi muuttui", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Sähköpostilla")).not.toBeChecked();
});

test("the Summary is off by default and can be set to weekly or daily for all or chosen Yearclocks", async ({ context, page }) => {
  let saved: { summary?: unknown } = {};
  await adminWorkspace(context, {
    extra: async (route, path) => {
      if (path !== "/notification-settings") return false;
      if (route.request().method() === "PUT") { saved = route.request().postDataJSON(); await route.fulfill({ status: 200, json: { items: [], summary: (saved as { summary: unknown }).summary } }); return true; }
      await route.fulfill({ status: 200, json: { items: [], summary: { frequency: "off", yearclock_ids: null } } });
      return true;
    },
  });
  await page.goto(`/organizations/${organizationId}/notification-settings`);
  const summary = page.getByRole("group", { name: "Summary of upcoming Events" });
  await expect(summary.getByLabel("Off")).toBeChecked();
  await expect(summary.getByLabel("All Yearclocks I can read")).toHaveCount(0);
  await summary.getByLabel("Weekly, on Mondays").check();
  await expect(summary.getByLabel("All Yearclocks I can read")).toBeChecked();
  expect(await axe(page)).toEqual([]);
  await summary.getByLabel("Only these Yearclocks").check();
  await summary.getByRole("list", { name: "Only these Yearclocks" }).getByLabel("Budget").uncheck();
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible();
  expect(saved.summary).toEqual({ frequency: "weekly", yearclock_ids: [] });
  await summary.getByLabel("Every day").check();
  await summary.getByRole("list", { name: "Only these Yearclocks" }).getByLabel("Budget").check();
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect.poll(() => saved.summary).toEqual({ frequency: "daily", yearclock_ids: ["b0000000-0000-4000-8000-000000000001"] });
});
