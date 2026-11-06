import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { apiBase } from "./support/admin-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));
const base = `${apiBase}/api/v1/legal/documents`;

const summaries = {
  en: [
    { key: "terms", title: "Terms of service", version: 2, effective_from: "2026-12-01", status: "published", acceptance: "required" },
    { key: "subprocessors", title: "Sub-processors", version: 1, effective_from: "2026-12-01", status: "draft", acceptance: "notice" },
  ],
  fi: [
    { key: "terms", title: "Palveluehdot", version: 2, effective_from: "2026-12-01", status: "published", acceptance: "required" },
    { key: "subprocessors", title: "Alikäsittelijät", version: 1, effective_from: "2026-12-01", status: "draft", acceptance: "notice" },
  ],
};
const bodies: Record<string, string> = {
  terms: "Intro text.\n\n## Scope\n\nSee [the privacy notice](/legal/privacy).\n\n| Name | Country |\n| --- | --- |\n| Scaleway | France |\n\n<script>window.injected = true</script>",
  subprocessors: "Placeholder list.",
};

async function serve(context: BrowserContext) {
  await context.route(new RegExp(`${base}(/.*)?(\\?.*)?$`), (route) => {
    const url = new URL(route.request().url());
    const locale = (url.searchParams.get("locale") ?? "en") as "en" | "fi";
    const key = url.pathname.split("/").pop();
    if (key === "documents") return route.fulfill({ status: 200, json: summaries[locale] });
    const item = summaries[locale].find((entry) => entry.key === key);
    if (!item) return route.fulfill({ status: 404, json: { detail: "document not found" } });
    return route.fulfill({ status: 200, json: { ...item, body: bodies[item.key] } });
  });
  await context.route(`${apiBase}/api/v1/auth/session`, (route) => route.fulfill({ status: 401, json: { detail: "authentication required" } }));
}

test("a signed-out visitor reads the documents in both languages", async ({ context, page }) => {
  await serve(context);
  await page.goto("/legal");
  await expect(page.getByRole("heading", { name: "Terms, privacy, and security", level: 1 })).toBeVisible();
  await expect(page.getByText("Version 2, in force from 2026-12-01")).toBeVisible();
  expect(await axe(page)).toEqual([]);

  await page.getByRole("link", { name: "Terms of service" }).click();
  await expect(page.getByRole("heading", { name: "Terms of service", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Scope", level: 2 })).toBeVisible();
  await expect(page.getByRole("link", { name: "the privacy notice" })).toHaveAttribute("href", "/legal/privacy");
  await expect(page.getByRole("table")).toContainText("Scaleway");
  expect(await page.evaluate(() => (window as unknown as { injected?: boolean }).injected)).toBeUndefined();
  expect(await axe(page)).toEqual([]);

  await page.getByRole("radio", { name: "Suomi" }).click();
  await expect(page.getByRole("heading", { name: "Palveluehdot", level: 1 })).toBeVisible();
  await expect(page.getByText("Versio 2, voimassa 2026-12-01 alkaen")).toBeVisible();
});

test("a draft shows the banner, and an unknown document says so", async ({ context, page }) => {
  await serve(context);
  await page.goto("/legal/subprocessors");
  await expect(page.getByText("Draft, not in force.", { exact: false })).toBeVisible();
  await page.goto("/legal/unknown");
  await expect(page.getByRole("heading", { name: "This document does not exist." })).toBeVisible();
});

test("the sign-in page links to the legal documents", async ({ context, page }) => {
  await serve(context);
  await page.goto("/");
  await page.getByRole("link", { name: "Terms and privacy" }).click();
  await expect(page).toHaveURL(/\/legal$/);
});
