import { expect, test } from "@playwright/test";

const session = {
  user_account: {
    id: "fc4dbf31-2fd3-43cf-bc95-96642b93b9eb",
    account_class: "customer",
    email: "alex@example.com",
    display_name: "Alex Example",
    locale: "en",
  },
};

test("anonymous visitors see only the Authentik sign-in entry point", async ({
  page,
}) => {
  await page.route("http://api.yearclock.test/api/v1/auth/session", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "authentication required" }),
    }),
  );

  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Sign in to Yearclock" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Continue with Authentik" }),
  ).toHaveAttribute(
    "href",
    "http://api.yearclock.test/api/v1/auth/login?return_to=%2F",
  );
  await expect(page.getByText("PostgreSQL ready")).toHaveCount(0);
});

test("a customer can sign in, switch language, and sign out", async ({
  page,
}) => {
  let activeSession: typeof session | null = null;
  let selectedLocale: string | null = null;

  await page.route("http://api.yearclock.test/api/v1/auth/session", (route) =>
    activeSession
      ? route.fulfill({ status: 200, json: activeSession })
      : route.fulfill({ status: 401, json: { detail: "authentication required" } }),
  );
  await page.route(
    "http://api.yearclock.test/api/v1/auth/profile/locale",
    async (route) => {
      selectedLocale = (await route.request().postDataJSON()).locale;
      activeSession = {
        user_account: { ...session.user_account, locale: selectedLocale ?? "en" },
      };
      await route.fulfill({ status: 200, json: activeSession });
    },
  );
  await page.route(
    "http://api.yearclock.test/api/v1/auth/login**",
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/html",
        body: `
          <main>
            <h1>Authentik</h1>
            <a href="http://api.yearclock.test/api/v1/auth/callback?code=test-code&state=test-state">
              Sign in
            </a>
          </main>
        `,
      }),
  );
  await page.route(
    "http://api.yearclock.test/api/v1/auth/callback**",
    (route) => {
      activeSession = session;
      return route.fulfill({
        status: 303,
        headers: { location: "http://127.0.0.1:8174/" },
      });
    },
  );
  await page.route("http://api.yearclock.test/api/v1/system/status", (route) =>
    route.fulfill({
      status: 200,
      json: {
        status: "ok",
        database: "ready",
        schema_revision: "0002",
      },
    }),
  );
  await page.route("http://api.yearclock.test/api/v1/auth/logout", async (route) => {
    activeSession = null;
    await route.fulfill({
      status: 303,
      headers: { location: "http://127.0.0.1:8174/" },
    });
  });

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Sign in to Yearclock" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Continue with Authentik" }).click();
  await expect(page.getByRole("heading", { name: "Authentik" })).toBeVisible();
  await page.getByRole("link", { name: "Sign in" }).click();

  await expect(page.getByRole("heading", { name: "Yearclock" })).toBeVisible();
  await expect(page.getByText("PostgreSQL ready · schema 0002")).toBeVisible();

  await page.getByRole("button", { name: "Account menu for Alex Example" }).click();
  await expect(page.getByRole("menu").getByText("Signed in as Alex Example")).toBeVisible();
  await expect(page.getByRole("menuitemradio", { name: "English" })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("menuitemradio", { name: "Suomi" }).click();

  await expect(page.getByRole("heading", { name: "Vuosikello" })).toBeVisible();
  expect(selectedLocale).toBe("fi");
  await page.getByRole("button", { name: "Tilivalikko: Alex Example" }).click();
  await expect(page.getByRole("menu").getByText("Kirjautuneena: Alex Example")).toBeVisible();

  await page.getByRole("menuitem", { name: "Kirjaudu ulos" }).click();
  await expect(
    page.getByRole("heading", { name: "Kirjaudu Yearclockiin" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Olet kirjautunut ulos.");
  await expect(page.getByText("Istuntosi on vanhentunut.")).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("Olet kirjautunut ulos.")).toHaveCount(0);
});

test("an expired application session fails closed", async ({ page }) => {
  let sessionIsValid = true;
  await page.route("http://api.yearclock.test/api/v1/auth/session", (route) =>
    sessionIsValid
      ? route.fulfill({ status: 200, json: session })
      : route.fulfill({ status: 401, json: { detail: "authentication required" } }),
  );

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Yearclock" })).toBeVisible();

  sessionIsValid = false;
  await page.reload();

  await expect(page.getByRole("alert")).toHaveText("Your session has expired.");
  await expect(
    page.getByRole("heading", { name: "Sign in to Yearclock" }),
  ).toBeVisible();
});
