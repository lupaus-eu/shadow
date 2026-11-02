import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import cytoscape from "cytoscape";
import type { GraphDto, GraphTypeCatalogDto } from "../../api/orgTwinStructure";
import GraphViewer from "./GraphViewer";

const cytoscapeMock = vi.hoisted(() => ({
  cyAdd: vi.fn(),
  cyAnimate: vi.fn(),
  cyData: vi.fn(),
  cyElementNonempty: vi.fn(() => true),
  cyElementsUnselect: vi.fn(),
  cyFit: vi.fn(),
  eventHandlers: new Map<
    string,
    Array<{ handler: (event: { target: unknown }) => void; selector?: string }>
  >(),
  cyRemove: vi.fn(),
  cyResize: vi.fn(),
  cySelect: vi.fn(),
  cySetPosition: vi.fn(),
  cyZoom: vi.fn((value?: unknown) => (value ? undefined : 1)),
  cyOn: vi.fn(
    (
      eventNames: string,
      selectorOrHandler: string | ((event: { target: unknown }) => void),
      maybeHandler?: (event: { target: unknown }) => void
    ) => {
      const selector = typeof selectorOrHandler === "string" ? selectorOrHandler : undefined;
      const handler = typeof selectorOrHandler === "function" ? selectorOrHandler : maybeHandler;

      if (!handler) return;

      for (const eventName of eventNames.split(" ")) {
        const handlers = cytoscapeMock.eventHandlers.get(eventName) ?? [];
        handlers.push({ handler, selector });
        cytoscapeMock.eventHandlers.set(eventName, handlers);
      }
    }
  ),
  trigger(eventName: string, target: unknown, selector?: string) {
    for (const entry of cytoscapeMock.eventHandlers.get(eventName) ?? []) {
      if (entry.selector && entry.selector !== selector) continue;
      entry.handler({ target });
    }
  }
}));

const resizeObserverMock = vi.hoisted(() => {
  let callback: ResizeObserverCallback | null = null;

  return {
    observe: vi.fn(),
    disconnect: vi.fn(),
    install() {
      class MockResizeObserver {
        constructor(nextCallback: ResizeObserverCallback) {
          callback = nextCallback;
        }

        observe = resizeObserverMock.observe;
        disconnect = resizeObserverMock.disconnect;
      }

      vi.stubGlobal("ResizeObserver", MockResizeObserver);
    },
    trigger() {
      callback?.([], {} as ResizeObserver);
    }
  };
});

vi.mock("cytoscape", () => ({
  default: vi.fn(() => {
    const store = new Map<string, { data: Record<string, unknown>; position?: unknown }>();

    const makeElement = (id: string) => ({
      empty: () => !store.has(id),
      nonempty: () => store.has(id),
      select: cytoscapeMock.cySelect,
      remove: () => {
        store.delete(id);
        cytoscapeMock.cyRemove(id);
      },
      data: (key: string, value: unknown) => {
        const current = store.get(id);
        if (!current) return undefined;
        current.data[key] = value;
        cytoscapeMock.cyData(id, key, value);
        return value;
      },
      position: (value: unknown) => {
        const current = store.get(id);
        if (!current) return undefined;
        current.position = value;
        cytoscapeMock.cySetPosition(id, value);
        return value;
      }
    });

    return {
      on: cytoscapeMock.cyOn,
      batch: (callback: () => void) => callback(),
      elements: () => ({
        unselect: cytoscapeMock.cyElementsUnselect
      }),
      add: (elements: Array<{ data: { id: string }; position?: unknown }>) => {
        for (const element of elements) {
          store.set(element.data.id, { data: { ...element.data }, position: element.position });
        }
        cytoscapeMock.cyAdd(elements);
      },
      layout: () => ({ run: vi.fn() }),
      fit: cytoscapeMock.cyFit,
      resize: cytoscapeMock.cyResize,
      destroyed: () => false,
      destroy: vi.fn(),
      $id: (id: string) => makeElement(id),
      zoom: cytoscapeMock.cyZoom,
      width: () => 800,
      height: () => 600,
      extent: () => ({ x1: 10, x2: 210, y1: 20, y2: 220 }),
      animate: cytoscapeMock.cyAnimate
    };
  })
}));

