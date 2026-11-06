import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { adminWorkspace, apiBase, organizationId } from "./support/admin-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const listing = (items: unknown[]) => (context: BrowserContext) => context.route(`${apiBase}/api/v1/legal/documents?*`, (route) => route.fulfill({ status: 200, json: items }));
const item = (key: string, title: string, extra: Record<string, unknown> = {}) => ({ key, title, version: 1, effective_from: "2026-01-01", status: "published", acceptance: "required", ...extra });

async function signedInWithoutOrganization(context: BrowserContext, locale: "en" | "fi" = "en") {
  await context.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 200, json: { user_account: { id: "fc4dbf31-2fd3-43cf-bc95-96642b93b9eb", account_class: "customer", email: "owner@example.com", display_name: "Olivia Owner", locale } } }));
  await context.route(`${apiBase}/api/v1/system/status`, (route) => route.fulfill({ status: 200, json: { status: "ok", database: "ready", schema_revision: "0049" } }));
  await context.route(`${apiBase}/api/v1/organizations`, (route) => route.fulfill({ status: 200, json: { organizations: [] } }));
}

async function fillSignup(page: Page) {
  await page.getByLabel("Organization name").fill("Northwind Oy");
  await page.getByLabel("Billing name").fill("Northwind Billing");
}

