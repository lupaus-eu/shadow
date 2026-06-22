import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  WorkspaceSelectionContext,
  type WorkspaceOrgStateSummary,
  type WorkspaceScenarioSummary
} from "./WorkspaceSelectionContext";

export default function WorkspaceSelectionProvider(props: {
  children: ReactNode;
}) {
  const [selectedScenario, setSelectedScenario] =
    useState<WorkspaceScenarioSummary | null>(null);
  const [selectedOrgState, setSelectedOrgState] =
    useState<WorkspaceOrgStateSummary | null>(null);

  const value = useMemo(
    () => ({
      selectedScenario,
      setSelectedScenario,
      selectedOrgState,
      setSelectedOrgState
    }),
    [selectedScenario, selectedOrgState]
  );

  return (
    <WorkspaceSelectionContext.Provider value={value}>
      {props.children}
    </WorkspaceSelectionContext.Provider>
  );
}
