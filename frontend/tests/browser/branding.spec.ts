import { expect, test } from "@playwright/test";

import { adminWorkspace, apiBase, organizationId } from "./support/admin-fixture";

test("the page declares the Yearclock tab icon and serves it", async ({ page, request }) => {
  await page.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 401, json: { detail: "authentication required" } }));
  await page.goto("/");
  const href = await page.locator('link[rel="icon"]').getAttribute("href");
  expect(href).toBe("/favicon.svg");
  const response = await request.get(new URL(href!, page.url()).toString());
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("svg");
});

test("the company wordmark shows small in the sign-in and sidebar footers", async ({ context, page }) => {
  await page.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 401, json: { detail: "authentication required" } }));
  await page.goto("/");
  await expect(page.getByRole("img", { name: "Lupaus" })).toHaveAttribute("src", "/lupaus-on-light.svg");
  await page.unroute(`${apiBase}/api/v1/auth/session`);
  await adminWorkspace(context);
  await page.goto(`/organizations/${organizationId}`);
  await expect(page.locator("aside").getByRole("img", { name: "Lupaus" })).toHaveAttribute("src", "/lupaus-on-dark.svg");
});
