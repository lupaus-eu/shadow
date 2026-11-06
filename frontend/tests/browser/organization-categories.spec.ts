import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Locator } from "@playwright/test";

import { apiBase, categories as yearclockCategories, organizationId, plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";
import { answerConfirm } from "./support/confirm";

type Category = { id: string; name: string; color: string | null; display_order: number; version: number; scope: "organization" | "yearclock"; usage: number };
const board: Category = { id: "ca7e0000-0000-4000-8000-000000000001", name: "Board", color: "#1f5f99", display_order: 0, version: 1, scope: "organization", usage: 3 };
const hr: Category = { id: "ca7e0000-0000-4000-8000-000000000002", name: "HR", color: "#2e7d32", display_order: 1, version: 1, scope: "organization", usage: 0 };

async function categoriesApi(context: BrowserContext) {
  let items = [board, hr];
  const calls: Array<[string, string]> = [];
  await context.route(new RegExp(`${apiBase}/api/v1/organizations/${organizationId}/categories.*`), async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(`/api/v1/organizations/${organizationId}/categories`, "");
    if (request.method() === "GET") return route.fulfill({ status: 200, json: items });
    calls.push([request.method(), path.replace(/ca7e0000-[0-9a-f-]+/, "{id}")]);
    const body = request.postData() ? request.postDataJSON() : null;
    if (request.method() === "POST") {
      const created = { id: "ca7e0000-0000-4000-8000-000000000009", name: body.name, color: body.color, display_order: items.length, version: 1, scope: "organization" as const, usage: 0 };
      items = [...items, created];
      return route.fulfill({ status: 201, json: created });
    }
    if (path === "/order") {
      items = body.ordered_ids.map((id: string, index: number) => ({ ...items.find((item) => item.id === id)!, display_order: index, version: 2 }));
      return route.fulfill({ status: 200, json: items });
    }
    items = items.filter((item) => !path.includes(item.id));
    return route.fulfill({ status: 204 });
  });
  return calls;
}

const row = (panel: Locator, name: string) => panel.locator(".label-list > li", { has: panel.page().locator("strong", { hasText: new RegExp(`^${name}$`) }) });

test("Owners define, reorder, and delete Organization Categories", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-24" });
  const calls = await categoriesApi(context);
  await page.goto(`/organizations/${organizationId}/admin/classification`);
  const section = page.getByRole("region", { name: "Organization Categories" });
  await expect(row(section, "Board")).toContainText("3 Events");
  expect(await new AxeBuilder({ page }).include(".classification").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await section.getByLabel("Organization Categories: Name").fill("Finance");
  await section.getByRole("button", { name: "Add Category" }).click();
  await expect(row(section, "Finance")).toBeVisible();
  await section.getByRole("button", { name: "Down: Board" }).click();
  await expect(section.locator(".label-list > li strong")).toHaveText(["HR", "Board", "Finance"]);
  let message = "";
  await section.getByRole("button", { name: "Delete: Board" }).click();
  message = await answerConfirm(page);
  await expect(row(section, "Board")).toHaveCount(0);
  expect(message).toBe("Delete the Organization Category “Board”? 3 Events in all Yearclocks become uncategorized.");
  expect(calls).toEqual([["POST", ""], ["PUT", "/order"], ["DELETE", "/{id}"]]);
});

test("a Yearclock shows Organization Categories locked and groups them in the Event form", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-24" });
  const own = yearclockCategories.map((category) => ({ ...category, scope: "yearclock" }));
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/categories`, (route) => route.fulfill({ status: 200, json: [{ ...board, name: "Company" }, ...own] }));
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const manager = page.getByRole("region", { name: "Categories" });
  await expect(manager.getByRole("list", { name: "Organization Categories" }).getByRole("listitem")).toHaveText(["Company"]);
  await expect(manager.getByText("Shared by the whole Organization.", { exact: false })).toBeVisible();
  await expect(manager.getByRole("button", { name: "Delete: Company" })).toHaveCount(0);
  await expect(manager.getByRole("button", { name: `Delete: ${own[0].name}` })).toBeVisible();
  await page.getByRole("main").getByRole("link", { name: /^Back to / }).click();
  await page.getByRole("button", { name: "New Event" }).click();
  const select = page.getByRole("form", { name: "New Event" }).getByRole("combobox", { name: /^Category/ });
  await expect(select.locator("optgroup")).toHaveCount(2);
  await expect(select.locator('optgroup[label="Organization Categories"] option')).toHaveText(["Company"]);
});
