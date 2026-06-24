export type WorkspaceTabSignature =
  | "org-states"
  | "graph"
  | "events"
  | "metrics"
  | "summary"
  | "analysis";

export type WorkspaceTab = {
  signature: WorkspaceTabSignature;
  label: string;
  emptyText: string;
  requiresScenarioAndOrgState?: boolean;
};

export const WORKSPACE_TABS: WorkspaceTab[] = [
  {
    signature: "org-states",
    label: "Scenarios",
    emptyText: "Scenario selection and organisation state tools will appear here."
  },
  {
    signature: "graph",
    label: "Structure",
    emptyText: "Organisation structure views will appear here.",
    requiresScenarioAndOrgState: true
  },
  {
    signature: "events",
    label: "Events",
    emptyText: "Event timelines and event editing will appear here.",
    requiresScenarioAndOrgState: true
  },
  {
    signature: "metrics",
    label: "Metrics",
    emptyText: "Metric definitions, values, and comparisons will appear here."
  },
  {
    signature: "summary",
    label: "Summary",
    emptyText: "Scenario and state summaries will appear here."
  },
  {
    signature: "analysis",
    label: "Analysis",
    emptyText: "Analysis tools and generated insight will appear here."
  }
];
