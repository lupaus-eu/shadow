import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { apiBase, categories, lanes, organizationId, plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";

test("an Editor previews a season and creates its copies a year later", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-25" });
  const bodies: Array<Record<string, unknown>> = [];
  let created = false;
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/plan-again`, (route) => {
    const body = route.request().postDataJSON();
    bodies.push(body);
    if (!body.dry_run) created = true;
    return route.fulfill({ status: 200, json: created && !body.dry_run ? { to_create: 3, skipped_existing: 1, limit_exceeded: false, maximum: 3000, created_ids: ["a", "b", "c"] } : { to_create: created ? 0 : 3, skipped_existing: created ? 4 : 1, limit_exceeded: false, maximum: 3000, created_ids: [] } });
  });
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const panel = page.getByRole("region", { name: "Plan a season again" });
  await expect(panel.getByLabel("Season to copy")).toHaveValue("2026-01-01");
  await expect(panel.getByLabel("Season to copy").locator("option")).toHaveText(["1 Jan 2025 – 31 Dec 2025", "1 Jan 2026 – 31 Dec 2026", "1 Jan 2027 – 31 Dec 2027"]);
  await panel.getByRole("group", { name: "Lanes to include" }).getByLabel("Finance").uncheck();
  await panel.getByRole("group", { name: "Categories to include" }).getByLabel("Audit").uncheck();
  await panel.getByLabel("Same weekday").check();
  await panel.getByRole("button", { name: "Preview" }).click();
  await expect(panel.getByRole("status")).toContainText("3 Events will be created between 1 Jan 2027 and 31 Dec 2027. 1 already exists and will be skipped.");
  expect(bodies[0]).toEqual({ season_start: "2026-01-01", lane_ids: [lanes[0].id], category_ids: [categories[0].id], include_uncategorized: true, date_rule: "same_weekday", dry_run: true });
  expect(await new AxeBuilder({ page }).include(".yc-structure").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);

  await panel.getByRole("button", { name: "Create 3 Events" }).click();
  await expect(panel.getByRole("status")).toHaveText("3 Events created.");
  expect(bodies[1]).toMatchObject({ dry_run: false, date_rule: "same_weekday" });
  await panel.getByRole("button", { name: "Preview" }).click();
  await expect(panel.getByRole("status")).toHaveText("There is nothing new to create: all 4 matching Events already exist.");
  await expect(panel.getByRole("button", { name: /^Create/ })).toHaveCount(0);

  await panel.getByLabel("Same date").check();
  await expect(panel.getByRole("status")).toHaveCount(0);
});

test("the preview names the Event limit and offers no creation", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-25", locale: "fi" });
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/plan-again`, (route) => route.fulfill({ status: 200, json: { to_create: 40, skipped_existing: 0, limit_exceeded: true, maximum: 3000, created_ids: [] } }));
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Vuosikellon asetukset" }).click();
  const panel = page.getByRole("region", { name: "Suunnittele kausi uudelleen" });
  await panel.getByRole("button", { name: "Esikatsele" }).click();
  await expect(panel.getByRole("status")).toHaveText(/ylittäisi vuosikellon 3000 tapahtuman rajan/);
  await expect(panel.getByRole("button", { name: /^Luo/ })).toHaveCount(0);
});
