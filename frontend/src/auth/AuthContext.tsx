import { createContext, useContext } from "react";
import type { UserDto } from "../api/users";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

// Server feature flags from the session response; `mcp` mirrors MCP_ENABLED.
export type SessionFeatures = {
  mcp: boolean;
};

export type AuthContextValue = {
  status: AuthStatus;
  user: UserDto | null;
  features: SessionFeatures;
  authError: string;
  login: (returnTo: string) => void;
  logout: () => Promise<void>;
  invalidateSession: () => void;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
