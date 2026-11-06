import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext } from "@playwright/test";

import { apiBase, organizationId, plannerApi, sampleEvents, yearclockPath } from "./support/yearclock-fixture";

type Label = { id: string; name: string; color: string; version: number; usage: number };
const label = (index: number, name: string): Label => ({ id: `1abe1000-0000-4000-8000-${String(index).padStart(12, "0")}`, name, color: "#1f5f99", version: 1, usage: 0 });

async function labelsApi(context: BrowserContext, initial: Label[]) {
  const labels = [...initial];
  const created: string[] = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/labels`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ status: 200, json: labels });
    const body = route.request().postDataJSON();
    const item = label(900 + labels.length, body.name);
    labels.push(item);
    created.push(body.name);
    return route.fulfill({ status: 201, json: item });
  });
  return created;
}

test("an Editor labels an Event with an existing and a newly created Label", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-24", events: [] });
  const created = await labelsApi(context, [label(1, "Budget"), label(2, "Decision needed")]);
  await page.goto(yearclockPath);
  await page.getByRole("button", { name: "New Event" }).click();
  const form = page.getByRole("form", { name: "New Event" });
  await form.getByLabel("Title").fill("Budget review");
  await form.getByLabel("Start date").fill("2026-10-01");
  const picker = form.getByRole("group", { name: /Labels/ });
  await picker.getByLabel("Decision needed").check();
  await picker.getByLabel("Find or create a Label").fill("Finance team");
  await expect(picker.getByLabel("Budget")).toHaveCount(0);
  await expect(picker.getByText("New Label names are visible to everyone in the Organization.")).toBeVisible();
  await picker.getByLabel("Find or create a Label").press("Enter");
  await expect(picker.getByLabel("Finance team")).toBeChecked();
  await expect(picker.getByText("2 of 10 selected")).toBeVisible();
  expect(await new AxeBuilder({ page }).include(".yc-label-picker").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
  const post = requests.find((request) => request.method === "POST" && request.path === "/events");
  expect(created).toEqual(["Finance team"]);
  expect(post?.body).toMatchObject({ title: "Budget review", label_ids: [label(2, "").id, label(902, "").id] });
});

test("Labels show in details, the summary, and the accessible name, and a Viewer cannot change them", async ({ context, page }) => {
  const events = sampleEvents();
  events[0] = { ...events[0], label_ids: [label(1, "").id, label(2, "").id] };
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-24", events });
  await labelsApi(context, [label(1, "Budget"), label(2, "Decision needed")]);
  await page.goto(yearclockPath);
  await expect(page.getByRole("button", { name: /^Board meeting, 10 Mar 2026, .*Labels: Budget, Decision needed/ })).toBeVisible();
  const summary = page.getByRole("region", { name: "Events in this window" });
  await expect(summary.getByRole("button", { name: /Board meeting/ })).toContainText("Budget");
  await summary.getByRole("button", { name: /Board meeting/ }).click();
  const details = page.getByRole("complementary", { name: "Event details" });
  await expect(details.locator(".yc-label-list").getByRole("listitem")).toHaveText(["Budget", "Decision needed"]);
  await expect(details.getByRole("button", { name: "Edit" })).toHaveCount(0);
});

test("the picker stops at ten Labels", async ({ context, page }) => {
  const labels = Array.from({ length: 11 }, (_, index) => label(index + 1, `Label ${String(index + 1).padStart(2, "0")}`));
  const events = sampleEvents();
  events[0] = { ...events[0], label_ids: labels.slice(0, 10).map((item) => item.id) };
  await plannerApi(context, { today: "2026-09-24", events });
  await labelsApi(context, labels);
  await page.goto(yearclockPath);
  await page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board meeting/ }).click();
  await page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit" }).click();
  const picker = page.getByRole("form", { name: "Edit" }).getByRole("group", { name: /Labels/ });
  await expect(picker.getByText("An Event can have at most 10 Labels.")).toBeVisible();
  await expect(picker.getByLabel("Label 11")).toBeDisabled();
  await picker.getByLabel("Label 01").uncheck();
  await expect(picker.getByLabel("Label 11")).toBeEnabled();
});
