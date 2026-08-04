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
import EventsTab from "../features/events/EventsTab";
import MetricsTab from "../features/metrics/MetricsTab";
import ScenariosTab from "../features/scenarios/ScenariosTab";
import StructureTab from "../features/structure/StructureTab";
import SummaryTab from "../features/summary/SummaryTab";
import { useWorkspaceSelection } from "../workspace/WorkspaceSelectionContext";
import WorkspaceSelectionProvider from "../workspace/WorkspaceSelectionProvider";
import { WORKSPACE_TABS, type WorkspaceTab } from "../workspace/workspaceTabs";

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
    <WorkspaceSelectionProvider key={orgId}>
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
          <WorkspaceTabs orgId={orgId} forwardedState={forwardedState} />
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
                element={<WorkspaceTabContent tab={tab} orgId={orgId} />}
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
  const orgStateValue = selectedOrgState
    ? `${selectedOrgState.name} (${selectedOrgState.targetDate})`
    : "None";

  return (
    <div className="workspace-indicators" aria-label="Current workspace context">
      <ReadOnlyChip label="Organisation" value={props.organisationName} />
      <ReadOnlyChip label="Scenario" value={selectedScenario?.name ?? "None"} />
      <ReadOnlyChip label="Org state" value={orgStateValue} />
    </div>
  );
}

function WorkspaceTabs(props: {
  orgId: string;
  forwardedState: WorkspaceNavState;
}) {
  const { selectedScenario, selectedOrgState } = useWorkspaceSelection();
  const hasScenarioAndOrgState = Boolean(selectedScenario && selectedOrgState);

  return (
    <nav className="tab-bar" aria-label="Schatten workspace tabs">
      {WORKSPACE_TABS.map((tab) => {
        const isDisabled =
          tab.requiresScenarioAndOrgState && !hasScenarioAndOrgState;

        if (isDisabled) {
          return (
            <span
              key={tab.signature}
              className="tab-link tab-link--disabled"
              aria-disabled="true"
              title="Select a scenario and org state in Scenarios first"
            >
              {tab.label}
            </span>
          );
        }

        return (
          <NavLink
            key={tab.signature}
            className={({ isActive }) =>
              `tab-link${isActive ? " tab-link--active" : ""}`
            }
            to={`/schatten/${props.orgId}/${tab.signature}`}
            state={props.forwardedState}
            end
          >
            {tab.label}
          </NavLink>
        );
      })}
    </nav>
  );
}

function WorkspaceTabContent(props: { tab: WorkspaceTab; orgId: string }) {
  const { selectedScenario, selectedOrgState } = useWorkspaceSelection();

  if (props.tab.signature === "org-states") {
    return <ScenariosTab orgId={props.orgId} />;
  }

  if (
    props.tab.requiresScenarioAndOrgState &&
    (!selectedScenario || !selectedOrgState)
  ) {
    return (
      <EmptyTab
        title={props.tab.label}
        description="Select a scenario and org state in Scenarios to activate this tab."
      />
    );
  }

  if (props.tab.signature === "events") {
    return <EventsTab orgId={props.orgId} />;
  }

  if (props.tab.signature === "metrics") {
    return <MetricsTab orgId={props.orgId} />;
  }

  if (props.tab.signature === "graph") {
    return <StructureTab orgId={props.orgId} />;
  }

  if (props.tab.signature === "summary") {
    return <SummaryTab orgId={props.orgId} />;
  }

  return <EmptyTab title={props.tab.label} description={props.tab.emptyText} />;
}

function ReadOnlyChip(props: { label: string; value: string }) {
  return (
    <span className="context-chip" title={`${props.label}: ${props.value}`}>
      <span className="context-chip__label">{props.label}</span>
      <span className="context-chip__value">{props.value}</span>
    </span>
  );
}
