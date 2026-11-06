import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { apiBase, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";

const eventsUrl = `${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/events`;

async function openBoardMeeting(page: Page, summaryName = "Events in this window") {
  if (await page.getByRole("tab", { selected: true }).count()) await showTab(page, summaryName === "Events in this window" ? "Events" : "Tapahtumat");
  await page.getByRole("region", { name: summaryName }).getByRole("button", { name: /Board meeting/ }).click();
}

test("descriptions keep line breaks and show markup literally (story 67)", async ({ context, page }) => {
  const events = sampleEvents();
  events[0] = { ...events[0], description: "First line\nSecond line\n<b>not bold</b> **not bold** [label](https://example.com/x)" };
  await plannerApi(context, { today: "2026-09-23", events });
  await page.goto(yearclockPath);
  await openBoardMeeting(page);
  const description = page.getByRole("complementary", { name: "Event details" }).locator(".yc-description");
  await expect(description).toContainText("<b>not bold</b> **not bold** [label](");
  expect(await description.evaluate((node) => node.querySelectorAll("b, strong, em").length)).toBe(0);
  expect(await description.evaluate((node) => (node as HTMLElement).innerText.split("\n").length)).toBeGreaterThanOrEqual(3);
  await expect(description.getByRole("link")).toHaveAttribute("href", "https://example.com/x");
  await expect(description).toContainText("[label](https://example.com/x)");
});

test("Cancel discards edits without sending anything (story 103)", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await openBoardMeeting(page);
  await page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit" }).click();
  const form = page.getByRole("form", { name: "Edit" });
  await form.getByLabel("Title").fill("Changed but cancelled");
  await form.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("form", { name: "Edit" })).toHaveCount(0);
  await expect(page.getByText("Changed but cancelled")).toHaveCount(0);
  await openBoardMeeting(page);
  await expect(page.getByRole("complementary", { name: "Event details" }).getByRole("heading", { name: "Board meeting" })).toBeVisible();
  expect(requests.filter((request) => request.method !== "GET")).toEqual([]);
});

test("a stale save shows the latest version for review (story 71)", async ({ context, page }) => {
  const events = sampleEvents();
  let conflicted = false;
  await plannerApi(context, { today: "2026-09-23", events });
  await context.route(`${eventsUrl}**`, async (route) => {
    const request = route.request();
    if (request.method() === "PATCH") {
      conflicted = true;
      return route.fulfill({ status: 409, json: { detail: { latest_version: 2 } } });
    }
    if (request.method() === "GET" && conflicted && new URL(request.url()).pathname.endsWith("/events")) {
      return route.fulfill({ status: 200, json: events.map((event, index) => (index === 0 ? { ...event, title: "Board meeting (moved by a colleague)", starts_on: "2026-03-12", version: 2 } : event)) });
    }
    return route.fallback();
  });
  await page.goto(yearclockPath);
  await openBoardMeeting(page);
  await page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit" }).click();
  const form = page.getByRole("form", { name: "Edit" });
  await form.getByLabel("Title").fill("My stale change");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Someone else changed this Event" })).toBeVisible();
  await expect(form.getByLabel("Title")).toHaveValue("Board meeting (moved by a colleague)");
  await expect(form.getByLabel("Start date")).toHaveValue("2026-03-12");
});

test("the Finnish interface translates the product but never customer content (stories 104, 107)", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", locale: "fi" });
  await page.goto(yearclockPath);
  const summary = page.getByRole("region", { name: "Tapahtumat tällä jaksolla" });
  await expect(summary).toBeVisible();
  await expect(page.getByRole("link", { name: "Takaisin: Northwind" })).toBeVisible();
  await expect(summary.getByRole("button", { name: /Board meeting/ })).toBeVisible();
  await expect(summary.getByRole("button", { name: /Audit period/ })).toBeVisible();
  await openBoardMeeting(page, "Tapahtumat tällä jaksolla");
  const details = page.getByRole("complementary", { name: "Tapahtuman tiedot" });
  await expect(details.getByRole("heading", { name: "Board meeting" })).toBeVisible();
  await expect(details.getByText("Budget approval")).toBeVisible();
  await expect(details.getByRole("button", { name: "Muokkaa" })).toBeVisible();
  for (const english of ["Events in this window", "Event details", "Previous period", "New Event", "Activity", "People"]) {
    await expect(page.getByText(english, { exact: true })).toHaveCount(0);
  }
  expect(await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
});

for (const timezoneId of ["America/Los_Angeles", "Pacific/Kiritimati"]) {
  test.describe(`in ${timezoneId}`, () => {
    test.use({ timezoneId });
    test("Event dates stay the same all-day dates (story 108)", async ({ context, page }) => {
      await plannerApi(context, { today: "2026-09-23" });
      await page.goto(yearclockPath);
      const summary = page.getByRole("region", { name: "Events in this window" });
      await expect(summary.getByRole("button", { name: /10 Mar 2026 Board meeting/ })).toBeVisible();
      await expect(summary.getByRole("button", { name: /1 Apr 2026 – 15 May 2026 Audit period/ })).toBeVisible();
      await openBoardMeeting(page);
      await page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit" }).click();
      await expect(page.getByRole("form", { name: "Edit" }).getByLabel("Start date")).toHaveValue("2026-03-10");
    });
  });
}

test("an invited person accepts the Invitation and opens the Organization (T2)", async ({ context, page }) => {
  await plannerApi(context, { role: "member", accessRole: "viewer", today: "2026-09-23" });
  let token: string | null = null;
  await context.route(`${apiBase}/api/v1/organizations`, (route) => route.fulfill({ status: 200, json: { organizations: token ? [{ id: organizationId, name: "Northwind", role: "member", status: "active", purge_after: null }] : [] } }));
  await context.route(`${apiBase}/api/v1/invitations/accept`, (route) => {
    token = route.request().postDataJSON().token;
    return route.fulfill({ status: 200, json: { id: "i1", organization_id: organizationId, email: "owner@example.com", role: "member", status: "accepted", expires_at: "2026-09-30T00:00:00Z", version: 2 } });
  });
  await page.goto("/invitations/abcDEF123_-token");
  await expect(page.getByRole("heading", { name: "Organization invitation" })).toBeVisible();
  await page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(page.getByRole("heading", { name: "Invitation accepted" })).toBeVisible();
  expect(token).toBe("abcDEF123_-token");
  await page.getByRole("link", { name: "Open Yearclock" }).click();
  await expect(page.getByRole("heading", { name: "Northwind", exact: true })).toBeVisible();
});

test("a rejected Invitation explains why (T2)", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await context.route(`${apiBase}/api/v1/invitations/accept`, (route) => route.fulfill({ status: 404, json: { detail: "invitation not found" } }));
  await page.goto("/invitations/expired-token");
  await page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(page.getByRole("alert")).toHaveText(/may be expired, revoked, or addressed to a different email/);
});
