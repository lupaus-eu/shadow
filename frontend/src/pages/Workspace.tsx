import { useLayoutEffect, useMemo } from "react";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams
} from "react-router-dom";
import EmptyTab from "../components/EmptyTab";
import { useWorkspaceSelection } from "../workspace/WorkspaceSelectionContext";
import WorkspaceSelectionProvider from "../workspace/WorkspaceSelectionProvider";
import { WORKSPACE_TABS } from "../workspace/workspaceTabs";

type WorkspaceNavState = {
  organisationName?: string;
};

export default function Workspace() {
  const { orgId } = useParams<{ orgId: string }>();
  const location = useLocation();

  const stateOrgName =
    (location.state as WorkspaceNavState | null)?.organisationName || undefined;
  const storageKey = useMemo(
    () => (orgId ? `schatten:organisationName:${orgId}` : ""),
    [orgId]
  );

  useLayoutEffect(() => {
    if (!orgId || !stateOrgName) return;
    try {
      sessionStorage.setItem(storageKey, stateOrgName);
    } catch {
      // Session storage is only a display convenience.
    }
  }, [orgId, stateOrgName, storageKey]);

  const storedOrgName = useMemo(() => {
    if (!orgId) return undefined;
    try {
      return sessionStorage.getItem(storageKey) ?? undefined;
    } catch {
      return undefined;
    }
  }, [orgId, storageKey]);

  if (!orgId) return <Navigate to="/" replace />;

  const organisationName = stateOrgName ?? storedOrgName ?? orgId;
  const forwardedState: WorkspaceNavState = { organisationName };

  return (
    <WorkspaceSelectionProvider>
      <div className="workspace-shell">
        <header className="workspace-header">
          <div className="workspace-header__top">
            <div className="workspace-header__brand">
              <span className="app-mark" aria-hidden="true">
                S
              </span>
              <span className="app-name">Schatten</span>
            </div>
            <WorkspaceIndicators organisationName={organisationName} />
          </div>
          <nav className="tab-bar" aria-label="Schatten workspace tabs">
            {WORKSPACE_TABS.map((tab) => (
              <NavLink
                key={tab.signature}
                className={({ isActive }) =>
                  `tab-link${isActive ? " tab-link--active" : ""}`
                }
                to={`/schatten/${orgId}/${tab.signature}`}
                state={forwardedState}
                end
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="workspace-content">
          <Routes>
            <Route
              index
              element={
                <Navigate to="org-states" replace state={forwardedState} />
              }
            />
            {WORKSPACE_TABS.map((tab) => (
              <Route
                key={tab.signature}
                path={tab.signature}
                element={
                  <EmptyTab title={tab.label} description={tab.emptyText} />
                }
              />
            ))}
            <Route
              path="*"
              element={
                <EmptyTab
                  title="Not found"
                  description="This workspace tab does not exist."
                />
              }
            />
          </Routes>
        </main>
      </div>
    </WorkspaceSelectionProvider>
  );
}

function WorkspaceIndicators(props: { organisationName: string }) {
  const { selectedScenario, selectedOrgState } = useWorkspaceSelection();

  return (
    <div className="workspace-indicators" aria-label="Current workspace context">
      <ReadOnlyChip label="Organisation" value={props.organisationName} />
      <ReadOnlyChip label="Scenario" value={selectedScenario?.name ?? "None"} />
      <ReadOnlyChip label="Org state" value={selectedOrgState?.name ?? "None"} />
    </div>
  );
}

function ReadOnlyChip(props: { label: string; value: string }) {
  return (
    <span className="context-chip" title={`${props.label}: ${props.value}`}>
      <span className="context-chip__label">{props.label}</span>
      <span className="context-chip__value">{props.value}</span>
    </span>
  );
}
