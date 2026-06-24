import { createContext, useContext } from "react";

export type WorkspaceScenarioSummary = {
  id: string;
  name: string;
};

export type WorkspaceOrgStateSummary = {
  id: string;
  name: string;
  targetDate: string;
};

type WorkspaceSelectionContextValue = {
  selectedScenario: WorkspaceScenarioSummary | null;
  setSelectedScenario: (scenario: WorkspaceScenarioSummary | null) => void;
  selectedOrgState: WorkspaceOrgStateSummary | null;
  setSelectedOrgState: (orgState: WorkspaceOrgStateSummary | null) => void;
};

export const WorkspaceSelectionContext =
  createContext<WorkspaceSelectionContextValue | null>(null);

export function useWorkspaceSelection(): WorkspaceSelectionContextValue {
  const value = useContext(WorkspaceSelectionContext);
  if (!value) {
    throw new Error(
      "useWorkspaceSelection must be used inside WorkspaceSelectionProvider"
    );
  }
  return value;
}