test("the sign-up form asks for every published required document and sends the acceptances", async ({ context, page }) => {
  await signedInWithoutOrganization(context);
  await listing([item("terms", "Terms of service"), item("dpa", "Data processing agreement"), item("privacy", "Privacy notice", { acceptance: "none" }), item("switching", "Switching", { status: "draft" }), item("subprocessors", "Sub-processors", { acceptance: "notice" })])(context);
  let posted: unknown = null;
  await context.route(`${apiBase}/api/v1/organization-signups`, (route) => { posted = route.request().postDataJSON(); return route.fulfill({ status: 201, json: { organization_id: organizationId, organization_name: "Northwind Oy", status: "pending_activation", initial_seats: 1, expires_at: "2026-07-30T09:00:00Z", checkout_url: "http://checkout.test/pay", initial_content: null } }); });
  await context.route("http://checkout.test/pay", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<h1>Checkout</h1>" }));
  await page.goto("/");
  await fillSignup(page);
  const submit = page.getByRole("button", { name: "Continue to secure checkout" });
  await expect(page.getByRole("checkbox")).toHaveCount(2);
  await expect(submit).toBeDisabled();
  await page.getByRole("checkbox", { name: /Terms of service/ }).check();
  await expect(submit).toBeDisabled();
  await page.getByRole("checkbox", { name: /Data processing agreement/ }).check();
  expect(await axe(page)).toEqual([]);
  await submit.click();
  await expect(page.getByRole("heading", { name: "Checkout" })).toBeVisible();
  expect(posted).toMatchObject({ accepted_documents: [{ document_key: "terms", version: 1, locale: "en" }, { document_key: "dpa", version: 1, locale: "en" }] });
});

test("nothing is asked while no required document is published", async ({ context, page }) => {
  await signedInWithoutOrganization(context);
  await listing([item("terms", "Terms of service", { status: "draft" })])(context);
  await page.goto("/");
  await fillSignup(page);
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Continue to secure checkout" })).toBeEnabled();
});

function legalState(documents: Array<Record<string, unknown>>) {
  const accepted: string[] = [];
  const handler = async (route: import("@playwright/test").Route, path: string) => {
    if (path.startsWith("/legal/acceptances")) {
      const body = route.request().postDataJSON() as { document_key: string; version: number };
      accepted.push(`${body.document_key}:${body.version}`);
      const doc = documents.find((entry) => entry.key === body.document_key)!;
      Object.assign(doc, { state: "accepted", accepted_version: body.version, accepted_at: "2026-11-05T10:00:00Z", accepted_by_name: "Olivia Owner", accepted_by_former_member: false });
      await route.fulfill({ status: 200, json: doc });
      return true;
    }
    if (path.startsWith("/legal")) { await route.fulfill({ status: 200, json: { documents } }); return true; }
    return false;
  };
  return { accepted, handler };
}

const due = { key: "terms", title: "Terms of service", acceptance: "required", current_version: 2, effective_from: "2026-01-01", accepted_version: 1, accepted_at: "2026-03-01T10:00:00Z", accepted_by_name: null, accepted_by_former_member: true, state: "acceptance_due" };
const accepted = { key: "dpa", title: "Data processing agreement", acceptance: "required", current_version: 1, effective_from: "2026-01-01", accepted_version: 1, accepted_at: "2026-03-01T10:00:00Z", accepted_by_name: "Olivia Owner", accepted_by_former_member: false, state: "accepted" };

test("an Owner sees a due version in the settings and the banner, and accepts it", async ({ context, page }) => {
  const documents = [structuredClone(due), structuredClone(accepted)];
  const { accepted: sent, handler } = legalState(documents);
  await adminWorkspace(context, { extra: (route, path) => handler(route, path) });
  await page.goto(`/organizations/${organizationId}/admin/billing`);
  await expect(page.getByRole("status").filter({ hasText: "A new version is in force and needs an Owner's acceptance: Terms of service." })).toBeVisible();
  await page.getByRole("link", { name: "Review and accept" }).click();
  await expect(page.getByRole("heading", { name: "Legal documents" })).toBeVisible();
  await expect(page.getByText("Version 1 accepted on", { exact: false }).first()).toContainText("a former member");
  await expect(page.getByText("A new version is waiting for your acceptance")).toBeVisible();
  expect(await axe(page)).toEqual([]);
  await page.getByRole("button", { name: /Accept this version/ }).click();
  await expect(page.getByText("Version 2 accepted on", { exact: false })).toContainText("Olivia Owner");
  await expect(page.getByRole("button", { name: /Accept this version/ })).toHaveCount(0);
  expect(sent).toEqual(["terms:2"]);
});

test("the banner waits for the in-force date, and Admins see neither block nor banner", async ({ context, page }) => {
  const future = [{ ...structuredClone(due), effective_from: "2999-01-01" }];
  await adminWorkspace(context, { extra: (route, path) => legalState(future).handler(route, path) });
  await page.goto(`/organizations/${organizationId}/admin/billing`);
  await expect(page.getByRole("heading", { name: "Subscription" }).or(page.getByText("Billing and seats")).first()).toBeVisible();
  await expect(page.getByText("needs an Owner's acceptance")).toHaveCount(0);
  await page.goto(`/organizations/${organizationId}/admin/settings`);
  await expect(page.getByRole("heading", { name: "Legal documents" })).toBeVisible();

  const asked: string[] = [];
  const state = await adminWorkspace(context, { role: "admin", extra: (route, path) => { if (path.startsWith("/legal")) asked.push(path); return false; } });
  await page.goto(`/organizations/${organizationId}/admin/settings`);
  await expect(page.getByRole("alert")).toBeVisible(); // Settings is an Owner area; an Admin gets "not found".
  await expect(page.getByRole("heading", { name: "Legal documents" })).toHaveCount(0);
  await page.goto(`/organizations/${organizationId}/admin/billing`);
  await expect(page.getByText("needs an Owner's acceptance")).toHaveCount(0);
  expect(asked).toEqual([]);
  expect(state.requests.some((request) => request.path.startsWith("/legal"))).toBe(false);
});

test("the Owner's block is in Finnish for a Finnish user", async ({ context, page }) => {
  const documents = [structuredClone(due)];
  await adminWorkspace(context, { locale: "fi", extra: (route, path) => legalState(documents).handler(route, path) });
  await page.goto(`/organizations/${organizationId}/admin/settings`);
  await expect(page.getByRole("heading", { name: "Lakiasiakirjat" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Hyväksy tämä versio/ })).toBeVisible();
});
