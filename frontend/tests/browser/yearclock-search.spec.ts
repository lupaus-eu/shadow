import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, sampleEvents, yearclockId, yearclockPath } from "./support/yearclock-fixture";

const found = (index: number, title: string, startsOn: string) => ({ id: `5ea0c000-0000-4000-8000-${String(index).padStart(12, "0")}`, lane_id: lanes[0].id, category_id: null, title, description: null, location: null, links: [], starts_on: startsOn, ends_on: null, version: 1, label_ids: [] });

test("searching jumps to a result in another year and opens it", async ({ context, page }) => {
  const nextYear = found(1, "Budget approval 2027", "2027-03-15");
  await plannerApi(context, { today: "2026-09-24", events: [...sampleEvents(), nextYear] });
  const queries: string[] = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/search**`, (route) => {
    const url = new URL(route.request().url());
    queries.push(`${url.searchParams.get("q")}@${url.searchParams.get("offset")}`);
    return route.fulfill({ status: 200, json: { items: [nextYear], next_offset: null, total: 1, includes_recurring: false } });
  });
  await page.goto(yearclockPath);
  const search = page.getByRole("search", { name: "Search this Yearclock" });
  await expect(search.getByRole("button", { name: "Search" })).toBeDisabled();
  await search.getByLabel("Search text").fill("b");
  await expect(search.getByText("Type at least two characters.")).toBeVisible();
  await search.getByLabel("Search text").fill("budget");
  await search.getByLabel("Search text").press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "1 Event found." })).toBeVisible();
  expect(await new AxeBuilder({ page }).include(".yc-search").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await page.getByRole("button", { name: /15 Mar 2027 Budget approval 2027/ }).click();
  await expect(page.getByText("Showing 1 Jan 2027 to 31 Dec 2027")).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Event details" }).getByRole("heading", { name: "Budget approval 2027" })).toBeVisible();
  expect(queries).toEqual(["budget@0"]);
});

test("results load in pages, mention recurring limits, and say when nothing matches", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-24" });
  const first = Array.from({ length: 50 }, (_, index) => found(index + 1, `Weekly review ${index + 1}`, "2026-10-01"));
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/search**`, (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("q") === "nothing") return route.fulfill({ status: 200, json: { items: [], next_offset: null, total: 0, includes_recurring: false } });
    const offset = Number(url.searchParams.get("offset"));
    return route.fulfill({ status: 200, json: offset === 0 ? { items: first, next_offset: 50, total: 52, includes_recurring: true } : { items: [found(51, "Weekly review 51", "2026-10-02"), found(52, "Weekly review 52", "2026-10-03")], next_offset: null, total: 52, includes_recurring: true } });
  });
  await page.goto(yearclockPath);
  const search = page.getByRole("search", { name: "Search this Yearclock" });
  await search.getByLabel("Search text").fill("review");
  await search.getByRole("button", { name: "Search" }).click();
  const results = page.locator(".yc-search-results > li");
  await expect(results).toHaveCount(50);
  await expect(page.getByText("Recurring Events are found up to about a year ahead.")).toBeVisible();
  await page.getByRole("button", { name: "Load more" }).click();
  await expect(results).toHaveCount(52);
  await expect(page.getByRole("button", { name: "Load more" })).toHaveCount(0);
  await search.getByLabel("Search text").fill("nothing");
  await search.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("status").filter({ hasText: "No Events match." })).toBeVisible();
  await expect(results).toHaveCount(0);
});
