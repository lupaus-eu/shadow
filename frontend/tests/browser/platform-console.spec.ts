import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext } from "@playwright/test";

const apiBase = "http://api.yearclock.test";
const job = { kind: "job", id: "9b1f2a9e-0c3d-4b5a-9e8f-1a2b3c4d5e6f", type: "content.purge", organization_id: "3ea19a50-62af-446f-a608-c2c3c99cbb92", status: "failed", attempts: 5, next_attempt_at: null, last_error: "RuntimeError: storage unavailable", created_at: "2026-09-22T08:00:00Z" };

async function consoleApi(context: BrowserContext, roles: string[]) {
  const calls: string[] = [];
  await context.route(`${apiBase}/api/v1/platform/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1/platform", "");
    calls.push(`${request.method()} ${path}`);
    if (path === "/session") return route.fulfill({ status: 200, json: { id: "p1", email: "ops@example.com", display_name: "Olli Operator", locale: "en", roles } });
    if (path === "/health") return route.fulfill({ status: 200, json: { database: "ready", email: { pending: 0, processing: 0, completed: 12, failed: 1 }, jobs: { "content.purge": { pending: 0, processing: 0, completed: 3, failed: 1 } }, webhooks: { activated: 2 }, organizations: { active: 2 } } });
    if (path === "/organizations") return route.fulfill({ status: 200, json: [{ id: job.organization_id, name: "Northwind", status: "active", subscription: { state: "grace", writable: true, grace_expires_at: "2026-09-30T00:00:00Z", cancel_at_period_end: true, current_period_end: null }, purchased_seats: 3, members: 2, yearclocks: 1, activated_at: "2026-07-30T09:00:00Z", deletion_requested_at: null, mcp_enabled: true, mcp_platform_blocked: false }] });
    if (path === "/jobs") return route.fulfill({ status: 200, json: calls.some((call) => call.startsWith("POST")) ? [] : [job] });
    if (path.endsWith("/mcp-block")) return route.fulfill({ status: 200, json: { id: job.organization_id, name: "Northwind", status: "active", subscription: { state: "grace", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, purchased_seats: 3, members: 2, yearclocks: 1, activated_at: null, deletion_requested_at: null, mcp_enabled: true, mcp_platform_blocked: request.postDataJSON().blocked } });
    if (path.endsWith("/replay")) return route.fulfill({ status: 200, json: { ...job, status: "pending", attempts: 0 } });
    return route.fulfill({ status: 404, json: {} });
  });
  return calls;
}

test("anonymous visitors see the platform sign-in", async ({ context, page }) => {
  await context.route(`${apiBase}/api/v1/platform/session`, (route) => route.fulfill({ status: 401, json: {} }));
  await page.goto("/platform");
  await expect(page.getByRole("heading", { name: "Sign in to the operator console" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Continue with Authentik" })).toHaveAttribute("href", `${apiBase}/api/v1/auth/login?audience=platform&return_to=%2Fplatform`);
});

test("customer accounts are turned away from the console", async ({ context, page }) => {
  await context.route(`${apiBase}/api/v1/platform/session`, (route) => route.fulfill({ status: 403, json: { detail: "platform account required" } }));
  await page.goto("/platform");
  await expect(page.getByRole("alert")).toHaveText(/signed in with a customer account/);
});

test("a Platform Admin sees health, Organizations, and replays a failed job", async ({ context, page }) => {
  const calls = await consoleApi(context, ["platform_admin"]);
  await page.goto("/platform");
  await expect(page.getByRole("heading", { name: "Operator console" })).toBeVisible();
  await expect(page.getByText("Olli Operator · Platform Admin")).toBeVisible();
  await expect(page.getByText("completed 12, failed 1")).toBeVisible();
  await expect(page.getByText("Platform", { exact: true }).first()).toBeVisible();
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Organizations" }).click();
  await expect(page).toHaveURL("/platform/organizations");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organizations");
  const row = page.getByRole("row", { name: /Northwind/ });
  await expect(row).toContainText("grace · cancellation scheduled");
  await expect(row).toContainText("3");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Failed jobs" }).click();
  await expect(page.getByText("Last error: RuntimeError: storage unavailable")).toBeVisible();
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await page.getByRole("button", { name: "Replay: content.purge" }).click();
  await expect(page.getByText("Queued again.")).toBeVisible();
  await expect(page.getByText("No failed jobs.")).toBeVisible();
  expect(calls).toContain(`POST /jobs/job/${job.id}/replay`);
});

test("a Support Agent sees health and failed jobs but no Organization list or replay", async ({ context, page }) => {
  const calls = await consoleApi(context, ["support_agent"]);
  await page.goto("/platform");
  await expect(page.getByRole("heading", { name: "Service health" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link")).toHaveText(["Service health", "Failed jobs", "Support Access"]);
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Failed jobs" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Failed jobs");
  await expect(page.getByRole("button", { name: /Replay/ })).toHaveCount(0);
  await page.goto("/platform/organizations");
  await expect(page.getByRole("alert")).toHaveText("This page does not exist or your platform role cannot open it.");
  expect(calls).not.toContain("GET /organizations");
});

test("a platform account opening the customer application is pointed to the console", async ({ context, page }) => {
  await context.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 403, json: { detail: "customer account required" } }));
  await page.goto("/");
  await expect(page.getByRole("alert")).toHaveText(/platform account/);
  await expect(page.getByRole("link", { name: "Open the operator console" })).toHaveAttribute("href", "/platform");
});

test("a Platform Admin blocks agent access for an Organization", async ({ context, page }) => {
  const calls = await consoleApi(context, ["platform_admin"]);
  await page.goto("/platform/organizations");
  const row = page.getByRole("row", { name: /Northwind/ });
  await expect(row).toContainText("allowed");
  await row.getByRole("button", { name: "Block" }).click();
  expect(calls).toContain(`PATCH /organizations/${job.organization_id}/mcp-block`);
});
