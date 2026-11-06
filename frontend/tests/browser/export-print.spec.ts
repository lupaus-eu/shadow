import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

import { plannerApi, yearclockPath } from "./support/yearclock-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const open = async (page: Page, display?: string) => {
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await expect(page.getByRole("button", { name: /^Export$|^Vie$/ })).toBeVisible();
  await page.waitForLoadState("networkidle");
  if (display) await page.getByRole("radiogroup", { name: "Display" }).getByRole("radio", { name: display }).click();
};

test("the Export menu offers Print and, for the circle only, the image", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await open(page);
  expect(await axe(page)).toEqual([]);
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByRole("menuitem")).toHaveText(["Print", "Download image (PNG)", "Export to Excel…", "Export to CSV…", "Export to calendar (.ics)…", "Import from Excel or CSV…"]);
  await page.keyboard.press("Escape");
  await page.getByRole("radio", { name: "List", exact: true }).click();
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByRole("menuitem")).toHaveText(["Print", "Export to Excel…", "Export to CSV…", "Export to calendar (.ics)…", "Import from Excel or CSV…"]);
});

test("Print opens the browser's print dialog without any request to the server", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await context.addInitScript("window.__printed = 0; window.print = () => { window.__printed += 1; };");
  await open(page);
  const requests: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/api/")) requests.push(request.url()); });
  await page.getByRole("button", { name: "Export" }).click();
  await page.getByRole("menuitem", { name: "Print" }).click();
  expect(await page.evaluate(() => (window as unknown as { __printed: number }).__printed)).toBe(1);
  expect(requests).toEqual([]);
});

test("the printout hides the chrome and adds a header, a legend, and the Event list", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await open(page);
  await expect(page.locator(".yc-print-header")).toBeHidden();
  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeHidden();
  await expect(page.getByRole("radiogroup", { name: "Display" })).toBeHidden();
  await expect(page.getByRole("tablist", { name: "Yearclock panel" })).toBeHidden();
  const header = page.locator(".yc-print-header");
  await expect(header.getByRole("heading", { name: "Northwind Yearclock" })).toBeVisible();
  await expect(header).toContainText("1 Jan 2026 – 31 Dec 2026");
  await expect(header).toContainText("Printed ");
  const legend = page.locator(".yc-print-legend");
  await expect(legend).toContainText("Lanes: Governance, Finance");
  await expect(legend).toContainText("Board");
  await expect(legend).toContainText("Audit");
  const events = page.locator(".yc-print-events");
  await expect(events.getByRole("row", { name: /Board meeting/ })).toBeVisible();
  await expect(events.getByRole("row", { name: /Weekly finance check — recurring, 20 occurrences/ })).toBeVisible();
  await expect(page.getByRole("group", { name: /Northwind Yearclock, January 2026/ })).toBeVisible();
});

test("printing the list uses the list itself without a second Event list", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await open(page, "List");
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".yc-print-events")).toHaveCount(0);
  await expect(page.locator(".yc-print-legend")).toBeVisible();
  await expect(page.getByRole("region", { name: "Events in this window" }).getByRole("table")).toBeVisible();
});

test("Download image saves a PNG at twice the screen size and sends nothing to the server", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await open(page);
  const svgWidth = Math.round((await page.locator(".yc-svg").boundingBox())!.width);
  const requests: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/api/")) requests.push(request.url()); });
  await page.getByRole("button", { name: "Export" }).click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("menuitem", { name: "Download image (PNG)" }).click()]);
  expect(download.suggestedFilename()).toBe("northwind-yearclock-2026-01-01.png");
  const bytes = readFileSync((await download.path())!);
  expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
  expect(bytes.readUInt32BE(16)).toBe((svgWidth + 48) * 2);
  expect(bytes.readUInt32BE(20)).toBeGreaterThan(bytes.readUInt32BE(16));
  expect(requests).toEqual([]);
});

test("the menu is in Finnish", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", locale: "fi" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: "Vie" }).click();
  await expect(page.getByRole("menuitem")).toHaveText(["Tulosta", "Lataa kuva (PNG)", "Vie Exceliin…", "Vie CSV-tiedostoon…", "Vie kalenteriin (.ics)…", "Tuo Excelistä tai CSV:stä…"]);
});
