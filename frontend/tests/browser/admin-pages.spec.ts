import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { adminWorkspace, organizationId } from "./support/admin-fixture";

const pages = [
  ["people", "People", "Invite people, change their roles, and see what each person can open."],
  ["groups", "Groups", "Put members in Groups to give several people the same Yearclock access."],
  ["yearclocks", "Yearclocks and access", "Create, order, archive, and share Yearclocks, and decide who can open each one."],
  ["classification", "Classification", "Categories and Labels that every Yearclock in the Organization can use."],
  ["activity", "Activity", "What changed in the Organization, newest first."],
  ["support", "Support Access", "Decide whether platform support may see your content."],
  ["agents", "Connect an agent", "Let an AI agent you choose work with this Organization's Yearclocks, and switch that off when needed."],
  ["billing", "Billing and seats", "Seats and the subscription."],
  ["settings", "Organization settings", "The Organization's details, its export, and its deletion."],
] as const;

test("every administration page has a title, a description, and no accessibility violations", async ({ context, page }) => {
  await adminWorkspace(context, { role: "owner" });
  for (const [section, title, description] of pages) {
    await page.goto(`/organizations/${organizationId}/admin/${section}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
    await expect(page.getByRole("main").getByText(description)).toBeVisible();
    await expect(page.getByRole("main").getByRole("heading", { level: 2 }).first()).toBeVisible();
    const violations = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => `${section}: ${violation.id}`));
    expect(violations).toEqual([]);
  }
});

test("the overview keeps Yearclocks and My groups, and administration lives on its pages", async ({ context, page }) => {
  await adminWorkspace(context, { role: "owner" });
  await page.goto(`/organizations/${organizationId}`);
  await expect(page.getByRole("region", { name: "Open a Yearclock" })).toBeVisible();
  await expect(page.getByRole("region", { name: "People", exact: true })).toHaveCount(0);
  await expect(page.getByText("Delete Organization", { exact: true })).toHaveCount(0);
  await page.goto(`/organizations/${organizationId}/admin/settings`);
  const danger = page.getByRole("region", { name: "Danger zone" });
  await expect(danger.getByRole("button", { name: "Delete Organization" })).toBeDisabled();
});

test("Owners and Admins connect an agent: the secret shows on request and the switch stops agent access", async ({ context, page }) => {
  const state = await adminWorkspace(context, { role: "owner" });
  await page.goto(`/organizations/${organizationId}/admin/agents`);
  const connect = page.getByRole("region", { name: "Connect an agent" });
  await expect(connect.getByText("https://yearclock.example.com/api/mcp")).toBeVisible();
  await expect(connect.getByText("yearclock-mcp", { exact: true })).toBeVisible();
  await expect(connect.getByText("shared-secret-for-tests")).toHaveCount(0);
  await connect.getByRole("button", { name: "Show the secret" }).click();
  await expect(connect.getByText("shared-secret-for-tests")).toBeVisible();
  await connect.getByRole("button", { name: "Hide the secret" }).click();
  await expect(connect.getByText("shared-secret-for-tests")).toHaveCount(0);
  const access = page.getByRole("region", { name: "Agent access for this Organization" });
  await access.getByRole("button", { name: "Turn off" }).click();
  await expect(access.getByText("Off", { exact: true })).toBeVisible();
  expect(state.requests.filter((item) => item.method === "PATCH" && item.path === "/mcp").map((item) => item.body)).toEqual([{ enabled: false }]);
});

test("an operator block cannot be turned off by the Organization", async ({ context, page }) => {
  const state = await adminWorkspace(context, { role: "admin" });
  state.mcp = { ...state.mcp, platform_blocked: true };
  await page.goto(`/organizations/${organizationId}/admin/agents`);
  const access = page.getByRole("region", { name: "Agent access for this Organization" });
  await expect(access.getByText("The operator has blocked agent access to this Organization. It cannot be turned on here.")).toBeVisible();
  await expect(access.getByRole("button", { name: /Turn o(n|ff)/ })).toHaveCount(0);
});
