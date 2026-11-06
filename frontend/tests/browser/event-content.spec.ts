import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { categories, lanes, plannerApi, yearclockPath } from "./support/yearclock-fixture";
import { showTab } from "./support/panel";

const axe = (page: Page) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze().then((result) => result.violations.map((violation) => violation.id));

async function openEditor(page: Page) {
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await page.getByRole("complementary", { name: "Event details" }).getByRole("button", { name: "Edit", exact: true }).click();
  return page.getByRole("form", { name: "Edit" });
}

test("the editor lists links with their titles, adds, reorders, and removes them, and saves the list", async ({ context, page }) => {
  const requests = await plannerApi(context, { today: "2026-09-23" });
  await page.setViewportSize({ width: 1280, height: 1000 });
  const form = await openEditor(page);
  await expect(form.getByLabel("Location")).toHaveValue("Room 4");
  await expect(form.getByRole("group", { name: "Link 1" }).getByLabel("Link text")).toHaveValue("Board page");
  await form.getByRole("button", { name: "Add link" }).click();
  const second = form.getByRole("group", { name: "Link 2" });
  await second.getByLabel("Link text").fill("Slides");
  await second.getByLabel("Address").fill("https://example.com/slides");
  await form.getByRole("button", { name: "Move link 2 up" }).click();
  await expect(form.getByRole("group", { name: "Link 1" }).getByLabel("Link text")).toHaveValue("Slides");
  await expect(form.getByRole("button", { name: "Move link 1 up" })).toBeDisabled();
  expect(await axe(page)).toEqual([]);
  await form.getByRole("button", { name: "Remove link 2" }).click();
  await form.getByRole("button", { name: "Add link" }).click();
  await form.getByRole("group", { name: "Link 2" }).getByLabel("Link text").fill("Again");
  await form.getByRole("group", { name: "Link 2" }).getByLabel("Address").fill("https://example.com/slides");
  await expect(form.getByText("Link 2 repeats an address that is already listed.")).toBeVisible();
  await expect(form.getByRole("button", { name: "Save" })).toBeDisabled();
  await form.getByRole("group", { name: "Link 2" }).getByLabel("Address").fill("https://example.com/other");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.", { exact: true })).toBeVisible();
  const saved = requests.find((request) => request.method === "PATCH");
  expect(saved?.body).toMatchObject({ location: "Room 4", links: [{ title: "Slides", url: "https://example.com/slides" }, { title: "Again", url: "https://example.com/other" }] });
});

test("an Event can have at most ten links", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.setViewportSize({ width: 1280, height: 1400 });
  const form = await openEditor(page);
  for (let index = 0; index < 9; index += 1) await form.getByRole("button", { name: "Add link" }).click();
  await expect(form.getByRole("button", { name: "Add link" })).toBeDisabled();
});

test("location and links show in the list, the agenda, the panel, and the print list", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23" });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("radio", { name: "List" }).check();
  await expect(page.getByRole("table").getByText("Room 4", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "Agenda" }).check();
  await expect(page.getByText(/· Room 4/)).toBeVisible();
  await page.getByRole("radio", { name: "Circle" }).check();
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".yc-print-events").getByText("Room 4")).toBeVisible();
  await expect(page.locator(".yc-print-events").getByText("Board page: https://example.com/board")).toBeVisible();
});

test("the editor is in Finnish", async ({ context, page }) => {
  await plannerApi(context, { today: "2026-09-23", locale: "fi" });
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.goto(`${yearclockPath}?window_start=2026-01-01`);
  await page.getByRole("button", { name: /^Board meeting,/ }).click();
  await page.getByRole("complementary", { name: "Tapahtuman tiedot" }).getByRole("button", { name: "Muokkaa", exact: true }).click();
  const form = page.getByRole("form", { name: "Muokkaa" });
  await expect(form.getByLabel("Sijainti")).toHaveValue("Room 4");
  await expect(form.getByRole("button", { name: "Lisää linkki" })).toBeVisible();
  await expect(form.getByRole("group", { name: "Linkki 1" }).getByLabel("Linkin teksti")).toHaveValue("Board page");
});
