import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { useAuth } from "./auth/AuthContext";
import LoginPage from "./auth/LoginPage";
import SessionControls from "./auth/SessionControls";
import HomePage from "./pages/HomePage";
import NotFound from "./pages/NotFound";
import Workspace from "./pages/Workspace";

export default function App() {
  return (
    <AuthProvider>
      <AuthenticatedApplication />
    </AuthProvider>
  );
}

function AuthenticatedApplication() {
  const location = useLocation();
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <main className="center-page" aria-busy="true">
        <section className="home-panel">
          <p className="eyebrow">Schatten</p>
          <h1 className="display-title">Loading session...</h1>
        </section>
      </main>
    );
  }

  if (location.pathname === "/login") {
    if (status === "authenticated") return <Navigate to="/" replace />;
    const authenticationFailed =
      new URLSearchParams(location.search).get("error") ===
      "authentication_failed";
    return (
      <LoginPage returnTo="/" authenticationFailed={authenticationFailed} />
    );
  }

  if (status === "anonymous") {
    return <LoginPage returnTo={`${location.pathname}${location.search}`} />;
  }

  return (
    <div className="authenticated-shell">
      <SessionControls />
      <div className="authenticated-shell__content">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/schatten/:orgId/*" element={<Workspace />} />
          <Route path="/404" element={<NotFound />} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Routes>
      </div>
    </div>
  );
}
