import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import {
  AuthenticationRequiredError,
  PlatformAccountError,
  loadSession,
  saveLocale,
  type UserAccount,
} from "./auth-client";
import { AuthenticatedShell } from "./components/AuthenticatedShell";
import { LegalRoutes } from "./legal/LegalPages";
import { PlatformConsole } from "./platform/PlatformConsole";
import { SignIn } from "./components/SignIn";
import { SignedOutLayout } from "./shell/SignedOutLayout";
import { Alert, OverlayProvider } from "./ui";
import {
  messages,
  rememberLocale,
  storedLocale,
  type Locale,
} from "./i18n";

const hadSessionKey = "yearclock.had-session";
const signedOutKey = "yearclock.signed-out";

type AuthState =
  | { state: "loading"; locale: Locale }
  | { state: "anonymous"; expired: boolean; signedOut: boolean; locale: Locale }
  | { state: "authenticated"; userAccount: UserAccount }
  | { state: "platform"; locale: Locale }
  | { state: "error"; locale: Locale };

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/platform/*" element={<PlatformConsole />} />
        <Route path="/legal/*" element={<LegalRoutes />} />
        <Route path="*" element={<CustomerApp />} />
      </Routes>
    </BrowserRouter>
  );
}

function CustomerApp() {
  const [authState, setAuthState] = useState<AuthState>({
    state: "loading",
    locale: storedLocale(),
  });

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const userAccount = await loadSession(controller.signal);
        if (userAccount === null) {
          setAuthState({
            state: "anonymous",
            expired: sessionStorage.getItem(hadSessionKey) === "true",
            signedOut: consumeSignedOut(),
            locale: storedLocale(),
          });
          return;
        }
        sessionStorage.setItem(hadSessionKey, "true");
        rememberLocale(userAccount.locale);
        setAuthState({ state: "authenticated", userAccount });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (error instanceof PlatformAccountError) {
          setAuthState({ state: "platform", locale: storedLocale() });
          return;
        }
        setAuthState({ state: "error", locale: storedLocale() });
      }
    }

    void load();
    return () => controller.abort();
  }, []);

  async function changeLocale(locale: Locale) {
    if (authState.state !== "authenticated") {
      return;
    }
    try {
      const userAccount = await saveLocale(locale);
      rememberLocale(userAccount.locale);
      setAuthState({ state: "authenticated", userAccount });
    } catch (error) {
      if (error instanceof AuthenticationRequiredError) {
        setAuthState({ state: "anonymous", expired: true, signedOut: false, locale });
        return;
      }
      setAuthState({ state: "error", locale });
    }
  }

  if (authState.state === "loading") {
    return (
      <SignedOutLayout>
        <p role="status" className="text-[13px] text-ink-muted">{messages(authState.locale).checkingSession}</p>
      </SignedOutLayout>
    );
  }
  if (authState.state === "anonymous") {
    return (
      <SignIn expired={authState.expired} signedOut={authState.signedOut} locale={authState.locale} />
    );
  }
  if (authState.state === "platform") {
    return (
      <SignedOutLayout>
        <Alert tone="info" role="alert">{messages(authState.locale).platformAccount}</Alert>
        <a className="inline-flex h-10 items-center justify-center rounded-[var(--radius-control)] bg-accent px-4 text-sm font-semibold text-white no-underline hover:bg-accent-hover" href="/platform">{messages(authState.locale).openConsole}</a>
      </SignedOutLayout>
    );
  }
  if (authState.state === "error") {
    return (
      <SignedOutLayout>
        <Alert tone="danger" role="alert">{messages(authState.locale).unavailable}</Alert>
      </SignedOutLayout>
    );
  }
  const shellLocale: Locale = authState.userAccount.locale === "fi" ? "fi" : "en";
  return (
    <OverlayProvider labels={messages(shellLocale).overlay}>
      <AuthenticatedShell
        userAccount={authState.userAccount}
        onLocaleChange={changeLocale}
        onLogout={() => { sessionStorage.removeItem(hadSessionKey); sessionStorage.setItem(signedOutKey, "true"); }}
      />
    </OverlayProvider>
  );
}

/** True once after the user signed out on purpose, so the sign-in page can confirm it. */
function consumeSignedOut(): boolean {
  try {
    const signedOut = sessionStorage.getItem(signedOutKey) === "true";
    sessionStorage.removeItem(signedOutKey);
    return signedOut;
  } catch {
    return false;
  }
}
