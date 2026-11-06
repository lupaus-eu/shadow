import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ContextType } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as structureApi from "../../api/orgTwinStructure";
import type { GraphDto, GraphTypeCatalogDto } from "../../api/orgTwinStructure";
import * as scenariosApi from "../../api/scenarios";
import * as timeseriesApi from "../../api/timeseries";
import { WorkspaceSelectionContext } from "../../workspace/WorkspaceSelectionContext";
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

vi.mock("../../api/scenarios", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/scenarios")>();
  return {
    ...actual,
    fetchOrgStates: vi.fn()
  };
});

vi.mock("../../api/timeseries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/timeseries")>();
  return {
    ...actual,
    createTimeserie: vi.fn(),
    fetchTimeserieExists: vi.fn(),
    fetchTimeserieSummaries: vi.fn(),
    fetchTimeseries: vi.fn(),
    deleteTimeserie: vi.fn()
  };
});

vi.mock("./GraphViewer", () => ({
  default: (props: {
    graph: GraphDto | null;
    endingNodeIds: ReadonlySet<string>;
    endingEdgeIds: ReadonlySet<string>;
    centerNodeRequest: { nodeId: string; requestId: number } | null;
    onSelect: (selection: { kind: "node" | "edge"; id: string } | null) => void;
    onNodePositionChange: (nodeId: string, position: { x: number; y: number }) => void;
    onViewportCenterChange: (position: { x: number; y: number }) => void;
  }) => (
    <div data-testid="graph-viewer">
      <span data-testid="graph-node-ids">
        {props.graph?.nodes.map((node) => node.id).join(",") ?? ""}
      </span>
      <span data-testid="graph-edge-ids">
        {props.graph?.edges.map((edge) => edge.id).join(",") ?? ""}
      </span>
      <span data-testid="ending-node-ids">{[...props.endingNodeIds].join(",")}</span>
      <span data-testid="ending-edge-ids">{[...props.endingEdgeIds].join(",")}</span>
      <span data-testid="center-node-request">
        {props.centerNodeRequest
          ? `${props.centerNodeRequest.nodeId}:${props.centerNodeRequest.requestId}`
          : "none"}
      </span>
      <button type="button" onClick={() => props.onViewportCenterChange({ x: 250, y: 300 })}>
        Set graph center
      </button>
      <button
        type="button"
        onClick={() => props.onNodePositionChange("node_ceo", { x: 44, y: 55 })}
      >
        Move CEO
      </button>
      <button type="button" onClick={() => props.onSelect({ kind: "node", id: "node_ceo" })}>
        Select CEO node in graph
      </button>
      <button type="button" onClick={() => props.onSelect({ kind: "node", id: "node_cfo" })}>
        Select CFO node in graph
      </button>
      <button type="button" onClick={() => props.onSelect({ kind: "node", id: "node_sales" })}>
        Select sales node in graph
      </button>
      <button type="button" onClick={() => props.onSelect({ kind: "node", id: "node_revenue" })}>
        Select revenue node in graph
      </button>
      <button type="button" onClick={() => props.onSelect({ kind: "edge", id: "edge_reports" })}>
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
      createDate: "2026-01-01",
      deleteDate: null,
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
      deleteDate: null,
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
      deleteDate: null,
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
      deleteDate: null,
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
      createDate: "2026-01-01",
      deleteDate: null,
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

const ruleGraph: GraphDto = {
  ...graph,
  nodes: [
    ...graph.nodes,
    {
      id: "node_goal",
      name: "Grow revenue",
      description: "Revenue growth goal",
      nodeTypeId: "nt_goal",
      createDate: null,
      deleteDate: null,
      position: { x: 260, y: 20 },
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    }
  ],
  edges: [
    ...graph.edges,
    {
      id: "edge_team_goal",
      name: "Has goal",
      description: "",
      edgeTypeId: "et_has",
      sourceNodeId: "node_sales",
      targetNodeId: "node_goal",
      createDate: null,
      deleteDate: null,
      attributes: {}
    },
    {
      id: "edge_goal_metric",
      name: "Measures",
      description: "",
      edgeTypeId: "et_has",
      sourceNodeId: "node_goal",
      targetNodeId: "node_revenue",
      createDate: null,
      deleteDate: null,
      attributes: {}
    }
  ]
};

const ruleCatalog: GraphTypeCatalogDto = {
  ...catalog,
  nodeTypes: [
    ...catalog.nodeTypes,
    {
      id: "nt_goal",
      name: "goal",
      displayName: "Goal",
      color: "#e9d5ff",
      shape: "rectangle",
      timeserieId: null,
      timeserieSecondaryId: null,
      timeserieIdRule: null
    }
  ],
  edgeTypes: [
    ...catalog.edgeTypes,
    {
      id: "et_has",
      name: "has",
      displayName: "Has",
      style: "solid",
      sourceEnd: "none",
      targetEnd: "arrow"
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
    setSelectedOrgState: vi.fn(),
    setWorkspaceSelection: vi.fn()
  };
}

function renderStructureTab(value: WorkspaceValue = workspaceValue()) {
  return render(
    <WorkspaceSelectionContext.Provider value={value}>
      <StructureTab orgId="acme" />
    </WorkspaceSelectionContext.Provider>
  );
}

// Source and Target are searchable dropdowns that show the selected node as text.
function edgeNodeSelect(panel: HTMLElement, label: "Source" | "Target") {
  return within(panel).getByLabelText(label);
}

function edgeNodeOptions(panel: HTMLElement) {
  return within(within(panel).getByRole("listbox")).getAllByRole("option");
}

function chooseEdgeNode(panel: HTMLElement, label: "Source" | "Target", nodeName: string) {
  fireEvent.click(edgeNodeSelect(panel, label));
  const option = edgeNodeOptions(panel).find((item) => item.textContent === nodeName);
  if (!option) throw new Error(`No ${label} option ${nodeName}`);
  fireEvent.click(option);
}

const timeserieLinkRegion = () =>
  screen.getByRole("region", { name: "Link to existing timeserie(s)" });
const timeserieEditRegion = () => screen.getByRole("region", { name: "Create/edit timeserie(s)" });

async function chooseTimeserieLink(slot: "Primary" | "Secondary", timeserieId: string) {
  const select = within(timeserieLinkRegion()).getByLabelText(`${slot} link`);
  await waitFor(() => expect(select).toBeEnabled());
  fireEvent.click(select);
  const listbox = within(timeserieLinkRegion()).getByRole("listbox");
  fireEvent.click(within(listbox).getByRole("option", { name: new RegExp(`^${timeserieId} – `) }));
}

function openTimeseriePanel() {
  fireEvent.click(screen.getByRole("button", { name: "Select revenue node in graph" }));
  fireEvent.click(screen.getByRole("button", { name: "Timeserie" }));
}

describe("StructureTab", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    vi.mocked(structureApi.fetchGraph).mockResolvedValue(graph);
    vi.mocked(structureApi.fetchGraphTypeCatalog).mockResolvedValue(catalog);
    vi.mocked(scenariosApi.fetchOrgStates).mockResolvedValue([]);
    vi.mocked(structureApi.createGraphNode).mockResolvedValue({
      id: "node_operations",
      name: "Operations",
      description: "",
      nodeTypeId: "nt_team",
      createDate: null,
      deleteDate: null,
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
          timeserieId: payload.timeserieId === undefined ? node.timeserieId : payload.timeserieId,
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
        exists: timeserieId === "id1" || timeserieId === "id3",
        shortName: timeserieId === "id1" ? "revenue_monthly" : ""
      })
    );
    vi.mocked(timeseriesApi.fetchTimeserieSummaries).mockResolvedValue(
      [
        ["id1", "Revenue"],
        ["id3", "Revenue target"]
      ].map(([id, name]) => ({
        id,
        name,
        description: "",
        unit: "",
        timeUnit: "month",
        valueUnit: "number"
      }))
    );
    vi.mocked(timeseriesApi.createTimeserie).mockImplementation(
      async (_orgId, _scenarioId, payload) => ({
        id: payload.id,
        name: payload.name,
        shortName: payload.shortName ?? "",
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

    fireEvent.click(within(vendorRegion).getByRole("button", { name: "Expand Vendor nodes" }));
    expect(within(vendorRegion).getByText("No nodes")).toBeInTheDocument();

    fireEvent.click(within(vendorRegion).getByRole("button", { name: "Create Vendor node" }));

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

  it("limits node and edge names to 60 characters", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    for (const panelName of ["Create node", "Create edge"]) {
      const panel = screen.getByRole("region", { name: panelName });
      const nameInput = within(panel).getByLabelText("Name");
      expect(nameInput).toHaveAttribute("maxLength", "60");
      expect(nameInput).toHaveAccessibleDescription("Max 60 characters.");
      // The app's code-point check decides, not the browser's code-unit maxlength.
      expect(nameInput.closest("form")).toHaveAttribute("novalidate");
    }
  });

  it("blocks saving a stored name longer than 60 characters until it is shortened", async () => {
    const longName = "C".repeat(61);
    vi.mocked(structureApi.fetchGraph).mockResolvedValue({
      ...graph,
      nodes: graph.nodes.map((node) =>
        node.id === "node_ceo" ? { ...node, name: longName } : node
      ),
      edges: graph.edges.map((edge) =>
        edge.id === "edge_reports" ? { ...edge, name: longName } : edge
      )
    });
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(screen.getByRole("button", { name: /Chief executive/ }));
    const editNodePanel = screen.getByRole("region", { name: "Edit node" });
    const nameInput = within(editNodePanel).getByLabelText("Name");
    const saveButton = within(editNodePanel).getByRole("button", { name: "Save node" });
    expect(nameInput).toHaveValue(longName);
    expect(nameInput).toHaveAttribute("aria-invalid", "true");
    expect(nameInput).toHaveAccessibleDescription("Name must be at most 60 characters.");
    expect(saveButton).toBeDisabled();

    fireEvent.change(nameInput, { target: { value: "CEO" } });
    expect(nameInput).not.toHaveAttribute("aria-invalid");
    expect(nameInput).toHaveAccessibleDescription("Max 60 characters.");
    expect(saveButton).toBeEnabled();
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(structureApi.updateGraphNode).toHaveBeenCalledWith(
        "acme",
        "future",
        "draft",
        "node_ceo",
        expect.objectContaining({ name: "CEO" })
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Select reports edge" }));
    const editEdgePanel = screen.getByRole("region", { name: "Edit edge" });
    expect(within(editEdgePanel).getByLabelText("Name")).toHaveAccessibleDescription(
      "Name must be at most 60 characters."
    );
    expect(within(editEdgePanel).getByRole("button", { name: "Save edge" })).toBeDisabled();
    fireEvent.change(within(editEdgePanel).getByLabelText("Name"), {
      target: { value: "Reports to" }
    });
    expect(within(editEdgePanel).getByRole("button", { name: "Save edge" })).toBeEnabled();
  });

  it("starts edge creation with no preselected nodes and shows the click hint", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    const createEdgePanel = screen.getByRole("region", { name: "Create edge" });
    expect(
      within(createEdgePanel).getByText("Click two nodes to connect, or use the dropdown menus...")
    ).toBeInTheDocument();
    expect(edgeNodeSelect(createEdgePanel, "Source")).toHaveTextContent("Select source node");
    expect(edgeNodeSelect(createEdgePanel, "Target")).toHaveTextContent("Select target node");
  });

  it("updates create-edge source and target from the last two graph node clicks", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    const createEdgePanel = screen.getByRole("region", { name: "Create edge" });
    const sourceSelect = edgeNodeSelect(createEdgePanel, "Source");
    const targetSelect = edgeNodeSelect(createEdgePanel, "Target");
    const typeSelect = within(createEdgePanel).getByLabelText("Type");

    fireEvent.click(screen.getByRole("button", { name: "Select CEO node in graph" }));
    expect(sourceSelect).toHaveTextContent("CEO");
    expect(targetSelect).toHaveTextContent("Select target node");

    fireEvent.click(screen.getByRole("button", { name: "Select CEO node in graph" }));
    expect(sourceSelect).toHaveTextContent("CEO");
    expect(targetSelect).toHaveTextContent("Select target node");

    fireEvent.click(screen.getByRole("button", { name: "Select sales node in graph" }));
    expect(sourceSelect).toHaveTextContent("CEO");
    expect(targetSelect).toHaveTextContent("Sales");
    expect(typeSelect).toHaveValue("et_partners_with");
    expect(
      within(createEdgePanel).queryByText(
        "Click two nodes to connect, or use the dropdown menus..."
      )
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Select CEO node in graph" }));
    expect(sourceSelect).toHaveTextContent("Sales");
    expect(targetSelect).toHaveTextContent("CEO");
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
      deleteDate: null,
      attributes: {}
    });

    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    const createEdgePanel = screen.getByRole("region", { name: "Create edge" });
    fireEvent.change(within(createEdgePanel).getByLabelText("Name"), {
      target: { value: "Partners with" }
    });
    chooseEdgeNode(createEdgePanel, "Source", "CEO");
    expect(edgeNodeSelect(createEdgePanel, "Source")).toHaveTextContent("CEO");

    fireEvent.click(edgeNodeSelect(createEdgePanel, "Target"));
    const targetSearch = within(createEdgePanel).getByRole("combobox", {
      name: "Search target nodes"
    });
    expect(edgeNodeOptions(createEdgePanel).map((option) => option.textContent)).toEqual([
      "CEO",
      "Sales",
      "CFO",
      "Revenue"
    ]);
    fireEvent.change(targetSearch, { target: { value: "SAL" } });
    expect(edgeNodeOptions(createEdgePanel).map((option) => option.textContent)).toEqual(["Sales"]);
    fireEvent.click(edgeNodeOptions(createEdgePanel)[0]);
    expect(edgeNodeSelect(createEdgePanel, "Target")).toHaveTextContent("Sales");
    expect(within(createEdgePanel).getByLabelText("Type")).toHaveValue("et_partners_with");

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

    fireEvent.click(screen.getByRole("button", { name: "Select revenue node in graph" }));
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

    openTimeseriePanel();
    expect(
      screen.getByRole("heading", { name: "Link to existing timeserie(s)" })
    ).toBeInTheDocument();

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
    openTimeseriePanel();

    await chooseTimeserieLink("Primary", "id3");
    await chooseTimeserieLink("Secondary", "id1");
    fireEvent.click(within(timeserieLinkRegion()).getByRole("button", { name: "Save link(s)" }));

    await waitFor(() => {
      expect(structureApi.updateGraphNode).toHaveBeenCalledWith(
        "acme",
        "future",
        "draft",
        "node_revenue",
        { timeserieId: "id3", timeserieSecondaryId: "id1" }
      );
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    vi.mocked(structureApi.updateGraphNode).mockClear();
    const primaryCard = () =>
      within(timeserieEditRegion()).getByRole("region", { name: "Primary timeserie" });
    await waitFor(() => {
      expect(within(primaryCard()).getByText("id3")).toBeInTheDocument();
    });
    expect(within(timeserieLinkRegion()).getByLabelText("Primary link")).toHaveTextContent(
      "Select existing timeseries id"
    );
    fireEvent.click(within(primaryCard()).getByRole("button", { name: "Unlink" }));

    await waitFor(() => {
      expect(structureApi.updateGraphNode).toHaveBeenCalledWith(
        "acme",
        "future",
        "draft",
        "node_revenue",
        { timeserieId: null }
      );
    });
    await waitFor(() => {
      expect(within(primaryCard()).getByText("Type default")).toBeInTheDocument();
    });
    expect(within(primaryCard()).getByText("id1")).toBeInTheDocument();
    expect(within(primaryCard()).queryByRole("button", { name: "Unlink" })).toBeNull();
  });

  it("shows rule context and the selected metric as an explicit link source", async () => {
    vi.mocked(structureApi.fetchGraph).mockResolvedValue(ruleGraph);
    vi.mocked(structureApi.fetchGraphTypeCatalog).mockResolvedValue(ruleCatalog);
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    openTimeseriePanel();

    const panel = timeserieLinkRegion();
    expect(panel).toHaveTextContent("Measured by from Grow revenue (Goal)");
    expect(panel).toHaveTextContent("Has goal from Sales (Team)");

    await chooseTimeserieLink("Primary", "id3");
    const primary = within(timeserieEditRegion()).getByRole("region", {
      name: "Primary timeserie"
    });
    expect(within(primary).getByText("Revenue (Metric)")).toBeInTheDocument();
  });

  it("shows an explicit missing rule-context fallback", async () => {
    vi.mocked(structureApi.fetchGraph).mockResolvedValue({
      ...graph,
      edges: [graph.edges[0]]
    });
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    openTimeseriePanel();

    expect(timeserieLinkRegion()).toHaveTextContent("Measured by from No linked goal");
  });

  it("shows an explicit ambiguous rule-context fallback", async () => {
    vi.mocked(structureApi.fetchGraph).mockResolvedValue({
      ...ruleGraph,
      nodes: [
        ...ruleGraph.nodes,
        {
          id: "node_goal_secondary",
          name: "Improve margin",
          description: "Secondary goal",
          nodeTypeId: "nt_goal",
          createDate: null,
          deleteDate: null,
          position: { x: 280, y: 80 },
          attributes: {},
          timeserieId: null,
          timeserieSecondaryId: null
        }
      ],
      edges: [
        ...ruleGraph.edges,
        {
          id: "edge_goal_secondary_metric",
          name: "Measures secondary",
          description: "",
          edgeTypeId: "et_has",
          sourceNodeId: "node_goal_secondary",
          targetNodeId: "node_revenue",
          createDate: null,
          deleteDate: null,
          attributes: {}
        }
      ]
    });
    vi.mocked(structureApi.fetchGraphTypeCatalog).mockResolvedValue(ruleCatalog);
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    openTimeseriePanel();

    expect(timeserieLinkRegion()).toHaveTextContent("Measured by from Multiple linked goals");
  });

  it("shows effective timeserie states and creates a missing record", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    openTimeseriePanel();

    const panel = timeserieEditRegion();
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
    fireEvent.change(within(secondary).getByLabelText("Short name"), {
      target: { value: "revenue_secondary" }
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
    fireEvent.click(within(secondary).getByRole("button", { name: "Create timeserie" }));

    await waitFor(() => {
      expect(timeseriesApi.createTimeserie).toHaveBeenCalledWith("acme", "future", {
        id: "id2",
        name: "Revenue secondary",
        shortName: "revenue_secondary",
        description: null,
        unit: "%",
        timeUnit: "year",
        valueUnit: "boolean"
      });
      expect(within(secondary).getByText("Exists")).toBeInTheDocument();
    });
  });

  it("deletes existing timeseries only after confirmation", async () => {
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    openTimeseriePanel();

    const panel = timeserieEditRegion();
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
      expect(timeseriesApi.deleteTimeserie).toHaveBeenCalledWith("acme", "future", "id1");
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
    chooseEdgeNode(createEdgePanel, "Source", "CEO");
    chooseEdgeNode(createEdgePanel, "Target", "CEO");
    expect(edgeNodeSelect(createEdgePanel, "Target")).toHaveTextContent("CEO");

    const createButton = within(createEdgePanel).getByRole("button", { name: "Create edge" });
    expect(createButton).toBeDisabled();
    expect(createButton.parentElement).toHaveAttribute(
      "title",
      "Self referencing edges not allowed"
    );
  });

  it("changes an edited edge's target through the searchable dropdown", async () => {
    vi.mocked(structureApi.updateGraphEdge).mockResolvedValue({
      ...graph.edges[0],
      targetNodeId: "node_cfo"
    });
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(screen.getByRole("button", { name: "Show & Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Select reports edge" }));
    const editEdgePanel = screen.getByRole("region", { name: "Edit edge" });
    expect(edgeNodeSelect(editEdgePanel, "Source")).toHaveTextContent("Sales");
    const targetSelect = edgeNodeSelect(editEdgePanel, "Target");
    expect(targetSelect).toHaveTextContent("CEO");

    fireEvent.keyDown(targetSelect, { key: "ArrowDown" });
    const targetSearch = within(editEdgePanel).getByRole("combobox", {
      name: "Search target nodes"
    });
    expect(targetSearch).toHaveFocus();
    expect(
      within(within(editEdgePanel).getByRole("listbox")).getByRole("option", { selected: true })
    ).toHaveTextContent("CEO");
    fireEvent.change(targetSearch, { target: { value: "c" } });
    fireEvent.keyDown(targetSearch, { key: "ArrowDown" });
    fireEvent.keyDown(targetSearch, { key: "Enter" });

    expect(targetSelect).toHaveTextContent("CFO");
    expect(targetSelect).toHaveFocus();
    expect(structureApi.updateGraphEdge).not.toHaveBeenCalled();
    fireEvent.click(within(editEdgePanel).getByRole("button", { name: "Save edge" }));

    await waitFor(() => {
      expect(structureApi.updateGraphEdge).toHaveBeenCalledWith(
        "acme",
        "future",
        "draft",
        "edge_reports",
        expect.objectContaining({ sourceNodeId: "node_sales", targetNodeId: "node_cfo" })
      );
    });
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

    expect(structureApi.bulkUpdatePositions).toHaveBeenCalledWith("acme", "future", "draft", {
      positions: [{ nodeId: "node_ceo", x: 44, y: 55 }]
    });
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

  it("refetches state-scoped data when workspace context changes in place", async () => {
    const { rerender } = renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });
    vi.mocked(structureApi.fetchGraph).mockClear();
    vi.mocked(structureApi.fetchGraphTypeCatalog).mockClear();

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

    await waitFor(() => {
      expect(structureApi.fetchGraph).toHaveBeenCalledWith(
        "acme",
        "alternate",
        "target",
        expect.any(AbortSignal)
      );
      expect(structureApi.fetchGraphTypeCatalog).toHaveBeenCalledWith(
        "acme",
        "alternate",
        "target",
        expect.any(AbortSignal)
      );
    });
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
      expect(structureApi.fetchGraph).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByTestId("graph-node-ids")).toHaveTextContent("node_ceo");
    expect(screen.getByTestId("graph-edge-ids")).toHaveTextContent("edge_reports");
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
      expect(structureApi.fetchGraph).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByTestId("graph-edge-ids")).toHaveTextContent("edge_reports");
  });

  it("removes a same-day deleted node and its connected edges locally", async () => {
    vi.mocked(structureApi.fetchGraph).mockResolvedValue({
      ...graph,
      nodes: graph.nodes.map((node) =>
        node.id === "node_ceo" ? { ...node, createDate: "2026-07-01" } : node
      )
    });
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(screen.getByRole("button", { name: "CEO Chief executive" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete selected node" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));

    await waitFor(() => {
      expect(screen.getByTestId("graph-node-ids")).not.toHaveTextContent("node_ceo");
      expect(screen.getByTestId("graph-edge-ids")).toBeEmptyDOMElement();
    });
    expect(structureApi.fetchGraph).toHaveBeenCalledTimes(1);
  });

  it("removes a same-day deleted edge locally", async () => {
    vi.mocked(structureApi.fetchGraph).mockResolvedValue({
      ...graph,
      edges: graph.edges.map((edge) => ({
        ...edge,
        createDate: "2026-07-01"
      }))
    });
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    fireEvent.click(screen.getByRole("button", { name: "Show & Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Select reports edge" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete selected edge" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));

    await waitFor(() => {
      expect(screen.getByTestId("graph-edge-ids")).toBeEmptyDOMElement();
    });
    expect(structureApi.fetchGraph).toHaveBeenCalledTimes(1);
  });

  describe("elements that end in the selected org state", () => {
    const orgStates = [
      { id: "state_1", name: "State 1", description: "", targetDate: "2026-01-01" },
      { id: "state_2", name: "State 2", description: "", targetDate: "2026-02-01" },
      { id: "state_3", name: "State 3", description: "", targetDate: "2026-03-01" }
    ];

    function endingGraph(deleteDate: string): GraphDto {
      return {
        ...graph,
        nodes: graph.nodes.map((node) => (node.id === "node_ceo" ? { ...node, deleteDate } : node)),
        edges: graph.edges.map((edge) =>
          edge.id === "edge_reports" ? { ...edge, createDate: "2026-01-01", deleteDate } : edge
        )
      };
    }

    function renderInState(index: number) {
      const orgState = orgStates[index];
      return renderStructureTab(
        workspaceValue(
          { id: "future", name: "Future" },
          { id: orgState.id, name: orgState.name, targetDate: orgState.targetDate }
        )
      );
    }

    beforeEach(() => {
      vi.mocked(scenariosApi.fetchOrgStates).mockResolvedValue(orgStates);
      vi.mocked(structureApi.fetchGraph).mockResolvedValue(endingGraph("2026-02-01"));
    });

    it("marks a node and edge removed in the selected org state", async () => {
      renderInState(1);

      await waitFor(() => {
        expect(screen.getByTestId("ending-node-ids")).toHaveTextContent("node_ceo");
        expect(screen.getByTestId("ending-edge-ids")).toHaveTextContent("edge_reports");
      });
      expect(scenariosApi.fetchOrgStates).toHaveBeenCalledWith(
        "acme",
        "future",
        expect.any(AbortSignal)
      );
      const ceo = screen.getByRole("button", { name: /^CEO Ends 2026-02-01/ });
      expect(within(ceo).getByText("Ends")).toHaveClass("structure-ending-badge");
      expect(screen.getByRole("button", { name: "CFO Finance lead" })).toBeInTheDocument();
    });

    it("does not mark the node in an earlier org state", async () => {
      renderInState(0);

      await screen.findByRole("button", { name: "CEO Chief executive" });
      expect(screen.getByTestId("ending-node-ids")).toBeEmptyDOMElement();
      expect(screen.getByTestId("ending-edge-ids")).toBeEmptyDOMElement();
    });

    it("marks a node whose delete date falls before the next org state", async () => {
      vi.mocked(structureApi.fetchGraph).mockResolvedValue(endingGraph("2026-01-15"));
      renderInState(0);

      await waitFor(() =>
        expect(screen.getByTestId("ending-node-ids")).toHaveTextContent("node_ceo")
      );
    });

    it("marks any node with a delete date when there is no later org state", async () => {
      vi.mocked(structureApi.fetchGraph).mockResolvedValue(endingGraph("2026-04-01"));
      renderInState(2);

      await waitFor(() =>
        expect(screen.getByTestId("ending-node-ids")).toHaveTextContent("node_ceo")
      );
    });

    it("falls back to the selected date when the org states cannot be loaded", async () => {
      vi.mocked(scenariosApi.fetchOrgStates).mockRejectedValue(new Error("Org states failed"));
      vi.mocked(structureApi.fetchGraph).mockResolvedValue({
        ...endingGraph("2026-02-01"),
        edges: graph.edges.map((edge) => ({ ...edge, deleteDate: "2026-02-15" }))
      });
      renderInState(1);

      await waitFor(() =>
        expect(screen.getByTestId("ending-node-ids")).toHaveTextContent("node_ceo")
      );
      expect(screen.getByTestId("ending-edge-ids")).toBeEmptyDOMElement();
      expect(screen.getByTestId("graph-node-ids")).toHaveTextContent("node_ceo");
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("disables Delete for a node already removed in the selected org state", async () => {
      renderInState(1);

      fireEvent.click(await screen.findByRole("button", { name: /^CEO Ends 2026-02-01/ }));

      expect(
        screen.getByText("Exists until 2026-02-01. Not shown in later org states.")
      ).toBeInTheDocument();
      const deleteButton = screen.getByRole("button", { name: "Delete selected node" });
      expect(deleteButton).toBeDisabled();
      expect(deleteButton).toHaveAccessibleDescription("Already removed in this org state.");
    });

    it("keeps Delete available for a node that ends after the selected org state", async () => {
      vi.mocked(structureApi.fetchGraph).mockResolvedValue(endingGraph("2026-02-15"));
      renderInState(1);

      fireEvent.click(await screen.findByRole("button", { name: /^CEO Ends 2026-02-15/ }));

      expect(
        screen.getByText("Exists until 2026-02-15. Not shown in later org states.")
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Delete selected node" })).toBeEnabled();
      expect(screen.queryByText("Already removed in this org state.")).not.toBeInTheDocument();
    });

    it("disables Delete for an edge already removed in the selected org state", async () => {
      renderInState(1);
      await screen.findByRole("region", { name: "Person nodes" });

      fireEvent.click(screen.getByRole("button", { name: "Show & Edit" }));
      fireEvent.click(screen.getByRole("button", { name: "Select reports edge" }));

      expect(
        screen.getByText("Exists until 2026-02-01. Not shown in later org states.")
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Delete selected edge" })).toBeDisabled();
    });
  });

  it("closes the load error and shows it again when loading fails again", async () => {
    vi.mocked(structureApi.fetchGraph).mockRejectedValue(new Error("Graph failed"));
    renderStructureTab();

    expect(await screen.findByRole("alert")).toHaveTextContent("Graph failed");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss Structure API error notice" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Graph failed");
  });

  describe("shows one alert, in the form, when a form action fails", () => {
    const failure = new Error("API request failed (422). Invalid");

    it.each([
      {
        action: "Create node",
        fail: () => vi.mocked(structureApi.createGraphNode).mockRejectedValue(failure),
        open: () => {
          const panel = screen.getByRole("region", { name: "Create node" });
          fireEvent.change(within(panel).getByLabelText("Name"), {
            target: { value: "Operations" }
          });
          return panel;
        }
      },
      {
        action: "Save node",
        fail: () => vi.mocked(structureApi.updateGraphNode).mockRejectedValue(failure),
        open: () => {
          fireEvent.click(screen.getByRole("button", { name: "CEO Chief executive" }));
          return screen.getByRole("region", { name: "Edit node" });
        }
      },
      {
        action: "Create edge",
        fail: () => vi.mocked(structureApi.createGraphEdge).mockRejectedValue(failure),
        open: () => {
          const panel = screen.getByRole("region", { name: "Create edge" });
          fireEvent.change(within(panel).getByLabelText("Name"), {
            target: { value: "Reports to" }
          });
          chooseEdgeNode(panel, "Source", "CFO");
          chooseEdgeNode(panel, "Target", "CEO");
          return panel;
        }
      },
      {
        action: "Save edge",
        fail: () => vi.mocked(structureApi.updateGraphEdge).mockRejectedValue(failure),
        open: () => {
          fireEvent.click(screen.getByRole("button", { name: "Show & Edit" }));
          fireEvent.click(screen.getByRole("button", { name: "Select reports edge" }));
          return screen.getByRole("region", { name: "Edit edge" });
        }
      }
    ])("$action", async ({ action, fail, open }) => {
      fail();
      renderStructureTab();
      await screen.findByRole("region", { name: "Person nodes" });

      const panel = open();
      fireEvent.click(within(panel).getByRole("button", { name: action }));

      expect(await within(panel).findByRole("alert")).toHaveTextContent(failure.message);
      expect(screen.getAllByRole("alert")).toHaveLength(1);
      expect(screen.queryByText("Structure save error")).not.toBeInTheDocument();
    });
  });

  it("shows a failed position save once as a Structure save error", async () => {
    vi.mocked(structureApi.bulkUpdatePositions).mockRejectedValue(new Error("Positions failed"));
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Move CEO" }));
    await act(async () => {
      vi.advanceTimersByTime(400);
      await Promise.resolve();
    });
    vi.useRealTimers();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Structure save error");
    expect(alert).toHaveTextContent("Positions failed");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it.each([
    {
      kind: "node",
      fail: () =>
        vi.mocked(structureApi.deleteGraphNode).mockRejectedValue(new Error("Delete failed")),
      open: () => fireEvent.click(screen.getByRole("button", { name: "CEO Chief executive" }))
    },
    {
      kind: "edge",
      fail: () =>
        vi.mocked(structureApi.deleteGraphEdge).mockRejectedValue(new Error("Delete failed")),
      open: () => {
        fireEvent.click(screen.getByRole("button", { name: "Show & Edit" }));
        fireEvent.click(screen.getByRole("button", { name: "Select reports edge" }));
      }
    }
  ])("shows a failed $kind delete once as a Structure save error", async ({ kind, fail, open }) => {
    fail();
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });
    open();

    fireEvent.click(screen.getByRole("button", { name: `Delete selected ${kind}` }));
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Structure save error");
    expect(alert).toHaveTextContent("Delete failed");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    // The confirmation stays open, so the delete can be retried or cancelled.
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Yes" })).toBeEnabled());
  });

  it("clears an earlier Structure save error when a form action starts", async () => {
    vi.mocked(structureApi.bulkUpdatePositions).mockRejectedValue(new Error("Positions failed"));
    vi.mocked(structureApi.createGraphNode).mockRejectedValue(new Error("Create failed"));
    renderStructureTab();
    await screen.findByRole("region", { name: "Person nodes" });

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Move CEO" }));
    await act(async () => {
      vi.advanceTimersByTime(400);
      await Promise.resolve();
    });
    vi.useRealTimers();
    expect(await screen.findByRole("alert")).toHaveTextContent("Structure save error");

    const panel = screen.getByRole("region", { name: "Create node" });
    fireEvent.change(within(panel).getByLabelText("Name"), { target: { value: "Operations" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Create node" }));

    expect(await within(panel).findByRole("alert")).toHaveTextContent("Create failed");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.queryByText("Structure save error")).not.toBeInTheDocument();
  });
});
