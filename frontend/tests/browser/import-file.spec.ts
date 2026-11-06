import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { apiBase, organizationId, plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const importUrl = `${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/import`;
const csv = { name: "events.csv", mimeType: "text/csv", buffer: Buffer.from("Title,Starts,Lane\r\nBoard,2026-10-01,General\r\nAudit,2026-10-02,General\r\n") };

const good = { rows: 2, create: [{ row: 2, title: "Board", starts_on: "2026-10-01", ends_on: null, lane: "General", category: "Board", labels: ["Draft"] }, { row: 3, title: "Audit", starts_on: "2026-10-02", ends_on: "2026-10-05", lane: "General", category: null, labels: [] }], skipped: [{ row: 4, title: "Old", reason: "duplicate" }], errors: [], created: 0 };

async function serve(context: BrowserContext, answer: (dryRun: boolean) => { status: number; json: unknown }) {
  const requests: Array<{ dryRun: boolean; format: string; body: string }> = [];
  await context.route(new RegExp(`${importUrl}\\?.*`), (route) => {
    const url = new URL(route.request().url());
    const dryRun = url.searchParams.get("dry_run") === "true";
    requests.push({ dryRun, format: url.searchParams.get("format") ?? "", body: route.request().postData() ?? "" });
    const reply = answer(dryRun);
    return route.fulfill({ status: reply.status, json: reply.json });
  });
  return requests;
}
const open = async (page: Page, entry = "Import from Excel or CSV…", group = "Export") => {
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: group }).click();
  await page.getByRole("menuitem", { name: entry }).click();
  return page.getByRole("dialog", { name: /Import Events|Tuo tapahtumat/ });
};

test("an Editor previews a file, sees what will happen, and saves it", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const requests = await serve(context, (dryRun) => ({ status: 200, json: dryRun ? good : { ...good, created: 2 } }));
  const dialog = await open(page);
  await expect(dialog.getByRole("button", { name: /^Import 0 Events$/ })).toBeDisabled();
  await dialog.getByLabel(/Spreadsheet file/).setInputFiles(csv);
  await expect(dialog.getByRole("status")).toHaveText("2 Events will be created, 1 skipped.");
  const table = dialog.getByRole("table", { name: "Events to create" });
  await expect(table.getByRole("row")).toHaveCount(3);
  await expect(table.getByRole("row", { name: /Audit.*2026-10-05/ })).toBeVisible();
  await expect(dialog.getByText("Row 4: Old — Already exists")).toBeVisible();
  expect(await axe(page)).toEqual([]);
  expect(requests).toEqual([{ dryRun: true, format: "csv", body: csv.buffer.toString() }]);
  await dialog.getByRole("button", { name: "Import 2 Events" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("status").filter({ hasText: "2 Events imported." })).toBeVisible();
  expect(requests.map((request) => request.dryRun)).toEqual([true, false]);
  expect(requests[1].body).toBe(csv.buffer.toString());
});

test("every problem is listed with its row and nothing can be saved", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await serve(context, () => ({ status: 200, json: { rows: 3, create: [], skipped: [], created: 0, errors: [{ row: 2, column: "lane", reason: "unknown_lane", value: "Operations" }, { row: 3, column: "starts", reason: "invalid_date", value: "someday" }, { row: 4, column: "title", reason: "duplicate_in_file", value: "2" }] } }));
  const dialog = await open(page);
  await dialog.getByLabel(/Spreadsheet file/).setInputFiles(csv);
  await expect(dialog.getByRole("alert")).toHaveText("3 problems: fix the file and choose it again.");
  const rows = dialog.getByRole("table").getByRole("row");
  await expect(rows.nth(1)).toContainText("2LaneThere is no Lane named “Operations”");
  await expect(rows.nth(2)).toContainText("“someday” is not a date (use 2026-03-10)");
  await expect(rows.nth(3)).toContainText("The same Event as row 2");
  await expect(dialog.getByRole("button", { name: /^Import/ })).toBeDisabled();
});

test("a file the server refuses, a wrong type, and a rate limit each say why", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  let reply: { status: number; json: unknown } = { status: 422, json: { detail: { reason: "macros_not_allowed" } } };
  const requests = await serve(context, () => reply);
  const dialog = await open(page);
  const upload = dialog.getByLabel(/Spreadsheet file/);
  await upload.setInputFiles({ name: "macros.xlsm", mimeType: "application/vnd.ms-excel", buffer: Buffer.from("x") });
  await expect(dialog.getByRole("alert")).toHaveText("Choose an .xlsx or .csv file.");
  expect(requests).toEqual([]);
  await upload.setInputFiles({ name: "plan.xlsx", mimeType: "application/octet-stream", buffer: Buffer.from("x") });
  await expect(dialog.getByRole("alert")).toHaveText("Files with macros are not accepted. Save a copy as .xlsx without macros.");
  reply = { status: 422, json: { detail: { reason: "too_many_rows", maximum: 1000 } } };
  await upload.setInputFiles(csv);
  await expect(dialog.getByRole("alert")).toHaveText("The file has more than 1000 rows.");
  reply = { status: 413, json: { detail: { reason: "file_too_large", maximum_bytes: 2097152 } } };
  await upload.setInputFiles(csv);
  await expect(dialog.getByRole("alert")).toHaveText("The file is larger than 2 MB.");
  reply = { status: 429, json: { detail: { reason: "rate_limited", retry_after_seconds: 61 } } };
  await upload.setInputFiles(csv);
  await expect(dialog.getByRole("alert")).toHaveText("You have made too many exports or imports. Try again in 2 minutes.");
  reply = { status: 409, json: { detail: { reason: "limit_reached", maximum: 3000 } } };
  await upload.setInputFiles(csv);
  await expect(dialog.getByRole("alert")).toHaveText("The Yearclock would exceed its limit of 3000 Events.");
});

test("the template downloads in the user's language, and Viewers are not offered the import", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const asked: string[] = [];
  await context.route(new RegExp(`${importUrl}/template.*`), (route) => { asked.push(new URL(route.request().url()).searchParams.get("locale") ?? ""); return route.fulfill({ status: 200, contentType: "application/octet-stream", headers: { "Content-Disposition": 'attachment; filename="yearclock-import-template-en.xlsx"', "Access-Control-Expose-Headers": "Content-Disposition" }, body: "template" }); });
  const dialog = await open(page);
  const [download] = await Promise.all([page.waitForEvent("download"), dialog.getByRole("button", { name: "Download template (Excel)" }).click()]);
  expect(download.suggestedFilename()).toBe("yearclock-import-template-en.xlsx");
  expect(asked).toEqual(["en"]);
});

test("a Viewer's Export menu has no import", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-23" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByRole("menuitem")).toHaveText(["Print", "Download image (PNG)", "Export to Excel…", "Export to CSV…", "Export to calendar (.ics)…"]);
});

test("the import dialog and its messages are in Finnish", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", locale: "fi" });
  await serve(context, () => ({ status: 200, json: good }));
  const dialog = await open(page, "Tuo Excelistä tai CSV:stä…", "Vie");
  await dialog.getByLabel(/Taulukkotiedosto/).setInputFiles(csv);
  await expect(dialog.getByRole("status")).toHaveText("2 tapahtumaa luodaan, 1 ohitetaan.");
  await expect(dialog.getByRole("button", { name: "Tuo 2 tapahtumaa" })).toBeEnabled();
});
