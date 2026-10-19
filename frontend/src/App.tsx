import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation, useMatch } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { useAuth } from "./auth/AuthContext";
import LoginPage from "./auth/LoginPage";
import SessionControls from "./auth/SessionControls";
import { RouteErrorBoundary, RouteLoadingFallback } from "./components/DeferredRoute";
import HomePage from "./pages/HomePage";
import NotFound from "./pages/NotFound";

const Workspace = lazy(() => import("./pages/Workspace"));

export default function App() {
  return (
    <AuthProvider>
      <AuthenticatedApplication />
    </AuthProvider>
  );
}

function AuthenticatedApplication() {
  const location = useLocation();
  const workspaceMatch = useMatch("/schatten/:orgId/*");
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
      new URLSearchParams(location.search).get("error") === "authentication_failed";
    return <LoginPage returnTo="/" authenticationFailed={authenticationFailed} />;
  }

  if (status === "anonymous") {
    return <LoginPage returnTo={`${location.pathname}${location.search}`} />;
  }

  return (
    <div className="authenticated-shell">
      {/* Workspace routes show the session controls in the workspace header instead,
          or in the route fallbacks below until that header renders. */}
      {workspaceMatch ? null : <SessionControls />}
      <div className="authenticated-shell__content">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route
            path="/schatten/:orgId/*"
            element={
              <RouteErrorBoundary
                title="Unable to load workspace"
                resetKey={location.pathname}
                errorPrefix={<SessionControls />}
              >
                <Suspense
                  fallback={
                    <>
                      <SessionControls />
                      <RouteLoadingFallback message="Loading workspace..." />
                    </>
                  }
                >
                  <Workspace />
                </Suspense>
              </RouteErrorBoundary>
            }
          />
          <Route path="/404" element={<NotFound />} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Routes>
      </div>
    </div>
  );
}
