import { expect, test } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";
import { answerConfirm } from "./support/confirm";

const basePath = `/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}`;
const base = `${apiBase}${basePath}`;
const seriesId = "s1000000-0000-4000-8000-000000000001";

async function openOccurrence(page: import("@playwright/test").Page, date: string) {
  await showTab(page, "Events");
  const summary = page.getByRole("region", { name: "Events in this window" });
  const occurrence = summary.getByRole("button", { name: new RegExp(`^${date} `) });
  if (!(await occurrence.isVisible())) await summary.getByText("Weekly finance check").first().click();
  await occurrence.click();
  return page.getByRole("complementary", { name: "Event details" });
}

test("an Editor edits one Occurrence, this and future Occurrences, skips, and ends the Series", async ({ context, page }) => {
  const events = sampleEvents();
  const requests = await plannerApi(context, { today: "2026-09-23", events });
  const calls: Array<{ path: string; body: unknown }> = [];
  await context.route(`${base}/series/${seriesId}**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(basePath, "");
    if (request.method() === "GET") return route.fulfill({ status: 200, json: { id: seriesId, title: "Weekly finance check", frequency: "WEEKLY", interval: 1, starts_on: "2026-01-05", effective_from: "2026-01-05", until: null, occurrence_count: null, last_day: false, rrule: "FREQ=WEEKLY;INTERVAL=1;BYDAY=MO", version: 3 } });
    calls.push({ path, body: request.postDataJSON() });
    return route.fulfill({ status: 200, json: path.endsWith("/end") ? { series: {}, removed_occurrences: 12 } : { id: "s2000000-0000-4000-8000-000000000002" } });
  });
  await context.route(`${base}/occurrences/**`, async (route) => {
    const request = route.request();
    calls.push({ path: new URL(request.url()).pathname.replace(basePath, "") + new URL(request.url()).search, body: request.postData() ? request.postDataJSON() : null });
    return route.fulfill({ status: 200, json: {} });
  });
  await page.goto(yearclockPath);

  let details = await openOccurrence(page, "2 Feb 2026");
  await expect(details.getByText(/Series date 2 Feb 2026/)).toBeVisible();
  await details.getByRole("button", { name: "Edit this occurrence" }).click();
  let form = page.getByRole("form", { name: "Edit this occurrence" });
  await expect(form.getByText("Only the fields you change here stop following the Series.")).toBeVisible();
  await form.getByLabel("Title").fill("Finance check with auditors");
  await form.getByLabel("Start date").fill("2026-02-04");
  await form.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => calls.find((call) => call.path.startsWith("/occurrences/") && (call.body as { title?: string } | null)?.title)?.body).toEqual({ title: "Finance check with auditors", starts_on: "2026-02-04", expected_version: 1 });

  details = await openOccurrence(page, "16 Feb 2026");
  await details.getByRole("button", { name: "Edit this and future occurrences" }).click();
  form = page.getByRole("form", { name: "Edit this and future occurrences" });
  await expect(form.getByText(/Changes apply from 16 Feb 2026 onward/)).toBeVisible();
  await expect(form.getByLabel("Start date")).toHaveCount(0);
  await form.getByLabel("Description").fill("Use the new template");
  await form.getByLabel("Lane").selectOption(lanes[0].id);
  await form.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => calls.find((call) => call.path.endsWith("/split"))?.body).toEqual({
    description: "Use the new template",
    lane_id: lanes[0].id,
    from_occurrence_id: events.find((event) => event.series_date === "2026-02-16")!.occurrence_id,
    expected_version: 3,
  });

  details = await openOccurrence(page, "2 Mar 2026");
  await details.getByRole("button", { name: "Skip occurrence" }).click();
  await expect.poll(() => calls.some((call) => call.path.includes("/skip"))).toBe(true);

  details = await openOccurrence(page, "9 Mar 2026");
  await details.getByRole("button", { name: "End Series from here" }).click();
  await answerConfirm(page);
  await expect.poll(() => calls.find((call) => call.path.endsWith("/end"))?.body).toEqual({
    from_occurrence_id: events.find((event) => event.series_date === "2026-03-09")!.occurrence_id,
    expected_version: 3,
  });
  await expect(page.getByText("Series ended. Earlier Occurrences remain.")).toBeVisible();
  expect(requests.filter((request) => request.method === "DELETE")).toEqual([]);
});

test("a Skipped Occurrence can be restored and a changed one restored to Series values", async ({ context, page }) => {
  const events = sampleEvents();
  const skipped = events.find((event) => event.series_date === "2026-03-02")!;
  skipped.skipped = true;
  const changed = events.find((event) => event.exception)!;
  await plannerApi(context, { today: "2026-09-23", events });
  const calls: string[] = [];
  await context.route(`${base}/occurrences/**`, (route) => {
    const url = new URL(route.request().url());
    calls.push(url.pathname.replace(basePath, "") + url.search);
    return route.fulfill({ status: 200, json: {} });
  });
  await page.goto(yearclockPath);
  const skippedList = page.getByRole("region", { name: "Skipped occurrences" });
  await expect(skippedList.getByText(/2 Mar 2026 — Weekly finance check/)).toBeVisible();
  await skippedList.getByRole("button", { name: "Restore" }).click();
  await expect.poll(() => calls).toContain(`/occurrences/${skipped.occurrence_id}/skip?skipped=false`);

  const summary = page.getByRole("region", { name: "Events in this window" });
  await summary.getByText("Weekly finance check").first().click();
  await summary.getByRole("button", { name: /Finance check \(moved\)/ }).click();
  const details = page.getByRole("complementary", { name: "Event details" });
  await expect(details.getByText(/changed occurrence/)).toBeVisible();
  await details.getByRole("button", { name: "Restore Series values" }).click();
  await expect.poll(() => calls).toContain(`/occurrences/${changed.occurrence_id}/restore?expected_version=1`);
});
