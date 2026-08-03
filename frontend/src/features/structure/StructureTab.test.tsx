import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within
} from "@testing-library/react";
import type { ContextType } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as structureApi from "../../api/orgTwinStructure";
import type { GraphDto, GraphTypeCatalogDto } from "../../api/orgTwinStructure";
import * as timeseriesApi from "../../api/timeseries";
import {
  WorkspaceSelectionContext
} from "../../workspace/WorkspaceSelectionContext";
import StructureTab from "./StructureTab";

vi.mock("../../api/orgTwinStructure", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/orgTwinStructure")>();
  return {
    ...actual,
    fetchGraph: vi.fn(),
    fetchGraphTypeCatalog: vi.fn(),
    createGraphNode: vi.fn(),
    updateGraphNode: vi.fn(),
    deleteGraphNode: vi.fn(),
    createGraphEdge: vi.fn(),
    updateGraphEdge: vi.fn(),
    deleteGraphEdge: vi.fn(),
    bulkUpdatePositions: vi.fn()
  };
});

vi.mock("../../api/timeseries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/timeseries")>();
  return {
    ...actual,
    createTimeserie: vi.fn(),
    fetchTimeserie: vi.fn(),
    fetchTimeserieExists: vi.fn(),
    deleteTimeserie: vi.fn()
  };
});

vi.mock("./GraphViewer", () => ({
  default: (props: {
    centerNodeRequest: { nodeId: string; requestId: number } | null;
    onSelect: (selection: { kind: "node" | "edge"; id: string } | null) => void;
    onNodePositionChange: (nodeId: string, position: { x: number; y: number }) => void;
    onViewportCenterChange: (position: { x: number; y: number }) => void;
  }) => (
    <div data-testid="graph-viewer">
      <span data-testid="center-node-request">
        {props.centerNodeRequest
          ? `${props.centerNodeRequest.nodeId}:${props.centerNodeRequest.requestId}`
          : "none"}
      </span>
      <button
        type="button"
        onClick={() => props.onViewportCenterChange({ x: 250, y: 300 })}
      >
        Set graph center
      </button>
      <button
        type="button"
        onClick={() => props.onNodePositionChange("node_ceo", { x: 44, y: 55 })}
      >
        Move CEO
      </button>
      <button
        type="button"
        onClick={() => props.onSelect({ kind: "node", id: "node_ceo" })}
      >
        Select CEO node in graph
      </button>
      <button
        type="button"
        onClick={() => props.onSelect({ kind: "node", id: "node_cfo" })}
      >
        Select CFO node in graph
      </button>
      <button
        type="button"
        onClick={() => props.onSelect({ kind: "node", id: "node_sales" })}
      >
        Select sales node in graph
      </button>
      <button
        type="button"
        onClick={() => props.onSelect({ kind: "node", id: "node_revenue" })}
      >
        Select revenue node in graph
      </button>
      <button
        type="button"
        onClick={() => props.onSelect({ kind: "edge", id: "edge_reports" })}
      >
        Select reports edge
      </button>
    </div>
  )
}));

const graph: GraphDto = {
  id: "future",
  name: "Future",
  description: "Future graph",
  nodes: [
    {
      id: "node_ceo",
      name: "CEO",
      description: "Chief executive",
      nodeTypeId: "nt_person",
      createDate: null,
      position: { x: 10, y: 20 },
      attributes: { level: 1 },
      timeserieId: null,
      timeserieSecondaryId: null
    },
    {
      id: "node_sales",
      name: "Sales",
      description: "Sales department",
      nodeTypeId: "nt_team",
      createDate: null,
      position: { x: 120, y: 20 },
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    },
    {
      id: "node_cfo",
      name: "CFO",
      description: "Finance lead",
      nodeTypeId: "nt_person",
      createDate: null,
      position: { x: 200, y: 20 },
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    },
    {
      id: "node_revenue",
      name: "Revenue",
      description: "Monthly revenue",
      nodeTypeId: "nt_metric",
      createDate: null,
      position: { x: 320, y: 20 },
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    }
  ],
  edges: [
    {
      id: "edge_reports",
      name: "Reports to",
      description: "",
      edgeTypeId: "et_reports_to",
      sourceNodeId: "node_sales",
      targetNodeId: "node_ceo",
      createDate: null,
      attributes: {}
    }
  ]
};

