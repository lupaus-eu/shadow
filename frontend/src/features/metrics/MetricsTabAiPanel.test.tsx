import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import type { ContextType } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as aiApi from "../../api/ai";
import type { AiChangeSetDetailDto, AiConnectionDto } from "../../api/ai";
import * as timeseriesApi from "../../api/timeseries";
import { WorkspaceSelectionContext } from "../../workspace/WorkspaceSelectionContext";
import MetricsTab from "./MetricsTab";

vi.mock("../../api/timeseries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/timeseries")>()),
  fetchTimeseries: vi.fn()
}));

vi.mock("../../api/ai", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/ai")>()),
  fetchAiChangeSets: vi.fn(),
  fetchAiChangeSet: vi.fn(),
  applyAiChangeSet: vi.fn(),
  fetchAiConnections: vi.fn()
}));

const changeSetDetail: AiChangeSetDetailDto = {
  id: "cs-1",
  scenarioKey: "future",
  title: "Revenue values",
  rationale: null,
  status: "submitted",
  operationCount: 1,
  clientId: "client-abc",
  clientName: "Claude",
  createdBy: 7,
  createdByName: "Ada Consultant",
  createdTime: "2026-10-27T09:00:00Z",
  modifiedTime: "2026-10-27T09:00:00Z",
  reviewedBy: null,
  reviewedByName: null,
  reviewedTime: null,
  reviewNote: null,
  reviewedVia: null,
  reviewClientId: null,
  reviewClientName: null,
  operations: [
    {
      position: 0,
      type: "set_timeserie_values",
      ref: null,
      operation: {
        type: "set_timeserie_values",
        scenario_key: "future",
        timeserie_key: "revenue",
        payload: { values: [{ date: "2030-03-01", value: 3000 }] }
      },
      error: null,
      frozenValues: null,
      replacesExisting: false,
      replaces: null
    }
  ],
  reviewFingerprint: "a".repeat(64),
  validationResult: { ok: true, operations: [], refs: {} },
  appliedResult: null
};

const connection: AiConnectionDto = {
  grantKey: "grant-1",
  clientId: "client-abc",
  clientName: "Claude",
  scope: "schatten.read schatten.write",
  resource: "https://app.localhost/api/mcp",
  createdTime: "2026-10-01T08:00:00Z",
  lastUsedTime: null,
  expiresTime: "2026-10-31T08:00:00Z"
};

function MetricsHarness(props: {
  mcpEnabled: boolean;
  initialChangeSetKey?: string | null;
  onChangeSetKeyChange: (key: string | null) => void;
}) {
  const [changeSetKey, setChangeSetKey] = useState(props.initialChangeSetKey ?? null);
  return (
    <MetricsTab
      orgId="acme"
      ai={{
        mcpEnabled: props.mcpEnabled,
        mcpChangeSetReview: false,
        changeSetKey,
        onChangeSetKeyChange: (key) => {
          props.onChangeSetKeyChange(key);
          setChangeSetKey(key);
        }
      }}
    />
  );
}

