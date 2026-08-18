import { createContext, useContext } from "react";
import type { UserDto } from "../api/users";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export type AuthContextValue = {
  status: AuthStatus;
  user: UserDto | null;
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
