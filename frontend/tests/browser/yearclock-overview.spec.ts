import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";

const clock = (id: string, name: string) => ({ id, name, version: 1, access_role: "editor", lanes });
const clocks = [
  clock(yearclockId, "Northwind Yearclock"),
  clock("7a000000-0000-4000-8000-000000000001", "Hallituksen käsittely 2027"),
  clock("7a000000-0000-4000-8000-000000000002", "HR year"),
];

async function overviewApi(context: BrowserContext, recent: string[]) {
  const requests = await plannerApi(context, { today: "2026-09-23" });
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role: "owner" }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: clocks, recent_yearclock_ids: recent } }));
  const visits: string[] = [];
  await context.route(new RegExp(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/[^/]+/visit$`), (route) => { visits.push(new URL(route.request().url()).pathname.split("/").at(-2) ?? ""); return route.fulfill({ status: 204 }); });
  return { requests, visits };
}

test("the overview lists Yearclocks, finds them by name, and shows recently opened ones", async ({ context, page }) => {
  await overviewApi(context, [clocks[2].id, clocks[0].id]);
  await page.goto(`/organizations/${organizationId}`);
  const overview = page.getByRole("region", { name: "Open a Yearclock" });
  const recent = overview.getByRole("navigation", { name: "Recently opened" });
  await expect(recent.getByRole("link")).toHaveText(["HR year", "Northwind Yearclock"]);
  const all = overview.getByRole("list", { name: "All Yearclocks" });
  await expect(all.getByRole("link")).toHaveCount(3);
  await overview.getByLabel("Find a Yearclock").fill("KASITTELY");
  await expect(all.getByRole("link")).toHaveText(["Hallituksen käsittely 2027"]);
  await overview.getByLabel("Find a Yearclock").fill("nothing like this");
  await expect(overview.getByRole("status")).toHaveText("No Yearclock matches your search.");
  expect(await new AxeBuilder({ page }).include(".yearclock-overview").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await expect(page.getByRole("region", { name: "Events in this window" })).toHaveCount(0);
});

test("a Yearclock opens on its own page, records the visit, and links back", async ({ context, page }) => {
  const { visits } = await overviewApi(context, []);
  await page.goto(`/organizations/${organizationId}`);
  await page.getByRole("main").getByRole("link", { name: "Northwind Yearclock" }).click();
  await expect(page).toHaveURL(yearclockPath);
  await expect(page.getByRole("heading", { name: "Northwind Yearclock", level: 1 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Events in this window" })).toBeVisible();
  await expect.poll(() => [...new Set(visits)]).toEqual([yearclockId]);
  await page.getByRole("link", { name: "Back to Northwind" }).click();
  await expect(page).toHaveURL(`/organizations/${organizationId}`);
});

test("a link to a Yearclock without access shows the not-found message", async ({ context, page }) => {
  const { visits } = await overviewApi(context, []);
  await page.goto(`/organizations/${organizationId}/yearclocks/7a000000-0000-4000-8000-00000000ffff`);
  await expect(page.getByRole("alert")).toHaveText("This Yearclock does not exist or you do not have access to it.");
  await expect(page.getByRole("link", { name: "Back to Northwind" })).toBeVisible();
  expect(visits).toEqual([]);
});