const graph: GraphDto = {
  id: "future",
  name: "Future",
  description: "",
  nodes: [
    {
      id: "node_ceo",
      name: "CEO",
      description: "",
      nodeTypeId: "nt_person",
      createDate: null,
      deleteDate: null,
      position: { x: 10, y: 20 },
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    },
    {
      id: "node_hidden",
      name: "Hidden",
      description: "",
      nodeTypeId: "nt_hidden",
      createDate: null,
      deleteDate: null,
      position: { x: 100, y: 120 },
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    }
  ],
  edges: [
    {
      id: "edge_visible",
      name: "Visible edge",
      description: "",
      edgeTypeId: "et_reports_to",
      sourceNodeId: "node_ceo",
      targetNodeId: "node_ceo",
      createDate: null,
      deleteDate: null,
      attributes: {}
    },
    {
      id: "edge_hidden",
      name: "Hidden edge",
      description: "",
      edgeTypeId: "et_reports_to",
      sourceNodeId: "node_hidden",
      targetNodeId: "node_ceo",
      createDate: null,
      deleteDate: null,
      attributes: {}
    }
  ]
};

const noEnding: ReadonlySet<string> = new Set();

const endingGraph: GraphDto = {
  ...graph,
  nodes: graph.nodes.map((node) =>
    node.id === "node_ceo" ? { ...node, createDate: "2026-01-01", deleteDate: "2026-02-01" } : node
  ),
  edges: graph.edges.map((edge) =>
    edge.id === "edge_visible"
      ? { ...edge, createDate: "2026-01-01", deleteDate: "2026-02-01" }
      : edge
  )
};

const catalog: GraphTypeCatalogDto = {
  nodeTypes: [
    {
      id: "nt_person",
      name: "person",
      displayName: "Person",
      color: "#dbeafe",
      shape: "rectangle",
      timeserieId: null,
      timeserieSecondaryId: null,
      timeserieIdRule: null
    }
  ],
  edgeTypes: [
    {
      id: "et_reports_to",
      name: "reports_to",
      displayName: "Reports to",
      style: "dashed",
      sourceEnd: "none",
      targetEnd: "arrow"
    }
  ],
  allowedConnections: []
};

