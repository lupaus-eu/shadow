import { useState } from "react";
import { useAuth } from "./AuthContext";

export default function SessionControls() {
  const { user, logout, authError } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);

  if (!user) return null;

  async function onLogout() {
    setLoggingOut(true);
    await logout();
    setLoggingOut(false);
  }

  return (
    <aside className="session-controls" aria-label="Current user session">
      <span className="session-controls__identity">
        <strong>{user.name}</strong>
        <span>{user.role === "admin" ? "Admin" : "Consultant"}</span>
      </span>
      <button
        className="btn btn--secondary btn--compact"
        type="button"
        onClick={() => void onLogout()}
        disabled={loggingOut}
      >
        {loggingOut ? "Signing out..." : "Sign out"}
      </button>
      {authError ? (
        <span className="session-controls__error">{authError}</span>
      ) : null}
    </aside>
  );
}