function renderMetrics(options: {
  mcpEnabled: boolean;
  changeSetKey?: string | null;
  scenario?: { id: string; name: string } | null;
}) {
  const onChangeSetKeyChange = vi.fn();
  const context: ContextType<typeof WorkspaceSelectionContext> = {
    selectedScenario:
      options.scenario === undefined ? { id: "future", name: "Future plan" } : options.scenario,
    setSelectedScenario: vi.fn(),
    selectedOrgState: null,
    setSelectedOrgState: vi.fn(),
    setWorkspaceSelection: vi.fn()
  };

  render(
    <WorkspaceSelectionContext.Provider value={context}>
      <MetricsHarness
        mcpEnabled={options.mcpEnabled}
        initialChangeSetKey={options.changeSetKey}
        onChangeSetKeyChange={onChangeSetKeyChange}
      />
    </WorkspaceSelectionContext.Provider>
  );
  return { onChangeSetKeyChange };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(timeseriesApi.fetchTimeseries).mockResolvedValue([
    {
      id: "revenue",
      name: "Revenue",
      description: "",
      unit: "EUR",
      timeUnit: "month",
      valueUnit: "number",
      values: [{ date: "2030-01-01", value: 1000 }]
    }
  ]);
  vi.mocked(aiApi.fetchAiChangeSets).mockResolvedValue([]);
  vi.mocked(aiApi.fetchAiConnections).mockResolvedValue([]);
  vi.mocked(aiApi.fetchAiChangeSet).mockResolvedValue(changeSetDetail);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MetricsTab AI panel", () => {
  it("toggles the panel from the toolbar when MCP is enabled", async () => {
    renderMetrics({ mcpEnabled: true });

    const toggle = await screen.findByRole("button", { name: "AI panel" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(aiApi.fetchAiConnections).not.toHaveBeenCalled();
    expect(screen.queryByRole("complementary", { name: "AI" })).not.toBeInTheDocument();

    fireEvent.click(toggle);

    const panel = screen.getByRole("complementary", { name: "AI" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAttribute("aria-controls", panel.id);
    expect(await within(panel).findByText("No change sets.")).toBeVisible();
    expect(within(panel).getByRole("button", { name: "Connect" })).toBeVisible();

    fireEvent.click(within(panel).getByRole("button", { name: "Connect" }));
    expect(
      within(panel).getByText(`${window.location.origin}/api/mcp`, { selector: "code" })
    ).toBeVisible();
    expect(within(panel).getAllByRole("button", { name: "Copy URL" })).toHaveLength(1);

    fireEvent.click(toggle);

    expect(screen.queryByRole("complementary", { name: "AI" })).not.toBeInTheDocument();
    expect(await screen.findByRole("rowheader", { name: /Revenue/ })).toBeVisible();
  });

  it("hides the toggle with MCP disabled until there is a change set or connection", async () => {
    renderMetrics({ mcpEnabled: false });

    await waitFor(() => expect(aiApi.fetchAiConnections).toHaveBeenCalledTimes(1));
    expect(aiApi.fetchAiChangeSets).toHaveBeenCalledWith(
      "acme",
      { limit: 1 },
      expect.any(AbortSignal)
    );
    expect(await screen.findByRole("rowheader", { name: /Revenue/ })).toBeVisible();
    expect(screen.queryByRole("button", { name: "AI panel" })).not.toBeInTheDocument();
  });

  it("offers the panel with MCP disabled when the user has a connection, without Connect", async () => {
    vi.mocked(aiApi.fetchAiConnections).mockResolvedValue([connection]);
    renderMetrics({ mcpEnabled: false });

    fireEvent.click(await screen.findByRole("button", { name: "AI panel" }));

    const panel = screen.getByRole("complementary", { name: "AI" });
    expect(await within(panel).findByText("No change sets.")).toBeVisible();
    expect(within(panel).queryByRole("button", { name: "Connect" })).not.toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Connections" }));
    expect(await within(panel).findByText("client-abc")).toBeVisible();
    expect(within(panel).getByText("Read and propose changes")).toBeVisible();
  });

  it("opens the panel on the deep-linked change set and clears the link on close", async () => {
    const { onChangeSetKeyChange } = renderMetrics({ mcpEnabled: false, changeSetKey: "cs-1" });

    const panel = screen.getByRole("complementary", { name: "AI" });
    expect(await within(panel).findByRole("heading", { name: "Revenue values" })).toBeVisible();
    expect(aiApi.fetchAiChangeSet).toHaveBeenCalledWith("acme", "cs-1", expect.any(AbortSignal));
    expect(screen.getByRole("button", { name: "AI panel" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );

    fireEvent.click(within(panel).getByRole("button", { name: "Close AI panel" }));

    expect(onChangeSetKeyChange).toHaveBeenCalledWith(null);
    await waitFor(() =>
      expect(screen.queryByRole("complementary", { name: "AI" })).not.toBeInTheDocument()
    );
  });

  it("keeps the panel open on the list when leaving a deep-linked change set", async () => {
    vi.mocked(aiApi.fetchAiChangeSets).mockResolvedValue([changeSetDetail]);
    const { onChangeSetKeyChange } = renderMetrics({ mcpEnabled: false, changeSetKey: "cs-1" });

    const panel = screen.getByRole("complementary", { name: "AI" });
    await within(panel).findByRole("heading", { name: "Revenue values" });
    fireEvent.click(within(panel).getByRole("button", { name: "Back to change sets" }));

    expect(onChangeSetKeyChange).toHaveBeenLastCalledWith(null);
    expect(await within(panel).findByRole("list", { name: "AI change sets" })).toBeVisible();
    expect(screen.getByRole("complementary", { name: "AI" })).toBe(panel);
    expect(screen.getByRole("button", { name: "AI panel" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
  });

  it("warns before an apply that would discard unsaved grid changes", async () => {
    renderMetrics({ mcpEnabled: true, changeSetKey: "cs-1" });

    fireEvent.change(await screen.findByLabelText("Revenue 2030-01-01"), {
      target: { value: "1500" }
    });
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));

    expect(screen.getByRole("alertdialog", { name: "Confirm apply" })).toHaveTextContent(
      "The metrics grid has unsaved changes in 1 timeserie(s)"
    );
  });

  it("opens a deep-linked change set before a scenario is selected", async () => {
    renderMetrics({ mcpEnabled: true, changeSetKey: "cs-1", scenario: null });

    expect(
      screen.getByText("Select a scenario in Scenarios to activate this tab.")
    ).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Revenue values" })).toBeVisible();
    expect(timeseriesApi.fetchTimeseries).not.toHaveBeenCalled();
  });

  it("selects a change set from the list through the change-set link", async () => {
    vi.mocked(aiApi.fetchAiChangeSets).mockResolvedValue([changeSetDetail]);
    const { onChangeSetKeyChange } = renderMetrics({ mcpEnabled: true });

    fireEvent.click(await screen.findByRole("button", { name: "AI panel" }));
    fireEvent.click(await screen.findByRole("button", { name: /Revenue values/ }));

    expect(onChangeSetKeyChange).toHaveBeenCalledWith("cs-1");
    expect(await screen.findByRole("heading", { name: "Revenue values" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Back to change sets" }));

    expect(onChangeSetKeyChange).toHaveBeenLastCalledWith(null);
    expect(await screen.findByRole("list", { name: "AI change sets" })).toBeVisible();
  });

  it("reloads the metrics grid after an apply", async () => {
    vi.mocked(aiApi.applyAiChangeSet).mockResolvedValue({
      changeSet: { ...changeSetDetail, status: "applied" },
      operations: [
        {
          position: 0,
          opType: "set_timeserie_values",
          status: "ok",
          scenarioKey: "future",
          key: "revenue"
        }
      ],
      refs: {}
    });
    renderMetrics({ mcpEnabled: true, changeSetKey: "cs-1" });

    await screen.findByRole("rowheader", { name: /Revenue/ });
    expect(timeseriesApi.fetchTimeseries).toHaveBeenCalledTimes(1);
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm apply" }));

    expect(await screen.findByText("Change set applied")).toBeVisible();
    await waitFor(() => expect(timeseriesApi.fetchTimeseries).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("list", { name: "Created or changed keys" })).toHaveTextContent(
      "#0 set_timeserie_values: revenue in scenario future"
    );
  });
});
