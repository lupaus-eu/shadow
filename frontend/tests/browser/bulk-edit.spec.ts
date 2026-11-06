import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";
import { answerConfirm } from "./support/confirm";

const decision = { id: "1abe1000-0000-4000-8000-000000000001", name: "Decision needed", color: "#c62828", version: 1, usage: 0 };
type Row = ReturnType<typeof sampleEvents>[number] & { label_ids?: string[] };

async function openPlanner(context: BrowserContext, page: Page, respond?: (body: Record<string, unknown>) => { status: number; json: unknown } | null) {
  const events: Row[] = sampleEvents();
  await plannerApi(context, { today: "2026-09-25", events });
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/labels`, (route) => route.fulfill({ status: 200, json: [decision] }));
  const bodies: Array<Record<string, unknown>> = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events/bulk`, (route) => {
    const body = route.request().postDataJSON();
    bodies.push(body);
    const override = respond?.(body);
    if (override) return route.fulfill(override);
    const ids = (body.items as Array<{ id: string }>).map((item) => item.id);
    for (const event of events.filter((item) => ids.includes(item.id))) {
      if (body.action === "move") event.lane_id = body.lane_id;
      if (body.action === "label") event.label_ids = [...new Set([...(event.label_ids ?? []), ...(body.add_label_ids ?? [])])].filter((id) => !(body.remove_label_ids ?? []).includes(id));
      event.version += 1;
    }
    if (body.action === "delete") events.splice(0, events.length, ...events.filter((item) => !ids.includes(item.id)));
    return route.fulfill({ status: 200, json: { bulk_id: "b1", changed: ids.length, items: [] } });
  });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  return { events, bodies, bulk: page.getByRole("region", { name: "Select Events" }), summary: page.getByRole("region", { name: "Events in this window" }) };
}

test("Editors select the Events the filters show and move them in one confirmed step", async ({ context, page }) => {
  const { bodies, bulk, summary } = await openPlanner(context, page);
  await expect(summary.getByRole("checkbox")).toHaveCount(0);
  await bulk.getByRole("button", { name: "Select Events" }).click();
  await expect(bulk.getByRole("button", { name: "Select Events" })).toHaveAttribute("aria-pressed", "true");
  await expect(bulk.getByText("Recurring occurrences cannot be selected; change them through their Series. Events of Linked Lanes are changed in their own Yearclock.")).toBeVisible();
  await showTab(page, "Filters");
  await page.getByRole("region", { name: "Filters" }).getByRole("group", { name: "Lanes" }).getByLabel(/Governance \(/).check();
  await showTab(page, "Events");
  await bulk.getByRole("button", { name: "Select all shown" }).click();
  await expect(bulk.getByRole("status")).toHaveText("2 Events selected");
  await expect(summary.getByRole("checkbox", { name: /^Select Board meeting,/ })).toBeChecked();
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);

  const dialogs: string[] = [];
  await bulk.getByLabel("Move to Lane").selectOption({ label: "Finance" });
  await bulk.getByRole("button", { name: "Move", exact: true }).click();
  dialogs.push(await answerConfirm(page));
  await expect(page.getByRole("status").filter({ hasText: "2 Events changed." })).toBeVisible();
  expect(dialogs).toEqual(["Change 2 Events?"]);
  expect(bodies[0]).toMatchObject({ action: "move", lane_id: lanes[1].id });
  expect((bodies[0].items as Array<{ expected_version: number }>).map((item) => item.expected_version)).toEqual([1, 1]);
});

test("occurrences cannot be selected, Labels are added, and deleting asks first", async ({ context, page }) => {
  const { bodies, bulk, summary } = await openPlanner(context, page);
  await bulk.getByRole("button", { name: "Select Events" }).click();
  await summary.getByText(/Weekly finance check/).first().click();
  const occurrence = summary.getByRole("checkbox", { name: /^Select Weekly finance check,/ }).first();
  await expect(occurrence).toBeDisabled();
  await expect(occurrence).toHaveAccessibleDescription("Recurring occurrences cannot be selected; change them through their Series. Events of Linked Lanes are changed in their own Yearclock.");

  const board = summary.getByRole("checkbox", { name: /^Select Board meeting,/ });
  await board.focus();
  await page.keyboard.press("Space");
  await expect(board).toBeChecked();
  await bulk.getByRole("button", { name: "Add Label" }).click();
  await answerConfirm(page);
  await expect.poll(() => bodies.length).toBe(1);
  expect(bodies[0]).toMatchObject({ action: "label", add_label_ids: [decision.id] });

  await bulk.getByRole("button", { name: "Delete selected" }).click();
  expect(await answerConfirm(page, "cancel")).toBe("Delete 1 Event? You can restore it for 30 days.");
  expect(bodies).toHaveLength(1);
  await bulk.getByRole("button", { name: "Delete selected" }).click();
  await answerConfirm(page);
  await expect(summary.getByRole("checkbox", { name: /^Select Board meeting,/ })).toHaveCount(0);
  await expect(bulk.getByRole("status")).toHaveText("0 Events selected");
});

test("a stale selection or too many Events saves nothing and explains why", async ({ context, page }) => {
  let reply: { status: number; json: unknown } = { status: 409, json: { detail: { reason: "stale", ids: [] } } };
  const { bulk, summary } = await openPlanner(context, page, () => reply);
  await bulk.getByRole("button", { name: "Select Events" }).click();
  await summary.getByRole("checkbox", { name: /^Select Audit period,/ }).check();
  await bulk.getByRole("button", { name: "Apply Category" }).click();
  await answerConfirm(page);
  await expect(page.getByRole("alert")).toHaveText("Some selected Events were changed by someone else, so nothing was saved. The latest versions are shown; review the selection and try again.");
  reply = { status: 409, json: { detail: { reason: "limit_reached", limit: "bulk_events", maximum: 200 } } };
  await bulk.getByRole("button", { name: "Delete selected" }).click();
  await answerConfirm(page);
  await expect(page.getByRole("alert")).toHaveText("At most 200 Events can be changed at once. Select fewer Events.");
});

test("Viewers have no selection mode", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-25" });
  await page.goto(yearclockPath);
  await expect(page.getByRole("heading", { name: "Events in this window" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Select Events" })).toHaveCount(0);
});
