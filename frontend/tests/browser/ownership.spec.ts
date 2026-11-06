import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { adminWorkspace, apiBase, mika, organizationId, owner, sanna } from "./support/admin-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const people = `/organizations/${organizationId}/admin/people`;

test("an Owner transfers ownership after reading what an Owner can do, and the request carries the choice", async ({ context, page }) => {
  const calls: Array<{ path: string; body: unknown }> = [];
  await adminWorkspace(context, { extra: async (route, path) => { if (/transfer-ownership$/.test(path)) { calls.push({ path, body: route.request().postDataJSON() }); await route.fulfill({ status: 200, json: { ...mika, role: "owner", version: 2 } }); return true; } return false; } });
  await page.goto(people);
  await page.getByRole("button", { name: "Transfer ownership" }).click();
  const dialog = page.getByRole("dialog", { name: "Transfer ownership" });
  await expect(dialog.getByText("Owners manage billing and the subscription", { exact: false })).toBeVisible();
  await expect(dialog.getByText("The billing contact is not changed.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Transfer ownership" })).toBeDisabled();
  expect(await axe(page)).toEqual([]);
  await dialog.getByLabel("New Owner").selectOption({ label: "Mika Member (Member)" });
  await dialog.getByRole("button", { name: "Transfer ownership" }).click();
  await expect(page.getByText("Mika Member is now an Owner.")).toBeVisible();
  expect(calls).toEqual([{ path: `/memberships/${mika.id}/transfer-ownership`, body: { keep_owner: false, expected_version: 1 } }]);
});

test("keeping the Owner role is sent as keep_owner", async ({ context, page }) => {
  const bodies: unknown[] = [];
  await adminWorkspace(context, { extra: async (route, path) => { if (/transfer-ownership$/.test(path)) { bodies.push(route.request().postDataJSON()); await route.fulfill({ status: 200, json: { ...sanna, role: "owner", version: 2 } }); return true; } return false; } });
  await page.goto(people);
  await page.getByRole("button", { name: "Transfer ownership" }).click();
  const dialog = page.getByRole("dialog", { name: "Transfer ownership" });
  await dialog.getByLabel("New Owner").selectOption({ label: "Sanna Sales (Member)" });
  await dialog.getByLabel("Keep me as an Owner").check();
  await dialog.getByRole("button", { name: "Transfer ownership" }).click();
  await expect(page.getByText("Sanna Sales is now an Owner.")).toBeVisible();
  expect(bodies).toEqual([{ keep_owner: true, expected_version: 1 }]);
});

test("choosing Owner in the role list asks first and does nothing when declined", async ({ context, page }) => {
  const patches: unknown[] = [];
  await adminWorkspace(context, { extra: async (route, path) => { if (route.request().method() === "PATCH" && path === `/memberships/${mika.id}`) { patches.push(route.request().postDataJSON()); await route.fulfill({ status: 200, json: { ...mika, role: "owner", version: 2 } }); return true; } return false; } });
  await page.goto(people);
  await page.getByLabel("People: Mika Member").selectOption("owner");
  const ask = page.getByRole("alertdialog");
  await expect(ask.getByRole("heading", { name: "Make Mika Member an Owner?" })).toBeVisible();
  await ask.getByRole("button", { name: "Cancel" }).click();
  expect(patches).toEqual([]);
  await page.getByLabel("People: Mika Member").selectOption("owner");
  await page.getByRole("alertdialog").getByRole("button", { name: "Make Owner" }).click();
  await expect.poll(() => patches).toEqual([{ role: "owner", expected_version: 1 }]);
});

test("the only Owner leaves by naming a successor", async ({ context, page }) => {
  const leaves: unknown[] = [];
  await context.route(`${apiBase}/api/v1/organizations`, (route) => route.fulfill({ status: 200, json: { organizations: [] } }));
  await adminWorkspace(context, { extra: async (route, path) => { if (path === `/memberships/${owner.id}/leave`) { leaves.push(route.request().postDataJSON()); await route.fulfill({ status: 204 }); return true; } return false; } });
  await page.goto(people);
  await expect(page.getByText("The only Owner: transfer ownership before leaving or stepping down.")).toBeVisible();
  await page.getByRole("button", { name: "Leave Olivia Owner" }).click();
  const dialog = page.getByRole("dialog", { name: "Leave this Organization?" });
  await expect(dialog.getByText("You are the only Owner.", { exact: false })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Transfer and leave" })).toBeDisabled();
  expect(await axe(page)).toEqual([]);
  await dialog.getByLabel("New Owner").selectOption({ label: "Mika Member (Member)" });
  await dialog.getByRole("button", { name: "Transfer and leave" }).click();
  await expect.poll(() => leaves).toEqual([{ successor_membership_id: mika.id }]);
});

test("with nobody else in the Organization, leaving points to an invitation or deletion", async ({ context, page }) => {
  const state = await adminWorkspace(context);
  state.memberships = [owner];
  await page.goto(people);
  await page.getByRole("button", { name: "Leave Olivia Owner" }).click();
  await expect(page.getByRole("dialog").getByText("You are the only person here", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Transfer and leave" })).toHaveCount(0);
});

test("ownership dialogs are in Finnish", async ({ context, page }) => {
  await adminWorkspace(context, { locale: "fi" });
  await page.goto(people);
  await page.getByRole("button", { name: "Siirrä omistajuus" }).click();
  const dialog = page.getByRole("dialog", { name: "Siirrä omistajuus" });
  await expect(dialog.getByText("Laskutusyhteyttä ei vaihdeta.", { exact: false })).toBeVisible();
  await expect(dialog.getByLabel("Pysyn omistajana")).not.toBeChecked();
});
