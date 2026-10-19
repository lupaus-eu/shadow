import { useMemo, useState } from "react";
import type { ContextType, ReactNode } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as scenariosApi from "../api/scenarios";
import type { OrgStateDto, ScenarioDto } from "../api/scenarios";
import {
  WorkspaceSelectionContext,
  type WorkspaceOrgStateSummary,
  type WorkspaceScenarioSummary
} from "../workspace/WorkspaceSelectionContext";
import OrgStateDropdown from "./OrgStateDropdown";
import ScenarioDropdown from "./ScenarioDropdown";

vi.mock("../api/scenarios", () => ({
  fetchScenarios: vi.fn(),
  fetchOrgStates: vi.fn()
}));

const scenarios: ScenarioDto[] = [
  {
    id: "reality",
    name: "Reality",
    description: "Current baseline",
    protected: true
  },
  {
    id: "future",
    name: "Future plan",
    description: "A possible future",
    protected: false
  }
];

const realityStates: OrgStateDto[] = [
  {
    id: "today",
    name: "Today",
    description: "Reality now",
    targetDate: "2026-06-23"
  }
];

const futureStates: OrgStateDto[] = [
  {
    id: "launch",
    name: "Planned launch",
    description: "Launch state",
    targetDate: "2026-07-01"
  },
  {
    id: "draft",
    name: "Draft state",
    description: "Draft",
    targetDate: "2026-06-01"
  }
];

type WorkspaceValue = NonNullable<ContextType<typeof WorkspaceSelectionContext>>;

function SelectionHarness(props: {
  children: ReactNode;
  initialScenario?: WorkspaceScenarioSummary | null;
  initialOrgState?: WorkspaceOrgStateSummary | null;
  onPairCommit?: () => void;
  onOrgStateChange?: () => void;
}) {
  const [selectedScenario, setSelectedScenario] = useState<WorkspaceScenarioSummary | null>(
    props.initialScenario === undefined ? { id: "reality", name: "Reality" } : props.initialScenario
  );
  const [selectedOrgState, setSelectedOrgStateState] = useState<WorkspaceOrgStateSummary | null>(
    props.initialOrgState === undefined
      ? { id: "today", name: "Today", targetDate: "2026-06-23" }
      : props.initialOrgState
  );

  const value = useMemo<WorkspaceValue>(
    () => ({
      selectedScenario,
      setSelectedScenario,
      selectedOrgState,
      setSelectedOrgState: (orgState) => {
        props.onOrgStateChange?.();
        setSelectedOrgStateState(orgState);
      },
      setWorkspaceSelection: (scenario, orgState) => {
        props.onPairCommit?.();
        setSelectedScenario(scenario);
        setSelectedOrgStateState(orgState);
      }
    }),
    [props, selectedOrgState, selectedScenario]
  );

  return (
    <WorkspaceSelectionContext.Provider value={value}>
      {props.children}
      <output aria-label="Active context">
        {selectedScenario?.id ?? "none"}:{selectedOrgState?.id ?? "none"}
      </output>
    </WorkspaceSelectionContext.Provider>
  );
}

function renderDropdowns(options?: {
  initialScenario?: WorkspaceScenarioSummary | null;
  initialOrgState?: WorkspaceOrgStateSummary | null;
  onPairCommit?: () => void;
  onOrgStateChange?: () => void;
}) {
  return render(
    <SelectionHarness {...options}>
      <ScenarioDropdown orgId="acme" />
      <OrgStateDropdown orgId="acme" />
    </SelectionHarness>
  );
}

