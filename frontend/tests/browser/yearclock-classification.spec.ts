import { expect, test } from "@playwright/test";

import { apiBase, categories, lanes, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";
import { answerConfirm } from "./support/confirm";

const base = `${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}`;

test("a Category colours Events on every Lane and is always named", async ({ context, page }) => {
  const events = sampleEvents();
  events.push({ id: "e8888888-0000-4000-8000-000000000000", lane_id: lanes[1].id, category_id: categories[0].id, title: "Board budget", description: null, location: null, links: [], starts_on: "2026-06-10", ends_on: null, version: 1 });
  await plannerApi(context, { today: "2026-09-23", events });
  await page.goto(yearclockPath);
  const clock = page.getByRole("group", { name: /Northwind Yearclock/ });
  const governance = clock.getByRole("button", { name: /^Board meeting, .*Governance, Board/ });
  const finance = clock.getByRole("button", { name: /^Board budget, .*Finance, Board/ });
  await expect(governance).toHaveAttribute("fill", "#336699");
  await expect(finance).toHaveAttribute("fill", "#336699");
  await showTab(page, "Filters");
  const legend = page.getByRole("region", { name: "Filters" }).getByRole("group", { name: "Categories" });
  await expect(legend.getByLabel("Board (2)")).toBeVisible();
  await expect(legend.getByLabel("Audit (1)")).toBeVisible();
  await showTab(page, "Events");
  await expect(page.getByRole("region", { name: "Events in this window" }).getByRole("button", { name: /Board budget — Finance · Board/ })).toBeVisible();
});

test("deleting a Category asks for confirmation and states the consequence", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-23" });
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  let message = "";
  await page.getByRole("button", { name: "Delete: Board" }).click();
  message = await answerConfirm(page, "cancel");
  expect(message).toBe("Delete the Category “Board”? Its Events become uncategorized.");
  expect(requests.some((request) => request.method === "DELETE")).toBe(false);
  await page.getByRole("button", { name: "Delete: Board" }).click();
  await answerConfirm(page);
  await expect.poll(() => requests.find((request) => request.method === "DELETE")?.search).toContain("confirm=true");
});

test("a Lane with Events is deleted only after moving its Events", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  let deleted = false;
  let moved: unknown = null;
  await context.route(`${base}/lanes/${lanes[1].id}**`, async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      moved = request.postDataJSON();
      await route.fulfill({ status: 200, json: { moved_events: 21, moved_series: 1, lane: { ...lanes[1], version: 2 }, target_lane: { ...lanes[0], version: 2 } } });
      return;
    }
    if (!moved) {
      await route.fulfill({ status: 409, json: { detail: { reason: "lane_has_events", events: 21, series: 1 } } });
      return;
    }
    expect(new URL(request.url()).searchParams.get("expected_version")).toBe("2");
    deleted = true;
    await route.fulfill({ status: 204, body: "" });
  });
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const lanesSection = page.getByRole("region", { name: "Lanes" });
  await lanesSection.getByRole("button", { name: "Delete: Finance" }).click();
  const move = lanesSection.getByRole("group", { name: "Move Events from Finance" });
  await expect(move.getByText("This Lane still has 21 Events and 1 recurring Series")).toBeVisible();
  await expect(move.getByLabel("Move to")).toHaveValue(lanes[0].id);
  await move.getByRole("button", { name: "Move Events and delete Lane" }).click();
  await expect.poll(() => deleted).toBe(true);
  expect(moved).toEqual({ target_lane_id: lanes[0].id, expected_version: 1 });
});
