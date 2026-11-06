import { expect, test, type BrowserContext } from "@playwright/test";
import { answerConfirm } from "./support/confirm";

const apiBase = "http://api.yearclock.test";
const organizationId = "3ea19a50-62af-446f-a608-c2c3c99cbb92";

type Clock = { id: string; name: string; display_order: number; version: number; archived_at: string | null; deleted_at?: string | null; purge_after?: string | null; lanes: Array<{ id: string; name: string; display_order: number; version: number }> };

async function structureApi(context: BrowserContext) {
  const clocks: Clock[] = [
    { id: "205fb875-dae5-4cad-ad5f-1c05bc1c745b", name: "Northwind Yearclock", display_order: 0, version: 1, archived_at: null, lanes: [{ id: "aa466c3d-1dd5-4c3e-99f2-e2bde6011448", name: "General", display_order: 0, version: 1 }] },
  ];
  let sequence = 0;
  const nextId = () => `00000000-0000-4000-8000-${String(++sequence).padStart(12, "0")}`;
  const workspaceClocks = () => clocks.filter((clock) => !clock.archived_at && !clock.deleted_at).sort((a, b) => a.display_order - b.display_order).map((clock) => ({ id: clock.id, name: clock.name, version: clock.version, access_role: "editor", lanes: [...clock.lanes].sort((a, b) => a.display_order - b.display_order) }));
  await context.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 200, json: { user_account: { id: "fc4dbf31-2fd3-43cf-bc95-96642b93b9eb", account_class: "customer", email: "owner@example.com", display_name: "Olivia Owner", locale: "en" } } }));
  await context.route(`${apiBase}/api/v1/system/status`, (route) => route.fulfill({ status: 200, json: { status: "ok", database: "ready", schema_revision: "0021" } }));
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role: "admin" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: workspaceClocks() } }));
  for (const path of ["invitations", "memberships"]) {
    await context.route(`${apiBase}/api/v1/organizations/${organizationId}/${path}`, (route) => route.fulfill({ status: 200, json: [] }));
  }
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/*/events**`, (route) => route.fulfill({ status: 200, json: [] }));
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/*/deleted-events`, (route) => route.fulfill({ status: 200, json: [] }));
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/*/categories`, (route) => route.fulfill({ status: 200, json: [] }));
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/*/access`, (route) => route.fulfill({ status: 200, json: [] }));
  await context.route(new RegExp(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks(\\?.*|/.*)?$`), async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(`/api/v1/organizations/${organizationId}/yearclocks`, "");
    const body = request.postData() ? request.postDataJSON() : {};
    if (request.method() === "GET" && path === "") {
      await route.fulfill({ status: 200, json: [...clocks].sort((a, b) => a.display_order - b.display_order) });
      return;
    }
    if (request.method() === "POST" && path === "") {
      const clock: Clock = { id: nextId(), name: body.name, display_order: clocks.length, version: 1, archived_at: null, lanes: [{ id: nextId(), name: "General", display_order: 0, version: 1 }] };
      clocks.push(clock);
      await route.fulfill({ status: 201, json: clock });
      return;
    }
    if (request.method() === "PUT" && path === "/order") {
      body.ordered_ids.forEach((id: string, index: number) => {
        const clock = clocks.find((item) => item.id === id)!;
        expect(body.expected_versions[id]).toBe(clock.version);
        clock.display_order = index;
        clock.version += 1;
      });
      await route.fulfill({ status: 200, json: clocks });
      return;
    }
    const [, clockId, action, laneAction] = path.split("/");
    const clock = clocks.find((item) => item.id === clockId)!;
    if (request.method() === "DELETE" && !action) {
      expect(new URL(request.url()).searchParams.get("expected_version")).toBe(String(clock.version));
      clock.deleted_at = "2026-09-23T10:00:00Z";
      clock.purge_after = "2026-10-23T10:00:00Z";
      clock.version += 1;
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (action === "recover") {
      clock.deleted_at = null;
      clock.purge_after = null;
      clock.version += 1;
      await route.fulfill({ status: 200, json: clock });
      return;
    }
    if (action === "archive" || action === "restore") {
      expect(body.expected_version).toBe(clock.version);
      clock.archived_at = action === "archive" ? "2026-09-23T10:00:00Z" : null;
      clock.version += 1;
      await route.fulfill({ status: 200, json: clock });
      return;
    }
    if (action === "lanes" && laneAction === "order") {
      expect(body.expected_version).toBe(clock.version);
      clock.lanes = body.ordered_ids.map((id: string, index: number) => ({ ...clock.lanes.find((lane) => lane.id === id)!, display_order: index }));
      clock.version += 1;
      await route.fulfill({ status: 200, json: clock.lanes });
      return;
    }
    if (action === "lanes") {
      const lane = { id: nextId(), name: body.name, display_order: clock.lanes.length, version: 1 };
      clock.lanes.push(lane);
      await route.fulfill({ status: 201, json: lane });
      return;
    }
    await route.fulfill({ status: 404, json: {} });
  });
}

test("an Admin creates, orders, archives, and restores Yearclocks and orders Lanes", async ({ context, page }) => {
  await structureApi(context);
  await page.goto(`/organizations/${organizationId}/admin/yearclocks`);
  const management = page.getByRole("region", { name: "Yearclocks" });
  await management.getByLabel("New Yearclock").fill("Board cycle");
  await management.getByRole("button", { name: "Create" }).click();
  const board = management.getByRole("article", { name: "Board cycle" });
  await expect(board).toBeVisible();

  await management.getByRole("button", { name: "Up: Board cycle" }).click();
  await expect(management.getByRole("article").first()).toHaveAccessibleName("Board cycle");

  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Board cycle" }).click();
  await expect(page.getByRole("region", { name: "Board cycle" })).toBeVisible();
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Yearclock settings: Board cycle");
  const lanesSection = page.getByRole("region", { name: "Lanes" });
  await lanesSection.getByLabel("New Lane").fill("Finance");
  await lanesSection.getByRole("button", { name: "Add Lane" }).click();
  await expect(lanesSection.getByLabel("Name: Finance")).toHaveValue("Finance");
  await lanesSection.getByRole("button", { name: "Up: Finance" }).click();
  await expect(lanesSection.getByRole("listitem").first().getByRole("textbox")).toHaveValue("Finance");
  await page.getByRole("link", { name: "Back to Board cycle" }).click();
  await page.getByRole("link", { name: "Back to Northwind" }).click();
  await expect(page.getByRole("region", { name: "Open a Yearclock" }).getByRole("link", { name: "Board cycle" })).toBeVisible();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Yearclocks and access" }).click();

  await board.getByRole("button", { name: "Archive" }).click();
  await expect(board.getByText("Archived — hidden from normal navigation.")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Board cycle" })).toHaveCount(0);
  const restored = page.getByRole("region", { name: "Yearclocks" }).getByRole("article", { name: "Board cycle" });
  await restored.getByRole("button", { name: "Restore" }).click();
  await page.reload();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Board cycle" })).toBeVisible();
});

test("the empty Yearclock shell stays within a small screen", async ({ context, page }) => {
  await structureApi(context);
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto(`/organizations/${organizationId}`);
  await page.getByRole("main").getByRole("link", { name: "Northwind Yearclock" }).click();
  const shell = page.getByRole("group", { name: /Northwind Yearclock/ }).first();
  await expect(shell).toBeVisible();
  const box = (await shell.boundingBox())!;
  expect(box.width).toBeGreaterThan(100);
  expect(box.x + box.width).toBeLessThanOrEqual(360);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("an Admin deletes a Yearclock and recovers it within 30 days", async ({ context, page }) => {
  await structureApi(context);
  await page.goto(`/organizations/${organizationId}/admin/yearclocks`);
  const management = page.getByRole("region", { name: "Yearclocks" });
  let message = "";
  await management.getByRole("button", { name: "Delete: Northwind Yearclock" }).click();
  message = await answerConfirm(page);
  expect(message).toBe("Delete the Yearclock “Northwind Yearclock” with all its Events? You can recover it for 30 days.");
  const deleted = page.getByRole("region", { name: "Deleted Yearclocks" });
  await expect(deleted.getByText(/Northwind Yearclock — recoverable until 23 Oct 2026/)).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Northwind Yearclock" })).toHaveCount(0);
  await deleted.getByRole("button", { name: "Recover: Northwind Yearclock" }).click();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Northwind Yearclock" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Deleted Yearclocks" })).toHaveCount(0);
});
