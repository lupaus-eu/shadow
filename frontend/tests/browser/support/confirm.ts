import { expect, type Page } from "@playwright/test";

/** Answer the confirmation dialog that replaced browser `confirm` (Yearclock V2 redesign); returns its question. */
export async function answerConfirm(page: Page, answer: "confirm" | "cancel" = "confirm"): Promise<string> {
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  const question = ((await dialog.getByRole("heading").first().textContent()) ?? "").trim();
  if (answer === "confirm") await dialog.locator("[data-confirm-action]").click();
  else await dialog.getByRole("button", { name: /^(Cancel|Peruuta)$/ }).click();
  await expect(dialog).toHaveCount(0);
  return question;
}
