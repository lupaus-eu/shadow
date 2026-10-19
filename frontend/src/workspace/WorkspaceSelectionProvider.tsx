import { useCallback, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  WorkspaceSelectionContext,
  type WorkspaceOrgStateSummary,
  type WorkspaceScenarioSummary
} from "./WorkspaceSelectionContext";

export default function WorkspaceSelectionProvider(props: { children: ReactNode }) {
  const [selection, setSelection] = useState<{
    selectedScenario: WorkspaceScenarioSummary | null;
    selectedOrgState: WorkspaceOrgStateSummary | null;
  }>({ selectedScenario: null, selectedOrgState: null });

  const setSelectedScenario = useCallback((selectedScenario: WorkspaceScenarioSummary | null) => {
    setSelection((current) => ({ ...current, selectedScenario }));
  }, []);

  const setSelectedOrgState = useCallback((selectedOrgState: WorkspaceOrgStateSummary | null) => {
    setSelection((current) => ({ ...current, selectedOrgState }));
  }, []);

  const setWorkspaceSelection = useCallback(
    (
      selectedScenario: WorkspaceScenarioSummary | null,
      selectedOrgState: WorkspaceOrgStateSummary | null
    ) => {
      setSelection({ selectedScenario, selectedOrgState });
    },
    []
  );

  const value = useMemo(
    () => ({
      selectedScenario: selection.selectedScenario,
      setSelectedScenario,
      selectedOrgState: selection.selectedOrgState,
      setSelectedOrgState,
      setWorkspaceSelection
    }),
    [
      selection.selectedOrgState,
      selection.selectedScenario,
      setSelectedOrgState,
      setSelectedScenario,
      setWorkspaceSelection
    ]
  );

  return (
    <WorkspaceSelectionContext.Provider value={value}>
      {props.children}
    </WorkspaceSelectionContext.Provider>
  );
}
