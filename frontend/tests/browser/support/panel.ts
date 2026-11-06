import type { Page } from "@playwright/test";

/** Show a tab of the planner's side panel (Events, Details, Filters, or their Finnish names). */
export async function showTab(page: Page, name: string): Promise<void> {
  const tab = page.getByRole("tab", { name: new RegExp(`^${name}`) });
  if ((await tab.getAttribute("aria-selected")) !== "true") await tab.click();
}
