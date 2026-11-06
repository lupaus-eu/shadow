import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext } from "@playwright/test";

import { apiBase, lanes, organizationId, plannerApi, yearclockId, yearclockPath } from "./support/yearclock-fixture";

async function workspace(context: BrowserContext, role: "owner" | "member" = "owner") {
  await plannerApi(context, { today: "2026-09-25", role, accessRole: role === "member" ? "viewer" : "editor" });
  const styled = [{ ...lanes[0], tint: "#1f5f99", height: "tall" }, { ...lanes[1] }];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}`, (route) => route.fulfill({ status: 200, json: { organization: { id: organizationId, name: "Northwind", time_zone: "Europe/Helsinki" }, membership: { role }, subscription: { state: "active", writable: true, grace_expires_at: null, cancel_at_period_end: false, current_period_end: null }, yearclocks: [{ id: yearclockId, name: "Northwind Yearclock", version: 1, access_role: role === "member" ? "viewer" : "editor", lanes: styled }] } }));
}

test("a tall, tinted Lane is drawn wider with a light band and markers keep their colours", async ({ context, page }) => {
  await workspace(context, "member");
  await page.goto(yearclockPath);
  const tint = page.locator(".yc-lane-tint");
  await expect(tint).toHaveCount(1);
  await expect(tint).toHaveAttribute("stroke", "#1f5f99");
  // Two Lanes share the 108-unit ring; the tall one weighs 2, so its band is 72 units wide.
  expect(Number(await tint.getAttribute("stroke-width"))).toBeCloseTo(72, 1);
  await expect(page.getByRole("button", { name: /^Board meeting,/ })).toHaveAttribute("fill", "#336699");
  expect(await new AxeBuilder({ page }).include(".yc-planner").withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id))).toEqual([]);
  await expect(page.getByRole("link", { name: "Yearclock settings" })).toHaveCount(0);
});

test("Editors set a Lane's tint and height", async ({ context, page }) => {
  await workspace(context);
  const bodies: unknown[] = [];
  await context.route(`${apiBase}/api/v1/organizations/${organizationId}/yearclocks/${yearclockId}/lanes/${lanes[1].id}`, (route) => { bodies.push(route.request().postDataJSON()); return route.fulfill({ status: 200, json: { ...lanes[1], version: 2, tint: "#2e7d32", height: "tall" } }); });
  await page.goto(yearclockPath);
  await page.getByRole("link", { name: "Yearclock settings" }).click();
  const lanesSection = page.getByRole("region", { name: "Lanes" });
  await lanesSection.getByLabel(`Tint: ${lanes[1].name}`).selectOption({ label: "Green" });
  await lanesSection.getByLabel(`Height: ${lanes[1].name}`).selectOption("tall");
  await lanesSection.getByRole("listitem").nth(1).getByRole("button", { name: "Save" }).click();
  await expect.poll(() => bodies).toEqual([{ name: lanes[1].name, tint: "#2e7d32", height: "tall", expected_version: lanes[1].version }]);
});