const catalog: GraphTypeCatalogDto = {
  nodeTypes: [
    {
      id: "nt_person",
      name: "person",
      displayName: "Person",
      color: "#dbeafe",
      shape: "roundrectangle",
      timeserieId: null,
      timeserieSecondaryId: null,
      timeserieIdRule: null
    },
    {
      id: "nt_team",
      name: "team",
      displayName: "Team",
      color: "#dcfce7",
      shape: "rectangle",
      timeserieId: null,
      timeserieSecondaryId: null,
      timeserieIdRule: null
    },
    {
      id: "nt_vendor",
      name: "vendor",
      displayName: "Vendor",
      color: "#fef3c7",
      shape: "rectangle",
      timeserieId: null,
      timeserieSecondaryId: null,
      timeserieIdRule: null
    },
    {
      id: "nt_metric",
      name: "metric",
      displayName: "Metric",
      color: "#fbcfe8",
      shape: "rectangle",
      timeserieId: "id1",
      timeserieSecondaryId: "id2",
      timeserieIdRule: "MEASURED_BY from Goal"
    }
  ],
  edgeTypes: [
    {
      id: "et_reports_to",
      name: "reports_to",
      displayName: "Reports to",
      style: "solid",
      sourceEnd: "none",
      targetEnd: "arrow"
    },
    {
      id: "et_partners_with",
      name: "partners_with",
      displayName: "Partners with",
      style: "dashed",
      sourceEnd: "none",
      targetEnd: "none"
    }
  ],
  allowedConnections: [
    {
      edgeTypeId: "et_reports_to",
      sourceNodeTypeId: "nt_person",
      targetNodeTypeId: "nt_person"
    },
    {
      edgeTypeId: "et_partners_with",
      sourceNodeTypeId: "nt_person",
      targetNodeTypeId: "nt_team"
    }
  ]
};

type WorkspaceValue = NonNullable<ContextType<typeof WorkspaceSelectionContext>>;

function workspaceValue(
  scenario: { id: string; name: string } = { id: "future", name: "Future" },
  orgState: { id: string; name: string; targetDate: string } = {
    id: "draft",
    name: "Draft",
    targetDate: "2026-07-01"
  }
): WorkspaceValue {
  return {
    selectedScenario: scenario,
    setSelectedScenario: vi.fn(),
    selectedOrgState: orgState,
    setSelectedOrgState: vi.fn()
  };
}

function renderStructureTab(value: WorkspaceValue = workspaceValue()) {
  return render(
    <WorkspaceSelectionContext.Provider value={value}>
      <StructureTab orgId="acme" />
    </WorkspaceSelectionContext.Provider>
  );
}

