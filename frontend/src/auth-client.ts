import type { Locale } from "./i18n";

export const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8100";

export type UserAccount = {
  id: string;
  account_class: "customer";
  email: string;
  display_name: string;
  locale: Locale;
};

export class AuthenticationRequiredError extends Error {}
export class PlatformAccountError extends Error {}

export async function loadSession(
  signal?: AbortSignal,
): Promise<UserAccount | null> {
  const response = await fetch(`${apiBaseUrl}/api/v1/auth/session`, {
    credentials: "include",
    signal,
  });
  if (response.status === 401) {
    return null;
  }
  if (response.status === 403) {
    throw new PlatformAccountError();
  }
  if (!response.ok) {
    throw new Error("Session request failed");
  }
  const result = (await response.json()) as { user_account: UserAccount };
  return result.user_account;
}

export async function saveLocale(locale: Locale): Promise<UserAccount> {
  const response = await fetch(`${apiBaseUrl}/api/v1/auth/profile/locale`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ locale }),
  });
  if (response.status === 401) {
    throw new AuthenticationRequiredError();
  }
  if (!response.ok) {
    throw new Error("Locale request failed");
  }
  const result = (await response.json()) as { user_account: UserAccount };
  return result.user_account;
}

export function loginUrl(returnTo: string) {
  return `${apiBaseUrl}/api/v1/auth/login?return_to=${encodeURIComponent(returnTo)}`;
}

export const logoutUrl = `${apiBaseUrl}/api/v1/auth/logout`;

export async function loadSystemRevision(
  signal: AbortSignal,
): Promise<string> {
  const response = await fetch(`${apiBaseUrl}/api/v1/system/status`, {
    credentials: "include",
    signal,
  });
  if (!response.ok) {
    throw new Error("System status request failed");
  }
  const result = (await response.json()) as {
    database: string;
    schema_revision: string;
  };
  if (result.database !== "ready") {
    throw new Error("Database is not ready");
  }
  return result.schema_revision;
}