function mockSuccessfulReads() {
  vi.mocked(scenariosApi.fetchScenarios).mockResolvedValue(scenarios);
  vi.mocked(scenariosApi.fetchOrgStates).mockImplementation(async (_orgId, scenarioId) =>
    scenarioId === "future" ? futureStates : realityStates
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

describe("workspace scenario and org state dropdowns", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps scenario choices as drafts until Select commits the pair", async () => {
    mockSuccessfulReads();
    const onPairCommit = vi.fn();
    renderDropdowns({ onPairCommit });

    fireEvent.click(screen.getByRole("button", { name: "Change scenario" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Scenario and org state selector"
    });
    const scenarioColumn = within(dialog).getByRole("region", {
      name: "Scenarios"
    });
    fireEvent.click(
      await within(scenarioColumn).findByRole("button", {
        name: /Future plan/
      })
    );

    expect(screen.getByRole("status", { name: "Active context" })).toHaveTextContent(
      "reality:today"
    );
    expect(onPairCommit).not.toHaveBeenCalled();

    const stateColumn = within(dialog).getByRole("region", {
      name: "Scenario org states"
    });
    expect(await within(stateColumn).findByRole("button", { name: /Draft state/ })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(within(stateColumn).queryByRole("button", { name: /Today/ })).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Select" }));

    expect(onPairCommit).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status", { name: "Active context" })).toHaveTextContent(
      "future:draft"
    );
    expect(
      screen.queryByRole("dialog", { name: "Scenario and org state selector" })
    ).not.toBeInTheDocument();
  });

  it("discards scenario drafts on Escape and restores trigger focus", async () => {
    mockSuccessfulReads();
    const onPairCommit = vi.fn();
    renderDropdowns({ onPairCommit });

    const trigger = screen.getByRole("button", { name: "Change scenario" });
    fireEvent.click(trigger);
    const scenarioColumn = within(
      await screen.findByRole("dialog", {
        name: "Scenario and org state selector"
      })
    ).getByRole("region", { name: "Scenarios" });
    fireEvent.click(
      await within(scenarioColumn).findByRole("button", {
        name: /Future plan/
      })
    );
    fireEvent.keyDown(document, { key: "Escape" });

    expect(onPairCommit).not.toHaveBeenCalled();
    expect(screen.getByRole("status", { name: "Active context" })).toHaveTextContent(
      "reality:today"
    );
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("switches the standalone org state immediately without changing scenario", async () => {
    mockSuccessfulReads();
    const onPairCommit = vi.fn();
    const onOrgStateChange = vi.fn();
    renderDropdowns({
      initialScenario: { id: "future", name: "Future plan" },
      initialOrgState: {
        id: "draft",
        name: "Draft state",
        targetDate: "2026-06-01"
      },
      onPairCommit,
      onOrgStateChange
    });

    fireEvent.click(screen.getByRole("button", { name: "Change org state" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Org state selector"
    });
    fireEvent.click(await within(dialog).findByRole("button", { name: /Planned launch/ }));

    expect(onPairCommit).not.toHaveBeenCalled();
    expect(onOrgStateChange).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status", { name: "Active context" })).toHaveTextContent(
      "future:launch"
    );
  });

  it("does not commit or refetch when the active choices are selected", async () => {
    mockSuccessfulReads();
    const onPairCommit = vi.fn();
    const onOrgStateChange = vi.fn();
    renderDropdowns({ onPairCommit, onOrgStateChange });

    fireEvent.click(screen.getByRole("button", { name: "Change scenario" }));
    const scenarioDialog = await screen.findByRole("dialog", {
      name: "Scenario and org state selector"
    });
    await within(scenarioDialog).findByRole("button", { name: /Today/ });
    fireEvent.click(within(scenarioDialog).getByRole("button", { name: "Select" }));
    expect(onPairCommit).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Change org state" }));
    const stateDialog = await screen.findByRole("dialog", {
      name: "Org state selector"
    });
    fireEvent.click(await within(stateDialog).findByRole("button", { name: /Today/ }));
    expect(onOrgStateChange).not.toHaveBeenCalled();
  });

  it("shows a retryable scenario error without clearing active context", async () => {
    vi.mocked(scenariosApi.fetchScenarios)
      .mockRejectedValueOnce(new Error("Scenarios unavailable"))
      .mockResolvedValueOnce(scenarios);
    vi.mocked(scenariosApi.fetchOrgStates).mockResolvedValue(realityStates);
    renderDropdowns();

    fireEvent.click(screen.getByRole("button", { name: "Change scenario" }));
    expect(await screen.findByText("Scenarios unavailable")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Active context" })).toHaveTextContent(
      "reality:today"
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("button", { name: /Reality/ })).toBeInTheDocument();
  });

  it("ignores a late org-state response from an abandoned draft scenario", async () => {
    const futureResponse = deferred<OrgStateDto[]>();
    vi.mocked(scenariosApi.fetchScenarios).mockResolvedValue(scenarios);
    vi.mocked(scenariosApi.fetchOrgStates).mockImplementation(async (_orgId, scenarioId) =>
      scenarioId === "future" ? futureResponse.promise : realityStates
    );
    renderDropdowns();

    fireEvent.click(screen.getByRole("button", { name: "Change scenario" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Scenario and org state selector"
    });
    const scenarioColumn = within(dialog).getByRole("region", {
      name: "Scenarios"
    });
    const stateColumn = within(dialog).getByRole("region", {
      name: "Scenario org states"
    });
    await within(stateColumn).findByRole("button", { name: /Today/ });

    fireEvent.click(within(scenarioColumn).getByRole("button", { name: /Future plan/ }));
    fireEvent.click(within(scenarioColumn).getByRole("button", { name: /Reality/ }));
    await within(stateColumn).findByRole("button", { name: /Today/ });

    await act(async () => futureResponse.resolve(futureStates));
    expect(
      within(stateColumn).queryByRole("button", { name: /Planned launch/ })
    ).not.toBeInTheDocument();
    expect(within(stateColumn).getByRole("button", { name: /Today/ })).toBeInTheDocument();
  });

  it("disables org state selection until a scenario is active", () => {
    mockSuccessfulReads();
    renderDropdowns({ initialScenario: null, initialOrgState: null });

    expect(screen.getByRole("button", { name: "Change org state" })).toBeDisabled();
  });
});
