import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { apiBase, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";

const basePath = `/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}`;
const base = `${apiBase}${basePath}`;
const seriesId = "s1000000-0000-4000-8000-000000000001";
const team = { id: "1abe1000-0000-4000-8000-000000000001", name: "Team", color: "#1f5f99", version: 1, usage: 20 };
const board = { id: "1abe1000-0000-4000-8000-000000000002", name: "Board", color: "#2e7d32", version: 1, usage: 0 };

async function seriesApi(context: BrowserContext) {
  const events = sampleEvents().map((event) => (event.series_id ? { ...event, label_ids: [team.id] } : event));
  const requests = await plannerApi(context, { today: "2026-09-24", events });
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/labels`, (route) => route.fulfill({ status: 200, json: [board, team] }));
  const calls: Array<{ path: string; body: unknown }> = [];
  await context.route(`${base}/series/${seriesId}**`, async (route) => {
    const request = route.request();
    if (request.method() === "GET") return route.fulfill({ status: 200, json: { id: seriesId, title: "Weekly finance check", frequency: "WEEKLY", interval: 1, starts_on: "2026-01-05", effective_from: "2026-01-05", until: null, occurrence_count: null, last_day: false, rrule: "FREQ=WEEKLY;INTERVAL=1;BYDAY=MO", version: 3, label_ids: [team.id] } });
    calls.push({ path: new URL(request.url()).pathname.replace(basePath, ""), body: request.postDataJSON() });
    return route.fulfill({ status: 200, json: { id: "s2000000-0000-4000-8000-000000000002" } });
  });
  await context.route(`${base}/occurrences/**`, async (route) => {
    calls.push({ path: new URL(route.request().url()).pathname.replace(basePath, ""), body: route.request().postDataJSON() });
    return route.fulfill({ status: 200, json: {} });
  });
  return { requests, calls, events };
}

async function openOccurrence(page: Page, date: string) {
  await showTab(page, "Events");
  const summary = page.getByRole("region", { name: "Events in this window" });
  const occurrence = summary.getByRole("button", { name: new RegExp(`^${date} `) });
  if (!(await occurrence.isVisible())) await summary.getByText("Weekly finance check").first().click();
  await occurrence.click();
  return page.getByRole("complementary", { name: "Event details" });
}

test("one Occurrence overrides only its Labels", async ({ context, page }) => {
  const { calls } = await seriesApi(context);
  await page.goto(yearclockPath);
  const details = await openOccurrence(page, "2 Feb 2026");
  await expect(details.getByRole("listitem")).toHaveText(["Team"]);
  await details.getByRole("button", { name: "Edit this occurrence" }).click();
  const form = page.getByRole("form", { name: "Edit this occurrence" });
  await form.getByRole("group", { name: /Labels/ }).getByLabel("Board").check();
  await form.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => calls.find((call) => call.path.startsWith("/occurrences/"))?.body).toEqual({ label_ids: [team.id, board.id], expected_version: 1 });
});

test("this and future Occurrences send their new Labels with the split", async ({ context, page }) => {
  const { calls, events } = await seriesApi(context);
  await page.goto(yearclockPath);
  const details = await openOccurrence(page, "16 Feb 2026");
  await details.getByRole("button", { name: "Edit this and future occurrences" }).click();
  const form = page.getByRole("form", { name: "Edit this and future occurrences" });
  const picker = form.getByRole("group", { name: /Labels/ });
  await picker.getByLabel("Team").uncheck();
  await picker.getByLabel("Board").check();
  await form.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => calls.find((call) => call.path.endsWith("/split"))?.body).toEqual({
    label_ids: [board.id],
    from_occurrence_id: events.find((event) => event.series_date === "2026-02-16")!.occurrence_id,
    expected_version: 3,
  });
});

test("a new Series is created with its Labels", async ({ context, page }) => {
  const { requests } = await seriesApi(context);
  await page.goto(yearclockPath);
  await page.getByRole("button", { name: "New Event" }).click();
  const form = page.getByRole("form", { name: "New Event" });
  await form.getByLabel("Title").fill("Monthly board pack");
  await form.getByLabel("Start date").fill("2026-10-05");
  await form.getByRole("group", { name: "Repeat" }).getByRole("combobox").first().selectOption("MONTHLY");
  await form.getByRole("group", { name: /Labels/ }).getByLabel("Board").check();
  await form.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => requests.find((request) => request.method === "POST" && request.path === "/series")?.body).toMatchObject({ title: "Monthly board pack", frequency: "MONTHLY", label_ids: [board.id] });
});
