import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { plannerApi, sampleEvents, yearclockPath } from "./support/yearclock-fixture";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));

const formatted = "**Deadline** 5 Nov\n\n- see [the plan](https://example.com/plan)\n- or https://example.org/other\n\n<script>window.hacked = true</script>";

function events() {
  const list = sampleEvents();
  list[0] = { ...list[0], description: formatted, description_format: "markdown" } as (typeof list)[number];
  return list;
}

test("a formatted description shows as formatting, links open safely, and markup is only text", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", events: events() });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  const details = page.getByRole("complementary", { name: "Event details" });
  await expect(details.locator("strong", { hasText: "Deadline" })).toBeVisible();
  await expect(details.locator("ul.yc-list, ul").filter({ hasText: "see the plan" }).getByRole("listitem")).toHaveCount(2);
  const plan = details.getByRole("link", { name: "the plan" });
  await expect(plan).toHaveAttribute("href", "https://example.com/plan");
  await expect(plan).toHaveAttribute("rel", "noopener noreferrer");
  await expect(plan).toHaveAttribute("target", "_blank");
  await expect(details.getByRole("link", { name: "https://example.org/other" })).toBeVisible();
  await expect(details.getByText("<script>window.hacked = true</script>")).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { hacked?: boolean }).hacked)).toBeUndefined();
});

test("new Events are formatted by default, the toolbar edits the text, and the preview shows the result", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-23" });
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: "New Event" }).click();
  const form = page.getByRole("form", { name: "New Event" });
  await form.getByLabel("Title", { exact: true }).fill("Workshop");
  await form.getByLabel("Start date").fill("2026-02-03");
  await expect(form.getByLabel("Use text formatting")).toBeChecked();
  await form.getByLabel("Description").fill("plan the day");
  await form.getByLabel("Description").selectText();
  await form.getByRole("button", { name: "Bold", exact: true }).click();
  await expect(form.getByLabel("Description")).toHaveValue("**plan the day**");
  await form.getByRole("button", { name: "Preview" }).click();
  await expect(form.getByRole("region", { name: "Preview" }).locator("strong")).toHaveText("plan the day");
  expect(await axe(page)).toEqual([]);
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
  const created = requests.find((request) => request.method === "POST" && request.path === "/events");
  expect(created?.body).toMatchObject({ title: "Workshop", description: "**plan the day**", description_format: "markdown" });
});

test("an older plain description stays literal until formatting is switched on", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-23" });
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit", exact: true }).click();
  const form = page.getByRole("form", { name: "Edit" });
  await expect(form.getByLabel("Use text formatting")).not.toBeChecked();
  await expect(form.getByRole("toolbar", { name: "Formatting" })).toHaveCount(0);
  await form.getByLabel("Use text formatting").check();
  await expect(form.getByRole("toolbar", { name: "Formatting" })).toBeVisible();
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
  expect(requests.find((request) => request.method === "PATCH")?.body).toMatchObject({ description_format: "markdown" });
});

test("the formatting controls are in Finnish", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", locale: "fi" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: "Uusi tapahtuma" }).click();
  const form = page.getByRole("form", { name: "Uusi tapahtuma" });
  await expect(form.getByLabel("Käytä tekstin muotoilua")).toBeChecked();
  await expect(form.getByRole("toolbar", { name: "Muotoilu" }).getByRole("button", { name: "Lihavointi" })).toBeVisible();
  await expect(form.getByText("Käytä **lihavointia**", { exact: false })).toBeVisible();
});
