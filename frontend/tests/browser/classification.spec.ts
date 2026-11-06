import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Locator } from "@playwright/test";

import { apiBase, organizationId, plannerApi } from "./support/yearclock-fixture";
import { answerConfirm } from "./support/confirm";

type Label = { id: string; name: string; color: string; version: number; usage: number };

async function labelsApi(context: BrowserContext, initial: Label[]) {
  let labels = [...initial];
  const calls: Array<{ method: string; path: string; body: unknown }> = [];
  await context.route(new RegExp(`${apiBase}/api/v1/organizations/${organizationId}/labels.*`), async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(`/api/v1/organizations/${organizationId}/labels`, "") + url.search;
    const body = request.postData() ? request.postDataJSON() : null;
    calls.push({ method: request.method(), path, body });
    if (request.method() === "GET") return route.fulfill({ status: 200, json: labels });
    if (request.method() === "POST" && path === "") {
      if (labels.length >= 3) return route.fulfill({ status: 409, json: { detail: { reason: "limit_reached", limit: "labels_per_organization", maximum: 3 } } });
      const created = { id: `1abe1000-0000-4000-8000-00000000000${labels.length + 1}`, name: body.name, color: body.color, version: 1, usage: 0 };
      labels.push(created);
      return route.fulfill({ status: 201, json: created });
    }
    const id = path.split(/[/?]/)[1];
    if (request.method() === "PATCH") {
      labels = labels.map((label) => (label.id === id ? { ...label, name: body.name, color: body.color, version: label.version + 1 } : label));
      return route.fulfill({ status: 200, json: labels.find((label) => label.id === id) });
    }
    if (path.includes("/merge")) {
      const source = labels.find((label) => label.id === id)!;
      labels = labels.filter((label) => label.id !== id).map((label) => (label.id === body.into_label_id ? { ...label, usage: label.usage + source.usage, version: label.version + 1 } : label));
      return route.fulfill({ status: 200, json: labels.find((label) => label.id === body.into_label_id) });
    }
    labels = labels.filter((label) => label.id !== id);
    return route.fulfill({ status: 204 });
  });
  return calls;
}

const row = (panel: Locator, name: string) => panel.locator(".label-list > li", { has: panel.page().locator("strong", { hasText: new RegExp(`^${name}$`) }) });

const budget = { id: "1abe1000-0000-4000-8000-0000000000a1", name: "Budget", color: "#1f5f99", version: 1, usage: 4 };
const finance = { id: "1abe1000-0000-4000-8000-0000000000a2", name: "Finance", color: "#2e7d32", version: 1, usage: 2 };

test("Owners create, rename, merge, and delete Labels with confirmations that state the usage", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-24" });
  const calls = await labelsApi(context, [budget, finance]);
  await page.goto(`/organizations/${organizationId}/admin/classification`);
  const panel = page.locator(".classification");
  await expect(panel.getByRole("note")).toContainText("Label names are visible to everyone in the Organization");
  await expect(row(panel, "Budget")).toContainText("4 Events");
  expect(await new AxeBuilder({ page }).include(".classification").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);

  await panel.getByLabel("Name", { exact: true }).fill("Decision needed");
  await panel.getByLabel("Colour", { exact: true }).selectOption({ label: "Red" });
  await panel.getByRole("button", { name: "Add Label" }).click();
  await expect(row(panel, "Decision needed")).toBeVisible();

  await panel.getByLabel("Name: Finance").fill("Finance team");
  await panel.getByRole("button", { name: "Save: Finance" }).click();
  await expect(row(panel, "Finance team")).toBeVisible();

  const messages: string[] = [];
  await panel.getByLabel("Merge into: Budget").selectOption({ label: "Finance team" });
  await panel.getByRole("button", { name: "Merge: Budget" }).click();
  messages.push(await answerConfirm(page));
  await expect(row(panel, "Finance team")).toContainText("6 Events");
  await panel.getByRole("button", { name: "Delete: Decision needed" }).click();
  messages.push(await answerConfirm(page));
  await expect(row(panel, "Decision needed")).toHaveCount(0);

  expect(messages).toEqual([
    "Merge “Budget” into “Finance team”? 4 Events move to “Finance team”, and “Budget” is removed.",
    "Delete the Label “Decision needed”? It is removed from 0 Events in all Yearclocks.",
  ]);
  expect(calls.filter((call) => call.method !== "GET").map((call) => [call.method, call.path.replace(/1abe1000-[0-9a-f-]+/g, "{id}")])).toEqual([
    ["POST", ""],
    ["PATCH", "/{id}"],
    ["POST", "/{id}/merge"],
    ["DELETE", "/{id}?expected_version=1&confirm=true"],
  ]);
});

test("the Label ceiling is explained, and a declined confirmation changes nothing", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-24" });
  const calls = await labelsApi(context, [budget, finance, { ...finance, id: "1abe1000-0000-4000-8000-0000000000a3", name: "HR" }]);
  await page.goto(`/organizations/${organizationId}/admin/classification`);
  const panel = page.locator(".classification");
  await panel.getByLabel("Name", { exact: true }).fill("One more");
  await panel.getByRole("button", { name: "Add Label" }).click();
  await expect(panel.getByRole("alert")).toHaveText("The Organization already has the maximum of 3 Labels. Merge or delete Labels first.");
  await panel.getByRole("button", { name: "Delete: Budget" }).click();
  await answerConfirm(page, "cancel");
  await expect(row(panel, "Budget")).toBeVisible();
  expect(calls.filter((call) => call.method === "DELETE")).toEqual([]);
});

test("Members do not see the Classification panel", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-24" });
  await labelsApi(context, [budget]);
  await page.goto(`/organizations/${organizationId}`);
  await expect(page.getByRole("heading", { name: "Northwind", exact: true })).toBeVisible();
  await expect(page.getByText("Classification", { exact: true })).toHaveCount(0);
});

test("a read-only Organization shows Labels without editing controls", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-24", subscription: { state: "read_only", writable: false } });
  await labelsApi(context, [budget]);
  await page.goto(`/organizations/${organizationId}/admin/classification`);
  const panel = page.locator(".classification");
  await expect(panel.getByRole("status")).toHaveText("Labels cannot be changed while the Organization is read-only.");
  await expect(row(panel, "Budget")).toBeVisible();
  await expect(panel.getByRole("button")).toHaveCount(0);
});
