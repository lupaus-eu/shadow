import { useLayoutEffect, useMemo, useState } from "react";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams
} from "react-router-dom";
import EmptyTab from "../components/EmptyTab";
import OrganisationDropdown from "../components/OrganisationDropdown";
import OrgStateDropdown from "../components/OrgStateDropdown";
import ScenarioDropdown from "../components/ScenarioDropdown";
import EventsTab from "../features/events/EventsTab";
import MetricsTab from "../features/metrics/MetricsTab";
import ScenariosTab from "../features/scenarios/ScenariosTab";
import StructureTab from "../features/structure/StructureTab";
import SummaryTab from "../features/summary/SummaryTab";
import UsersTab from "../features/users/UsersTab";
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

  return (
    <WorkspaceSelectionProvider key={orgId}>
      <WorkspaceShell orgId={orgId} initialOrganisationName={organisationName} />
    </WorkspaceSelectionProvider>
  );
}

function WorkspaceShell(props: {
  orgId: string;
  initialOrganisationName: string;
}) {
  const [organisationName, setOrganisationName] = useState(
    props.initialOrganisationName
  );
  const forwardedState: WorkspaceNavState = { organisationName };

  return (
    <div className="workspace-shell">
      <header className="workspace-header">
        <div className="workspace-header__top">
          <div className="workspace-header__brand">
            <span className="app-mark" aria-hidden="true">
              S
            </span>
            <span className="app-name">Schatten</span>
          </div>
          <WorkspaceIndicators
            orgId={props.orgId}
            organisationName={organisationName}
            onOrganisationNameChange={setOrganisationName}
          />
        </div>
        <WorkspaceTabs orgId={props.orgId} forwardedState={forwardedState} />
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
              element={<WorkspaceTabContent tab={tab} orgId={props.orgId} />}
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
  );
}

function WorkspaceIndicators(props: {
  orgId: string;
  organisationName: string;
  onOrganisationNameChange: (name: string) => void;
}) {
  return (
    <div className="workspace-indicators" aria-label="Current workspace context">
      <OrganisationDropdown
        orgId={props.orgId}
        organisationName={props.organisationName}
        onOrganisationNameChange={props.onOrganisationNameChange}
      />
      <ScenarioDropdown orgId={props.orgId} />
      <OrgStateDropdown orgId={props.orgId} />
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

  if (props.tab.signature === "users") {
    return <UsersTab />;
  }

  return <EmptyTab title={props.tab.label} description={props.tab.emptyText} />;
}
