import { useState } from "react";
import { useAuth } from "./AuthContext";

type SessionControlsProps = {
  variant?: "bar" | "header";
};

export default function SessionControls({ variant = "bar" }: SessionControlsProps) {
  const { user, logout, authError } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);

  if (!user) return null;

  async function onLogout() {
    setLoggingOut(true);
    await logout();
    setLoggingOut(false);
  }

  const content = (
    <>
      <span className="session-controls__identity">
        <strong title={variant === "header" ? user.name : undefined}>{user.name}</strong>
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
        <span
          className="session-controls__error"
          title={variant === "header" ? authError : undefined}
        >
          {authError}
        </span>
      ) : null}
    </>
  );

  if (variant === "header") {
    // A group rather than an aside, so the banner does not contain a complementary landmark.
    return (
      <div
        className="session-controls session-controls--header"
        role="group"
        aria-label="Current user session"
      >
        {content}
      </div>
    );
  }

  return (
    <aside className="session-controls" aria-label="Current user session">
      {content}
    </aside>
  );
}
