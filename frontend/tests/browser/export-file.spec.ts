import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const exportUrl = `${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/export`;

async function serve(context: BrowserContext, respond?: () => { status: number; json?: unknown }) {
  const bodies: Array<Record<string, unknown>> = [];
  await context.route(exportUrl, (route) => {
    bodies.push(route.request().postDataJSON());
    const override = respond?.();
    if (override) return route.fulfill({ status: override.status, json: override.json ?? {} });
    const format = bodies.at(-1)!.format as string;
    const types: Record<string, string> = { csv: "text/csv", ics: "text/calendar", xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" };
    return route.fulfill({ status: 200, contentType: types[format], headers: { "Content-Disposition": `attachment; filename="northwind-yearclock-2026-01-01-12m.${format}"`, "Access-Control-Expose-Headers": "Content-Disposition, Retry-After" }, body: "file" });
  });
  return bodies;
}
const open = async (page: Page, entry: string, locale = "en") => {
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: locale === "fi" ? "Vie" : "Export" }).click();
  await page.getByRole("menuitem", { name: entry }).click();
  return page.getByRole("dialog");
};

test("Export to Excel asks what to export and downloads the file the server builds", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const bodies = await serve(context);
  const dialog = await open(page, "Export to Excel…");
  await expect(dialog.getByRole("heading", { name: "Export Events" })).toBeVisible();
  await expect(dialog.getByLabel("The current window (1 Jan 2026 – 31 Dec 2026)")).toBeChecked();
  await expect(dialog.getByLabel("Excel (.xlsx)")).toBeChecked();
  expect(await axe(page)).toEqual([]);
  const [download] = await Promise.all([page.waitForEvent("download"), dialog.getByRole("button", { name: "Export", exact: true }).click()]);
  expect(download.suggestedFilename()).toBe("northwind-yearclock-2026-01-01-12m.xlsx");
  expect(bodies).toEqual([{ format: "xlsx", scope: "window", window_start: "2026-01-01", length: 12, filters: { lanes: [], categories: [], labels: [] }, locale: "en" }]);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("status").filter({ hasText: "Export saved." })).toBeVisible();
});

test("Export to CSV starts with CSV, can take the whole Yearclock, and sends the Filters", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const bodies = await serve(context);
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await showTab(page, "Filters");
  await page.getByRole("region", { name: "Filters" }).getByRole("group", { name: "Lanes" }).getByLabel(/Finance \(/).check();
  await page.getByRole("button", { name: "Export" }).click();
  await page.getByRole("menuitem", { name: "Export to CSV…" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("CSV (text file)")).toBeChecked();
  await expect(dialog.getByText("Your Filters are applied.")).toBeVisible();
  await dialog.getByLabel("The whole Yearclock").check();
  await expect(dialog.getByText("Your Filters are applied.")).toHaveCount(0);
  const [download] = await Promise.all([page.waitForEvent("download"), dialog.getByRole("button", { name: "Export", exact: true }).click()]);
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
  expect(bodies[0]).toMatchObject({ format: "csv", scope: "all", filters: { lanes: [lanes[1].id], categories: [], labels: [] } });
});

test("Export to calendar sends the ics format in either language", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  const bodies = await serve(context);
  const dialog = await open(page, "Export to calendar (.ics)…");
  await expect(dialog.getByLabel("Calendar file (.ics)")).toBeChecked();
  expect(await axe(page)).toEqual([]);
  const [download] = await Promise.all([page.waitForEvent("download"), dialog.getByRole("button", { name: "Export", exact: true }).click()]);
  expect(download.suggestedFilename()).toMatch(/\.ics$/);
  expect(bodies[0]).toMatchObject({ format: "ics", scope: "window", locale: "en" });
});

test("a refusal for too many exports says when to retry, and other failures stay in the dialog", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  let answer: { status: number; json?: unknown } = { status: 429, json: { detail: { reason: "rate_limited", retry_after_seconds: 125 } } };
  await serve(context, () => answer);
  const dialog = await open(page, "Export to Excel…");
  await dialog.getByRole("button", { name: "Export", exact: true }).click();
  await expect(dialog.getByRole("alert")).toHaveText("You have made too many exports or imports. Try again in 3 minutes.");
  answer = { status: 500 };
  await dialog.getByRole("button", { name: "Export", exact: true }).click();
  await expect(dialog.getByRole("alert")).toHaveText("The export failed. Try again.");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("the export dialog and its request are in Finnish", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", locale: "fi" });
  const bodies = await serve(context);
  const dialog = await open(page, "Vie Exceliin…", "fi");
  await expect(dialog.getByRole("heading", { name: "Vie tapahtumat" })).toBeVisible();
  await expect(dialog.getByLabel(/^Nykyinen jakso/)).toBeChecked();
  const [download] = await Promise.all([page.waitForEvent("download"), dialog.getByRole("button", { name: "Vie", exact: true }).click()]);
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
  expect(bodies[0].locale).toBe("fi");
});