describe("GraphViewer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cytoscapeMock.eventHandlers.clear();
    resizeObserverMock.install();
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function mockRect(
      this: HTMLElement
    ) {
      if (this.dataset.testid === "graph-canvas-shell") {
        return {
          x: 0,
          y: 0,
          top: 0,
          left: 0,
          right: 320,
          bottom: 280,
          width: 320,
          height: 280,
          toJSON() {
            return {};
          }
        } as DOMRect;
      }

      if (this.getAttribute("role") === "tooltip") {
        return {
          x: 0,
          y: 0,
          top: 0,
          left: 0,
          right: 180,
          bottom: 84,
          width: 180,
          height: 84,
          toJSON() {
            return {};
          }
        } as DOMRect;
      }

      return {
        x: 0,
        y: 0,
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        width: 0,
        height: 0,
        toJSON() {
          return {};
        }
      } as DOMRect;
    });
  });

  it("renders graph controls and sends visible elements to Cytoscape", async () => {
    const onViewportCenterChange = vi.fn();
    render(
      <GraphViewer
        graph={graph}
        catalog={catalog}
        visibleNodeTypeIds={new Set(["nt_person"])}
        endingNodeIds={noEnding}
        endingEdgeIds={noEnding}
        selected={null}
        centerNodeRequest={null}
        fitRequestId={1}
        onSelect={vi.fn()}
        onNodePositionChange={vi.fn()}
        onViewportCenterChange={onViewportCenterChange}
      />
    );

    expect(screen.getByRole("button", { name: "Zoom to Fit" })).toBeInTheDocument();

    await waitFor(() => expect(cytoscapeMock.cyAdd).toHaveBeenCalled());
    const elements = cytoscapeMock.cyAdd.mock.calls.at(-1)?.[0] as Array<{
      data: { id: string; label?: string };
    }>;
    expect(elements.map((element) => element.data.id)).toEqual(["node_ceo", "edge_visible"]);
    expect(elements).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          data: expect.objectContaining({
            id: "node_ceo",
            label: "Person:\nCEO"
          })
        }),
        expect.objectContaining({
          data: expect.objectContaining({
            id: "edge_visible",
            label: "Reports to:\nVisible edge"
          })
        })
      ])
    );
    expect(cytoscape).toHaveBeenCalledWith(expect.objectContaining({ wheelSensitivity: 2.5 }));
    expect(cytoscape).toHaveBeenCalledWith(
      expect.objectContaining({
        style: expect.arrayContaining([
          expect.objectContaining({
            selector: "edge",
            style: expect.objectContaining({
              "line-color": "#86efac",
              "target-arrow-color": "#86efac",
              "arrow-scale": 1
            })
          })
        ])
      })
    );
    expect(onViewportCenterChange).toHaveBeenCalledWith({ x: 110, y: 120 });
  });

  it("only exposes zoom-to-fit as a graph control", async () => {
    const onViewportCenterChange = vi.fn();
    render(
      <GraphViewer
        graph={graph}
        catalog={catalog}
        visibleNodeTypeIds={new Set(["nt_person"])}
        endingNodeIds={noEnding}
        endingEdgeIds={noEnding}
        selected={null}
        centerNodeRequest={null}
        fitRequestId={1}
        onSelect={vi.fn()}
        onNodePositionChange={vi.fn()}
        onViewportCenterChange={onViewportCenterChange}
      />
    );

    expect(screen.queryByRole("button", { name: "Zoom In" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Zoom Out" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Up" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Down" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Left" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Right" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Zoom to Fit" }));

    expect(cytoscapeMock.cyFit).toHaveBeenCalled();
    expect(onViewportCenterChange).toHaveBeenCalledWith({ x: 110, y: 120 });
  });

  it("resizes Cytoscape when the graph container size changes", async () => {
    render(
      <GraphViewer
        graph={graph}
        catalog={catalog}
        visibleNodeTypeIds={new Set(["nt_person"])}
        endingNodeIds={noEnding}
        endingEdgeIds={noEnding}
        selected={null}
        centerNodeRequest={null}
        fitRequestId={1}
        onSelect={vi.fn()}
        onNodePositionChange={vi.fn()}
        onViewportCenterChange={vi.fn()}
      />
    );

    await waitFor(() => expect(cytoscapeMock.cyAdd).toHaveBeenCalled());
    resizeObserverMock.trigger();

    expect(cytoscapeMock.cyResize).toHaveBeenCalled();
  });

  it("selects nodes without centering unless a center request is provided", async () => {
    const baseProps = {
      graph,
      catalog,
      visibleNodeTypeIds: new Set(["nt_person"]),
      endingNodeIds: noEnding,
      endingEdgeIds: noEnding,
      selected: { kind: "node" as const, id: "node_ceo" },
      onSelect: vi.fn(),
      onNodePositionChange: vi.fn(),
      onViewportCenterChange: vi.fn(),
      fitRequestId: 1
    };

    const { rerender } = render(<GraphViewer {...baseProps} centerNodeRequest={null} />);

    await waitFor(() => expect(cytoscapeMock.cySelect).toHaveBeenCalled());
    expect(cytoscapeMock.cyAnimate).not.toHaveBeenCalled();

    rerender(
      <GraphViewer {...baseProps} centerNodeRequest={{ nodeId: "node_ceo", requestId: 1 }} />
    );

    await waitFor(() => expect(cytoscapeMock.cyAnimate).toHaveBeenCalled());
    expect(cytoscapeMock.cyAnimate).toHaveBeenCalledWith(
      expect.objectContaining({
        center: expect.any(Object),
        zoom: 1
      }),
      { duration: 180 }
    );
  });

  it("zooms to fit after a fit request and shows node descriptions on hover", async () => {
    render(
      <GraphViewer
        graph={graph}
        catalog={catalog}
        visibleNodeTypeIds={new Set(["nt_person"])}
        endingNodeIds={noEnding}
        endingEdgeIds={noEnding}
        selected={null}
        centerNodeRequest={null}
        fitRequestId={2}
        onSelect={vi.fn()}
        onNodePositionChange={vi.fn()}
        onViewportCenterChange={vi.fn()}
      />
    );

    await waitFor(() => expect(cytoscapeMock.cyFit).toHaveBeenCalled());

    cytoscapeMock.trigger(
      "mouseover",
      {
        id: () => "node_ceo",
        data: (key: string) =>
          ({
            name: "CEO",
            description: "Chief executive"
          })[key as "name" | "description"],
        renderedPosition: () => ({ x: 180, y: 220 })
      },
      "node"
    );

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Chief executive");
    expect(tooltip.querySelector(".graph-viewer__popover-description")).toHaveTextContent(
      "Chief executive"
    );
    expect(tooltip).toHaveStyle({
      left: "90px",
      top: "92px",
      visibility: "visible"
    });

    cytoscapeMock.trigger(
      "mouseout",
      {
        id: () => "node_ceo",
        data: () => "",
        renderedPosition: () => ({ x: 180, y: 220 })
      },
      "node"
    );

    await waitFor(() => {
      expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    });
  });

  it("keeps the tooltip inside the visible graph area near edges", async () => {
    render(
      <GraphViewer
        graph={graph}
        catalog={catalog}
        visibleNodeTypeIds={new Set(["nt_person"])}
        endingNodeIds={noEnding}
        endingEdgeIds={noEnding}
        selected={null}
        centerNodeRequest={null}
        fitRequestId={2}
        onSelect={vi.fn()}
        onNodePositionChange={vi.fn()}
        onViewportCenterChange={vi.fn()}
      />
    );

    cytoscapeMock.trigger(
      "mouseover",
      {
        id: () => "node_ceo",
        data: (key: string) =>
          ({
            name: "CEO",
            description: "Chief executive"
          })[key as "name" | "description"],
        renderedPosition: () => ({ x: 24, y: 26 })
      },
      "node"
    );

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveStyle({
      left: "107px",
      top: "12px",
      visibility: "visible"
    });
  });

  it("marks ending nodes and edges and shows the key", async () => {
    render(
      <GraphViewer
        graph={endingGraph}
        catalog={catalog}
        visibleNodeTypeIds={new Set(["nt_person"])}
        endingNodeIds={new Set(["node_ceo"])}
        endingEdgeIds={new Set(["edge_visible"])}
        selected={null}
        centerNodeRequest={null}
        fitRequestId={1}
        onSelect={vi.fn()}
        onNodePositionChange={vi.fn()}
        onViewportCenterChange={vi.fn()}
      />
    );

    await waitFor(() => expect(cytoscapeMock.cyAdd).toHaveBeenCalled());
    const elements = cytoscapeMock.cyAdd.mock.calls.at(-1)?.[0] as Array<{
      data: Record<string, string>;
    }>;
    expect(elements.map((element) => element.data)).toEqual([
      expect.objectContaining({
        id: "node_ceo",
        label: "Person:\nCEO",
        ending: "true",
        endDate: "2026-02-01"
      }),
      expect.objectContaining({
        id: "edge_visible",
        name: "Visible edge",
        label: "Reports to:\nVisible edge",
        ending: "true",
        endDate: "2026-02-01"
      })
    ]);
    expect(screen.getByText("Ends in this state")).toBeInTheDocument();

    const options = vi.mocked(cytoscape).mock.calls.at(-1)?.[0] as unknown as {
      style: Array<{ selector: string; style: Record<string, unknown> }>;
    };
    const styles = options.style;
    const selectors = styles.map((entry) => entry.selector);
    expect(selectors.indexOf('node[ending = "true"]')).toBeGreaterThan(-1);
    expect(selectors.indexOf('edge[ending = "true"]')).toBeGreaterThan(-1);
    expect(selectors.indexOf('node[ending = "true"]')).toBeLessThan(selectors.indexOf(":selected"));
    expect(styles.find((entry) => entry.selector === 'node[ending = "true"]')?.style).toEqual(
      expect.objectContaining({ "border-style": "dashed", color: "#736c5e" })
    );
    const endingNodeStyle = styles.find((entry) => entry.selector === 'node[ending = "true"]');
    expect(endingNodeStyle?.style).not.toHaveProperty("font-size");
    expect(styles.find((entry) => entry.selector === 'edge[ending = "true"]')?.style).toEqual(
      expect.objectContaining({
        "line-color": "#9ca3af",
        "line-style": "dashed",
        "target-arrow-color": "#9ca3af",
        "source-arrow-color": "#9ca3af",
        "text-events": "yes"
      })
    );
  });

  it("does not mark elements that do not end in the selected state", async () => {
    render(
      <GraphViewer
        graph={endingGraph}
        catalog={catalog}
        visibleNodeTypeIds={new Set(["nt_person"])}
        endingNodeIds={noEnding}
        endingEdgeIds={noEnding}
        selected={null}
        centerNodeRequest={null}
        fitRequestId={1}
        onSelect={vi.fn()}
        onNodePositionChange={vi.fn()}
        onViewportCenterChange={vi.fn()}
      />
    );

    await waitFor(() => expect(cytoscapeMock.cyAdd).toHaveBeenCalled());
    const elements = cytoscapeMock.cyAdd.mock.calls.at(-1)?.[0] as Array<{
      data: Record<string, string>;
    }>;
    expect(elements.map((element) => [element.data.label, element.data.ending])).toEqual([
      ["Person:\nCEO", "false"],
      ["Reports to:\nVisible edge", "false"]
    ]);
    expect(screen.queryByText("Ends in this state")).not.toBeInTheDocument();
  });

  it("updates existing elements when they start ending", async () => {
    const baseProps = {
      graph: endingGraph,
      catalog,
      visibleNodeTypeIds: new Set(["nt_person"]),
      endingEdgeIds: noEnding,
      selected: null,
      centerNodeRequest: null,
      fitRequestId: 1,
      onSelect: vi.fn(),
      onNodePositionChange: vi.fn(),
      onViewportCenterChange: vi.fn()
    };
    const { rerender } = render(<GraphViewer {...baseProps} endingNodeIds={noEnding} />);
    await waitFor(() => expect(cytoscapeMock.cyAdd).toHaveBeenCalled());

    rerender(<GraphViewer {...baseProps} endingNodeIds={new Set(["node_ceo"])} />);

    await waitFor(() =>
      expect(cytoscapeMock.cyData).toHaveBeenCalledWith("node_ceo", "ending", "true")
    );
    expect(cytoscapeMock.cyData).toHaveBeenCalledWith("node_ceo", "endDate", "2026-02-01");
  });

  it("shows the end date of an ending node on hover", async () => {
    render(
      <GraphViewer
        graph={endingGraph}
        catalog={catalog}
        visibleNodeTypeIds={new Set(["nt_person"])}
        endingNodeIds={new Set(["node_ceo"])}
        endingEdgeIds={noEnding}
        selected={null}
        centerNodeRequest={null}
        fitRequestId={1}
        onSelect={vi.fn()}
        onNodePositionChange={vi.fn()}
        onViewportCenterChange={vi.fn()}
      />
    );

    cytoscapeMock.trigger(
      "mouseover",
      {
        id: () => "node_ceo",
        data: (key: string) =>
          ({ name: "CEO", description: "", endDate: "2026-02-01" })[
            key as "name" | "description" | "endDate"
          ],
        renderedPosition: () => ({ x: 180, y: 220 })
      },
      "node"
    );

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Exists until 2026-02-01. Not shown in later org states.");
    expect(tooltip.querySelector(".graph-viewer__popover-description")).toBeNull();
  });

  it("shows the end date of an ending edge on hover and nothing for other edges", async () => {
    render(
      <GraphViewer
        graph={endingGraph}
        catalog={catalog}
        visibleNodeTypeIds={new Set(["nt_person"])}
        endingNodeIds={noEnding}
        endingEdgeIds={new Set(["edge_visible"])}
        selected={null}
        centerNodeRequest={null}
        fitRequestId={1}
        onSelect={vi.fn()}
        onNodePositionChange={vi.fn()}
        onViewportCenterChange={vi.fn()}
      />
    );
    const edgeTarget = (endDate: string) => ({
      id: () => "edge_visible",
      data: (key: string) => ({ name: "Visible edge", endDate })[key as "name" | "endDate"],
      renderedMidpoint: () => ({ x: 240, y: 260 })
    });

    cytoscapeMock.trigger("mouseover", edgeTarget(""), "edge");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    cytoscapeMock.trigger("mouseover", edgeTarget("2026-02-01"), "edge");
    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Visible edge");
    expect(tooltip).toHaveTextContent("Exists until 2026-02-01. Not shown in later org states.");

    cytoscapeMock.trigger("mouseout", edgeTarget("2026-02-01"), "edge");
    await waitFor(() => expect(screen.queryByRole("tooltip")).not.toBeInTheDocument());
  });
});
