import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { adminWorkspace, apiBase, organizationId } from "./support/admin-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const base = `${apiBase}/api/v1/data-transfer`;
const headers = { "Access-Control-Expose-Headers": "Content-Disposition, Retry-After" };

async function serve(context: BrowserContext, scope: unknown[], preview: () => { status: number; json: unknown }) {
  const saves: string[] = [];
  await context.route(`${base}/organizations`, (route) => route.fulfill({ status: 200, headers, json: { organizations: scope } }));
  await context.route(`${base}/export`, (route) => route.fulfill({ status: 200, contentType: "text/csv", headers: { ...headers, "Content-Disposition": 'attachment; filename="yearclock-data-2026-11-05.csv"' }, body: "type,id\n" }));
  await context.route(`${base}/import?*`, (route) => {
    const dryRun = new URL(route.request().url()).searchParams.get("dry_run");
    if (dryRun === "false") saves.push("save");
    const reply = preview();
    return route.fulfill({ status: dryRun === "false" && reply.status === 200 ? 200 : reply.status, headers, json: reply.json });
  });
  return saves;
}

const clean = { rows: 3, organizations: [{ id: organizationId, name: "Northwind", kinds: { event: { created: 1, updated: 2, unchanged: 5 }, lane: { created: 0, updated: 0, unchanged: 1 } }, overwrites_newer: 1 }], errors: [], saved: false };
const file = { name: "yearclock-data.csv", mimeType: "text/csv", buffer: Buffer.from("type,id\n") };

test("an Owner or Admin downloads the file, previews an import, and saves it", async ({ context, page }) => {
  await adminWorkspace(context, { role: "admin" });
  const saves = await serve(context, [{ id: organizationId, name: "Northwind", role: "admin" }], () => ({ status: 200, json: clean }));
  await page.goto("/data-transfer");
  await expect(page.getByRole("heading", { name: "Export and import data", level: 1 })).toBeVisible();
  await expect(page.getByText("Northwind")).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
  expect(download.suggestedFilename()).toBe("yearclock-data-2026-11-05.csv");
  await page.getByLabel("Choose a CSV file").setInputFiles(file);
  await expect(page.getByText("What the import would do")).toBeVisible();
  await expect(page.getByRole("row", { name: /Events\s+1\s+2\s+5/ })).toBeVisible();
  await expect(page.getByText("1 Event has been changed by someone after this file was made", { exact: false })).toBeVisible();
  expect(await axe(page)).toEqual([]);
  await page.getByRole("button", { name: "Save import" }).click();
  await expect(page.getByRole("status").filter({ hasText: "The import was saved." })).toBeVisible();
  expect(saves).toEqual(["save"]);
});

test("problems stop the save and name the row", async ({ context, page }) => {
  await adminWorkspace(context, { role: "owner" });
  const errors = [{ row: 7, type: "event", column: "lane_id", reason: "unknown_lane", value: "abc" }];
  await serve(context, [{ id: organizationId, name: "Northwind", role: "owner" }], () => ({ status: 200, json: { ...clean, errors } }));
  await page.goto("/data-transfer");
  await page.getByLabel("Choose a CSV file").setInputFiles(file);
  await expect(page.getByRole("alert").filter({ hasText: "1 problem found" })).toBeVisible();
  await expect(page.getByRole("row", { name: /7\s+Events\s+lane_id\s+The Lane was not found in this Yearclock: abc/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save import" })).toBeDisabled();
  expect(await axe(page)).toEqual([]);
});

test("a person who administers nothing sees no export or import, and the page speaks Finnish", async ({ context, page }) => {
  await adminWorkspace(context, { role: "member", locale: "fi" });
  await serve(context, [], () => ({ status: 200, json: clean }));
  await page.goto("/data-transfer");
  await expect(page.getByText("Et ole minkään organisaation omistaja tai ylläpitäjä")).toBeVisible();
  await expect(page.getByRole("button", { name: "Lataa CSV" })).toHaveCount(0);
});