describe("StructureTab", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    vi.mocked(structureApi.fetchGraph).mockResolvedValue(graph);
    vi.mocked(structureApi.fetchGraphTypeCatalog).mockResolvedValue(catalog);
    vi.mocked(structureApi.createGraphNode).mockResolvedValue({
      id: "node_operations",
      name: "Operations",
      description: "",
      nodeTypeId: "nt_team",
      createDate: null,
      position: { x: 0, y: 0 },
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    });
    vi.mocked(structureApi.updateGraphNode).mockImplementation(
      async (_orgId, _scenarioId, _orgStateId, nodeId, payload) => {
        const node = graph.nodes.find((item) => item.id === nodeId) ?? graph.nodes[0];
        return {
          ...node,
          name: payload.name ?? node.name,
          description: payload.description ?? node.description,
          nodeTypeId: payload.nodeTypeId ?? node.nodeTypeId,
          position: payload.position ?? node.position,
          attributes: payload.attributes ?? node.attributes,
          timeserieId:
            payload.timeserieId === undefined ? node.timeserieId : payload.timeserieId,
          timeserieSecondaryId:
            payload.timeserieSecondaryId === undefined
              ? node.timeserieSecondaryId
              : payload.timeserieSecondaryId
        };
      }
    );
    vi.mocked(structureApi.deleteGraphNode).mockResolvedValue(undefined);
    vi.mocked(structureApi.deleteGraphEdge).mockResolvedValue(undefined);
    vi.mocked(structureApi.bulkUpdatePositions).mockResolvedValue({
      ...graph,
      nodes: graph.nodes.map((node) =>
        node.id === "node_ceo" ? { ...node, position: { x: 44, y: 55 } } : node
      )
    });
    vi.mocked(timeseriesApi.fetchTimeserieExists).mockImplementation(
      async (_orgId, _scenarioId, timeserieId) => ({
        id: timeserieId,
        exists: timeserieId === "id1"
      })
    );
    vi.mocked(timeseriesApi.createTimeserie).mockImplementation(
      async (_orgId, _scenarioId, payload) => ({
        id: payload.id,
        name: payload.name,
        description: payload.description ?? "",
        unit: payload.unit ?? "",
        timeUnit: payload.timeUnit,
        valueUnit: payload.valueUnit,
        values: []
      })
    );
    vi.mocked(timeseriesApi.deleteTimeserie).mockResolvedValue(undefined);
  });

  it("loads graph data and renders grouped node types", async () => {
    renderStructureTab();

    expect(await screen.findByRole("heading", { name: "Structure" })).toBeInTheDocument();
    const personRegion = await screen.findByRole("region", { name: "Person nodes" });
    expect(personRegion).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Team nodes" })).toBeInTheDocument();
    const vendorRegion = screen.getByRole("region", { name: "Vendor nodes" });
    expect(vendorRegion).toBeInTheDocument();
    expect(within(personRegion).getByText("(2)")).toBeInTheDocument();
    expect(
      within(personRegion).getByRole("button", { name: "Collapse Person nodes" })
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      within(vendorRegion).getByRole("button", { name: "Expand Vendor nodes" })
    ).toHaveAttribute("aria-expanded", "false");
    expect(within(vendorRegion).queryByText("No nodes")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CEO Chief executive" })).toBeInTheDocument();
    expect(personRegion.querySelector(".structure-type-swatch")).toBeNull();
    expect(personRegion.querySelector(".structure-type-tag")).toHaveStyle({
      backgroundColor: "rgb(219, 234, 254)"
    });
    expect(structureApi.fetchGraph).toHaveBeenCalledWith(
      "acme",
      "future",
      "draft",
      expect.any(AbortSignal)
    );
  });

  it("shows empty node types and lets the plus button preselect create type", async () => {
    renderStructureTab();

    const vendorRegion = await screen.findByRole("region", { name: "Vendor nodes" });

    fireEvent.click(
      within(vendorRegion).getByRole("button", { name: "Expand Vendor nodes" })
    );
    expect(within(vendorRegion).getByText("No nodes")).toBeInTheDocument();

    fireEvent.click(
      within(vendorRegion).getByRole("button", { name: "Create Vendor node" })
    );

    const createNodePanel = screen.getByRole("region", { name: "Create node" });
    expect(within(createNodePanel).getByLabelText("Type")).toHaveValue("nt_vendor");
  });

  it("requests graph centering only when nodes are selected from the side panel", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    expect(screen.getByTestId("center-node-request")).toHaveTextContent("none");

    fireEvent.click(screen.getByRole("button", { name: "Select sales node in graph" }));
    expect(screen.getByTestId("center-node-request")).toHaveTextContent("none");

    fireEvent.click(screen.getByRole("button", { name: "CEO Chief executive" }));
    expect(screen.getByTestId("center-node-request")).toHaveTextContent("node_ceo:1");

    fireEvent.click(screen.getByRole("button", { name: "CEO Chief executive" }));
    expect(screen.getByTestId("center-node-request")).toHaveTextContent("node_ceo:2");
  });

  it("creates a node from create mode", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(screen.getByRole("button", { name: "Set graph center" }));
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    const createNodePanel = screen.getByRole("region", { name: "Create node" });
    const createEdgePanel = screen.getByRole("region", { name: "Create edge" });
    expect(within(createNodePanel).queryByLabelText("Node id")).not.toBeInTheDocument();
    expect(within(createNodePanel).queryByLabelText("X")).not.toBeInTheDocument();
    expect(within(createNodePanel).queryByLabelText("Y")).not.toBeInTheDocument();
    expect(within(createNodePanel).queryByLabelText("Attributes")).not.toBeInTheDocument();
    expect(within(createEdgePanel).queryByLabelText("Edge id")).not.toBeInTheDocument();
    expect(within(createEdgePanel).queryByLabelText("Attributes")).not.toBeInTheDocument();
    fireEvent.change(within(createNodePanel).getByLabelText("Name"), {
      target: { value: "Operations" }
    });
    fireEvent.click(within(createNodePanel).getByRole("button", { name: "Create node" }));

    await waitFor(() => {
      expect(structureApi.createGraphNode).toHaveBeenCalledWith(
        "acme",
        "future",
        "draft",
        expect.objectContaining({
          id: "node_operations",
          name: "Operations",
          nodeTypeId: "nt_person",
          position: { x: 250, y: 300 }
        })
      );
    });
  });

  it("starts edge creation with no preselected nodes and shows the click hint", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    const createEdgePanel = screen.getByRole("region", { name: "Create edge" });
    expect(within(createEdgePanel).getByText("Click two nodes to connect, or use the dropdown menus...")).toBeInTheDocument();
    expect(within(createEdgePanel).getByLabelText("Source")).toHaveValue("");
    expect(within(createEdgePanel).getByLabelText("Target")).toHaveValue("");
  });

  it("updates create-edge source and target from the last two graph node clicks", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    const createEdgePanel = screen.getByRole("region", { name: "Create edge" });
    const sourceSelect = within(createEdgePanel).getByLabelText("Source");
    const targetSelect = within(createEdgePanel).getByLabelText("Target");
    const typeSelect = within(createEdgePanel).getByLabelText("Type");

    fireEvent.click(screen.getByRole("button", { name: "Select CEO node in graph" }));
    expect(sourceSelect).toHaveValue("node_ceo");
    expect(targetSelect).toHaveValue("");

    fireEvent.click(screen.getByRole("button", { name: "Select CEO node in graph" }));
    expect(sourceSelect).toHaveValue("node_ceo");
    expect(targetSelect).toHaveValue("");

    fireEvent.click(screen.getByRole("button", { name: "Select sales node in graph" }));
    expect(sourceSelect).toHaveValue("node_ceo");
    expect(targetSelect).toHaveValue("node_sales");
    expect(typeSelect).toHaveValue("et_partners_with");
    expect(
      within(createEdgePanel).queryByText("Click two nodes to connect, or use the dropdown menus...")
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Select CEO node in graph" }));
    expect(sourceSelect).toHaveValue("node_sales");
    expect(targetSelect).toHaveValue("node_ceo");
    expect(typeSelect).toHaveValue("");
    expect(within(createEdgePanel).getByText("No allowed edge types")).toBeInTheDocument();
    expect(sourceSelect).not.toBeDisabled();
    expect(targetSelect).not.toBeDisabled();
  });

  it("still allows choosing create-edge source and target from the dropdowns", async () => {
    vi.mocked(structureApi.createGraphEdge).mockResolvedValue({
      id: "edge_partners",
      name: "Partners with",
      description: "",
      edgeTypeId: "et_partners_with",
      sourceNodeId: "node_ceo",
      targetNodeId: "node_sales",
      createDate: null,
      attributes: {}
    });

    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    const createEdgePanel = screen.getByRole("region", { name: "Create edge" });
    fireEvent.change(within(createEdgePanel).getByLabelText("Name"), {
      target: { value: "Partners with" }
    });
    fireEvent.change(within(createEdgePanel).getByLabelText("Source"), {
      target: { value: "node_ceo" }
    });
    fireEvent.change(within(createEdgePanel).getByLabelText("Target"), {
      target: { value: "node_sales" }
    });

    fireEvent.click(within(createEdgePanel).getByRole("button", { name: "Create edge" }));

    await waitFor(() => {
      expect(structureApi.createGraphEdge).toHaveBeenCalledWith(
        "acme",
        "future",
        "draft",
        expect.objectContaining({
          id: "edge_partners_with",
          name: "Partners with",
          edgeTypeId: "et_partners_with",
          sourceNodeId: "node_ceo",
          targetNodeId: "node_sales"
        })
      );
    });
  });

  it("filters create-edge types to the allowed source and target combination", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    const createEdgePanel = screen.getByRole("region", { name: "Create edge" });
    const typeSelect = within(createEdgePanel).getByLabelText("Type");

    fireEvent.click(screen.getByRole("button", { name: "Select CEO node in graph" }));
    fireEvent.click(screen.getByRole("button", { name: "Select CFO node in graph" }));

    const options = within(typeSelect).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["Reports to"]);
    expect(typeSelect).toHaveValue("et_reports_to");
  });

  it("shows timeserie mode only for selected timeseries-capable nodes", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    const modeGroup = screen.getByRole("group", { name: "Structure mode" });
    expect(
      within(modeGroup)
        .getAllByRole("button")
        .map((button) => button.textContent)
    ).toEqual(["Create", "Show & Edit", "AI Assistant"]);

    fireEvent.click(screen.getByRole("button", { name: "Select CEO node in graph" }));
    expect(within(modeGroup).queryByRole("button", { name: "Timeserie" })).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: "Select revenue node in graph" })
    );
    expect(
      within(modeGroup)
        .getAllByRole("button")
        .map((button) => button.textContent)
    ).toEqual(["Create", "Show & Edit", "Timeserie", "AI Assistant"]);

    fireEvent.click(screen.getByRole("button", { name: "Select reports edge" }));
    expect(within(modeGroup).queryByRole("button", { name: "Timeserie" })).toBeNull();
  });

  it("falls back to edit mode after leaving a timeseries-capable node", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(
      screen.getByRole("button", { name: "Select revenue node in graph" })
    );
    fireEvent.click(screen.getByRole("button", { name: "Timeserie" }));
    expect(screen.getByRole("heading", { name: "Timeserie" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Select reports edge" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Edit edge" })).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Show & Edit" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
  });

  it("saves and clears selected node timeserie links", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(
      screen.getByRole("button", { name: "Select revenue node in graph" })
    );
    fireEvent.click(screen.getByRole("button", { name: "Timeserie" }));

    const panel = screen.getByRole("region", { name: "Timeserie" });
    fireEvent.change(within(panel).getByLabelText("Primary link"), {
      target: { value: "id1" }
    });
    fireEvent.change(within(panel).getByLabelText("Secondary link"), {
      target: { value: "id2" }
    });
    fireEvent.click(within(panel).getByRole("button", { name: "Save links" }));

    await waitFor(() => {
      expect(structureApi.updateGraphNode).toHaveBeenCalledWith(
        "acme",
        "future",
        "draft",
        "node_revenue",
        { timeserieId: "id1", timeserieSecondaryId: "id2" }
      );
    });

    vi.mocked(structureApi.updateGraphNode).mockClear();
    await waitFor(() => {
      expect(
        within(screen.getByRole("region", { name: "Timeserie" })).getByLabelText(
          "Primary link"
        )
      ).toHaveValue("id1");
      expect(
        within(screen.getByRole("region", { name: "Timeserie" })).getByLabelText(
          "Secondary link"
        )
      ).toHaveValue("id2");
    });
    const updatedPanel = screen.getByRole("region", { name: "Timeserie" });
    fireEvent.change(within(updatedPanel).getByLabelText("Primary link"), {
      target: { value: "" }
    });
    fireEvent.change(within(updatedPanel).getByLabelText("Secondary link"), {
      target: { value: "" }
    });
    fireEvent.click(within(updatedPanel).getByRole("button", { name: "Save links" }));

    await waitFor(() => {
      expect(structureApi.updateGraphNode).toHaveBeenCalledWith(
        "acme",
        "future",
        "draft",
        "node_revenue",
        { timeserieId: null, timeserieSecondaryId: null }
      );
    });
  });

  it("shows effective timeserie states and creates a missing record", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(
      screen.getByRole("button", { name: "Select revenue node in graph" })
    );
    fireEvent.click(screen.getByRole("button", { name: "Timeserie" }));

    const panel = screen.getByRole("region", { name: "Timeserie" });
    const primary = within(panel).getByRole("region", { name: "Primary timeserie" });
    const secondary = within(panel).getByRole("region", {
      name: "Secondary timeserie"
    });

    await waitFor(() => {
      expect(within(primary).getByText("Exists")).toBeInTheDocument();
      expect(within(secondary).getByText("Missing")).toBeInTheDocument();
    });

    fireEvent.change(within(secondary).getByLabelText("Name"), {
      target: { value: "Revenue secondary" }
    });
    fireEvent.change(within(secondary).getByLabelText("Unit"), {
      target: { value: "%" }
    });
    fireEvent.change(within(secondary).getByLabelText("Time unit"), {
      target: { value: "year" }
    });
    fireEvent.change(within(secondary).getByLabelText("Value unit"), {
      target: { value: "boolean" }
    });
    fireEvent.click(
      within(secondary).getByRole("button", { name: "Create timeserie" })
    );

    await waitFor(() => {
      expect(timeseriesApi.createTimeserie).toHaveBeenCalledWith(
        "acme",
        "future",
        {
          id: "id2",
          name: "Revenue secondary",
          description: null,
          unit: "%",
          timeUnit: "year",
          valueUnit: "boolean"
        }
      );
      expect(within(secondary).getByText("Exists")).toBeInTheDocument();
    });
  });

  it("deletes existing timeseries only after confirmation", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(
      screen.getByRole("button", { name: "Select revenue node in graph" })
    );
    fireEvent.click(screen.getByRole("button", { name: "Timeserie" }));

    const panel = screen.getByRole("region", { name: "Timeserie" });
    const primary = within(panel).getByRole("region", { name: "Primary timeserie" });
    await waitFor(() => {
      expect(within(primary).getByText("Exists")).toBeInTheDocument();
    });

    fireEvent.click(within(primary).getByRole("button", { name: "Delete timeserie" }));
    expect(
      within(primary).getByText("Are you sure you want to delete this timeserie?")
    ).toBeInTheDocument();

    fireEvent.click(within(primary).getByRole("button", { name: "No" }));
    expect(timeseriesApi.deleteTimeserie).not.toHaveBeenCalled();

    fireEvent.click(within(primary).getByRole("button", { name: "Delete timeserie" }));
    fireEvent.click(within(primary).getByRole("button", { name: "Yes" }));

    await waitFor(() => {
      expect(timeseriesApi.deleteTimeserie).toHaveBeenCalledWith(
        "acme",
        "future",
        "id1"
      );
      expect(within(primary).getByText("Missing")).toBeInTheDocument();
    });
  });

  it("blocks self-referencing create edges and shows the hint on the submit control", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    const createEdgePanel = screen.getByRole("region", { name: "Create edge" });
    fireEvent.change(within(createEdgePanel).getByLabelText("Name"), {
      target: { value: "Reports to self" }
    });
    fireEvent.change(within(createEdgePanel).getByLabelText("Source"), {
      target: { value: "node_ceo" }
    });
    fireEvent.change(within(createEdgePanel).getByLabelText("Target"), {
      target: { value: "node_ceo" }
    });

    const createButton = within(createEdgePanel).getByRole("button", { name: "Create edge" });
    expect(createButton).toBeDisabled();
    expect(createButton.parentElement).toHaveAttribute(
      "title",
      "Self referencing edges not allowed"
    );
  });

  it("debounces drag position persistence", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Move CEO" }));

    act(() => {
      vi.advanceTimersByTime(399);
    });
    expect(structureApi.bulkUpdatePositions).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(1);
      await Promise.resolve();
    });

    expect(structureApi.bulkUpdatePositions).toHaveBeenCalledWith(
      "acme",
      "future",
      "draft",
      {
        positions: [{ nodeId: "node_ceo", x: 44, y: 55 }]
      }
    );
    vi.useRealTimers();
  });

  it("clears pending drag position persistence when workspace context changes", async () => {
    const { rerender } = renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Move CEO" }));

    rerender(
      <WorkspaceSelectionContext.Provider
        value={workspaceValue(
          { id: "alternate", name: "Alternate" },
          { id: "target", name: "Target", targetDate: "2026-08-01" }
        )}
      >
        <StructureTab orgId="acme" />
      </WorkspaceSelectionContext.Provider>
    );

    await act(async () => {
      vi.advanceTimersByTime(400);
      await Promise.resolve();
    });

    expect(structureApi.bulkUpdatePositions).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("confirms selected node deletion with yes and no buttons", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(screen.getByRole("button", { name: "CEO Chief executive" }));
    expect(screen.getByRole("heading", { name: "Edit node" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete selected node" }));
    expect(
      screen.getByText("Are you sure you want to delete the selected node?")
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "No" }));
    expect(structureApi.deleteGraphNode).not.toHaveBeenCalled();
    expect(
      screen.queryByText("Are you sure you want to delete the selected node?")
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete selected node" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));

    await waitFor(() => {
      expect(structureApi.deleteGraphNode).toHaveBeenCalledWith(
        "acme",
        "future",
        "draft",
        "node_ceo"
      );
    });
  });

  it("confirms selected edge deletion with yes and no buttons", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(screen.getByRole("button", { name: "Show & Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Select reports edge" }));
    expect(screen.getByRole("heading", { name: "Edit edge" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete selected edge" }));
    expect(
      screen.getByText("Are you sure you want to delete the selected edge?")
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "No" }));
    expect(structureApi.deleteGraphEdge).not.toHaveBeenCalled();
    expect(
      screen.queryByText("Are you sure you want to delete the selected edge?")
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete selected edge" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));

    await waitFor(() => {
      expect(structureApi.deleteGraphEdge).toHaveBeenCalledWith(
        "acme",
        "future",
        "draft",
        "edge_reports"
      );
    });
  });
});
