import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PropsWithChildren } from "react";
import { authenticatedFetch, buildApiUrl, configureRequestAuthentication } from "../api/client";
import type { UserDto } from "../api/users";
import { AuthContext } from "./AuthContext";
import type { AuthContextValue, AuthStatus, SessionFeatures } from "./AuthContext";
import { navigateBrowser } from "./browserNavigation";

type SessionResponse = {
  user: UserDto;
  csrfToken: string;
  features: SessionFeatures;
};

const DISABLED_FEATURES: SessionFeatures = { mcp: false, mcpChangeSetReview: false };

type LogoutResponse = {
  logoutUrl: string | null;
};

function isUser(value: unknown): value is UserDto {
  if (!value || typeof value !== "object") return false;
  const user = value as Partial<UserDto>;
  return (
    typeof user.id === "number" &&
    typeof user.name === "string" &&
    typeof user.email === "string" &&
    (user.role === "admin" || user.role === "consultant")
  );
}

function parseSession(value: unknown): SessionResponse {
  if (!value || typeof value !== "object") {
    throw new Error("Invalid authentication session response.");
  }
  const session = value as Partial<SessionResponse>;
  if (!isUser(session.user) || typeof session.csrfToken !== "string" || !session.csrfToken) {
    throw new Error("Invalid authentication session response.");
  }
  return { user: session.user, csrfToken: session.csrfToken, features: parseFeatures(session) };
}

// A missing or malformed flag keeps the feature off, so MCP-only UI stays hidden.
function parseFeatures(session: Partial<SessionResponse>): SessionFeatures {
  const features: unknown = session.features;
  if (!features || typeof features !== "object") return DISABLED_FEATURES;
  const flags = features as Partial<SessionFeatures>;
  const mcp = flags.mcp === true;
  return { mcp, mcpChangeSetReview: mcp && flags.mcpChangeSetReview === true };
}

function parseLogout(value: unknown): LogoutResponse {
  if (!value || typeof value !== "object") {
    throw new Error("Invalid logout response.");
  }
  const logoutUrl = (value as Partial<LogoutResponse>).logoutUrl;
  if (logoutUrl !== null && typeof logoutUrl !== "string") {
    throw new Error("Invalid logout response.");
  }
  return { logoutUrl };
}

function safeReturnTo(value: string): string {
  const hasControlCharacter = Array.from(value).some((character) => {
    const code = character.charCodeAt(0);
    return code < 32 || code === 127;
  });
  const hasMalformedPercentEscape = Array.from(value).some(
    (character, index) =>
      character === "%" && !/^[0-9a-f]{2}$/i.test(value.slice(index + 1, index + 3))
  );
  return value.startsWith("/") &&
    !value.startsWith("//") &&
    !value.includes("\\") &&
    !value.includes("#") &&
    !hasControlCharacter &&
    !hasMalformedPercentEscape
    ? value
    : "/";
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<UserDto | null>(null);
  const [features, setFeatures] = useState<SessionFeatures>(DISABLED_FEATURES);
  const [authError, setAuthError] = useState("");
  const csrfTokenRef = useRef<string | null>(null);

  const invalidateSession = useCallback(() => {
    csrfTokenRef.current = null;
    setUser(null);
    setFeatures(DISABLED_FEATURES);
    setAuthError("");
    setStatus("anonymous");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const removeAuthentication = configureRequestAuthentication({
      getCsrfToken: () => csrfTokenRef.current,
      onUnauthorized: invalidateSession
    });

    async function restoreSession() {
      try {
        const response = await authenticatedFetch(
          "/api/v1/auth/session",
          {
            method: "GET",
            headers: { Accept: "application/json" }
          },
          controller.signal
        );
        if (!response.ok) {
          if (response.status === 401) return;
          throw new Error(`Session restoration failed (${response.status}).`);
        }
        const session = parseSession(await response.json());
        if (!active) return;
        csrfTokenRef.current = session.csrfToken;
        setUser(session.user);
        setFeatures(session.features);
        setAuthError("");
        setStatus("authenticated");
      } catch (error) {
        if (!active || (error as { name?: string }).name === "AbortError") return;
        invalidateSession();
        setAuthError(error instanceof Error ? error.message : "Session restoration failed.");
      }
    }

    void restoreSession();
    return () => {
      active = false;
      controller.abort();
      removeAuthentication();
    };
  }, [invalidateSession]);

  const login = useCallback((returnTo: string) => {
    const parameters = new URLSearchParams({ return_to: safeReturnTo(returnTo) });
    navigateBrowser(buildApiUrl(`/api/v1/auth/login?${parameters.toString()}`));
  }, []);

  const logout = useCallback(async () => {
    try {
      setAuthError("");
      const response = await authenticatedFetch("/api/v1/auth/logout", {
        method: "POST",
        headers: { Accept: "application/json" }
      });
      if (!response.ok) {
        throw new Error(`Logout failed (${response.status}).`);
      }
      invalidateSession();
      const result = parseLogout(await response.json());
      navigateBrowser(result.logoutUrl || "/login");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Logout failed.");
    }
  }, [invalidateSession]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, features, authError, login, logout, invalidateSession }),
    [authError, features, invalidateSession, login, logout, status, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
