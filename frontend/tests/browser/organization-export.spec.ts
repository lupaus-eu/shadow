import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { adminWorkspace, apiBase, organizationId } from "./support/admin-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const url = `${apiBase}/api/v1/organizations/${organizationId}/export`;

async function serve(context: BrowserContext, answer: () => { status: number; json?: unknown }) {
  let asked = 0;
  await context.route(url, (route) => {
    asked += 1;
    const reply = answer();
    if (reply.status !== 200) return route.fulfill({ status: reply.status, json: reply.json ?? {} });
    return route.fulfill({ status: 200, contentType: "application/json", headers: { "Content-Disposition": 'attachment; filename="northwind-organization-export-2026-10-05.json"', "Access-Control-Expose-Headers": "Content-Disposition" }, body: '{"schema":"yearclock-export/1"}' });
  });
  return () => asked;
}

test("an Owner downloads the Organization Export from the settings page", async ({ context, page }) => {
  await adminWorkspace(context, { role: "owner" });
  const asked = await serve(context, () => ({ status: 200 }));
  await page.goto(`/organizations/${organizationId}/admin/settings`);
  const section = page.getByRole("region", { name: "Organization Export" });
  await expect(section.getByText("Left out: Event history, the Activity log, billing data, and email records.")).toBeVisible();
  expect(await axe(page)).toEqual([]);
  const [download] = await Promise.all([page.waitForEvent("download"), section.getByRole("button", { name: "Download Organization Export" }).click()]);
  expect(download.suggestedFilename()).toBe("northwind-organization-export-2026-10-05.json");
  await expect(page.getByRole("status").filter({ hasText: "Organization Export saved." })).toBeVisible();
  expect(asked()).toBe(1);
});

test("a refusal says when to retry and a failure stays next to the button", async ({ context, page }) => {
  await adminWorkspace(context, { role: "owner" });
  let reply: { status: number; json?: unknown } = { status: 429, json: { detail: { reason: "rate_limited", retry_after_seconds: 3000 } } };
  await serve(context, () => reply);
  await page.goto(`/organizations/${organizationId}/admin/settings`);
  const section = page.getByRole("region", { name: "Organization Export" });
  await section.getByRole("button", { name: "Download Organization Export" }).click();
  await expect(section.getByRole("alert")).toHaveText("You have downloaded the export too often. Try again in 50 minutes.");
  reply = { status: 500 };
  await section.getByRole("button", { name: "Download Organization Export" }).click();
  await expect(section.getByRole("alert")).toHaveText("The Organization Export could not be downloaded. Try again.");
});

test("an Administrator has no export on the settings address", async ({ context, page }) => {
  await adminWorkspace(context, { role: "admin" });
  await page.goto(`/organizations/${organizationId}/admin/settings`);
  await expect(page.getByRole("alert")).toHaveText("This page does not exist.");
  await expect(page.getByRole("region", { name: "Organization Export" })).toHaveCount(0);
});

test("the Organization Export page text is in Finnish", async ({ context, page }) => {
  await adminWorkspace(context, { role: "owner", locale: "fi" });
  await page.goto(`/organizations/${organizationId}/admin/settings`);
  await expect(page.getByRole("region", { name: "Organisaation vienti" }).getByRole("button", { name: "Lataa organisaation vienti" })).toBeVisible();
});
