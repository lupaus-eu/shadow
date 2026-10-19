import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import cytoscape from "cytoscape";
import type {
  Core,
  EdgeSingular,
  ElementDefinition,
  EventObject,
  NodeSingular,
  SingularElementReturnValue,
  StylesheetJson
} from "cytoscape";
import type { GraphDto, GraphPosition, GraphTypeCatalogDto } from "../../api/orgTwinStructure";

export type GraphSelection = { kind: "node"; id: string } | { kind: "edge"; id: string };

export type GraphCenterRequest = { nodeId: string; requestId: number };

const DEFAULT_NODE_COLOR = "#dbeafe";
const DEFAULT_EDGE_COLOR = "#86efac";
const GRAPH_FIT_PADDING = 56;
const GRAPH_NODE_WIDTH = 138;
const GRAPH_NODE_HEIGHT = 60;
const POPOVER_MARGIN = 12;
const POPOVER_GAP = 14;
const GRAPH_STYLES = [
  {
    selector: "node",
    style: {
      "background-color": "data(color)",
      shape: "data(shape)",
      label: "data(label)",
      color: "#1a1714",
      "font-size": 12,
      "font-weight": 600,
      "text-valign": "center",
      "text-halign": "center",
      "text-wrap": "wrap",
      "text-max-width": 120,
      width: 138,
      height: 60,
      "border-width": 1,
      "border-color": "#b8ae9b"
    }
  },
  {
    selector: "edge",
    style: {
      width: 4,
      "arrow-scale": 1,
      "line-color": DEFAULT_EDGE_COLOR,
      "line-style": "data(lineStyle)",
      label: "data(label)",
      color: "#4f4a42",
      "font-size": 11,
      "curve-style": "bezier",
      "target-arrow-color": DEFAULT_EDGE_COLOR,
      "source-arrow-color": DEFAULT_EDGE_COLOR,
      "target-arrow-shape": "data(targetArrow)",
      "source-arrow-shape": "data(sourceArrow)",
      "text-wrap": "wrap",
      "text-max-width": 140,
      "text-background-color": "#ffffff",
      "text-background-opacity": 1,
      "text-background-padding": 4,
      "text-border-color": "#b8ae9b",
      "text-border-opacity": 1,
      "text-border-width": 1
    }
  },
  {
    selector: ":selected",
    style: {
      "border-color": "#e85d1f",
      "border-width": 3,
      "line-color": "#e85d1f",
      "target-arrow-color": "#e85d1f",
      "source-arrow-color": "#e85d1f"
    }
  }
] as unknown as StylesheetJson;

function cytoscapeShape(shape: string | null | undefined): string {
  if (shape === "ellipse" || shape === "diamond" || shape === "hexagon") {
    return shape;
  }
  if (shape === "rectangle" || shape === "roundrectangle") {
    return shape;
  }
  return "roundrectangle";
}

function edgeLineStyle(style: string | null | undefined): string {
  return style === "dashed" || style === "dotted" ? style : "solid";
}

function edgeArrow(end: string | null | undefined): string {
  return end === "arrow" ? "triangle" : "none";
}

function fallbackPosition(index: number): GraphPosition {
  const column = index % 4;
  const row = Math.floor(index / 4);
  return {
    x: 120 + column * 180,
    y: 120 + row * 130
  };
}

function typeDisplayName(
  type: { displayName: string; name: string | null } | undefined,
  fallbackId: string
): string {
  return type?.displayName || type?.name || fallbackId;
}

function buildInstanceLabel(typeName: string, instanceName: string): string {
  return `${typeName}:\n${instanceName}`;
}

function viewportCenter(cy: Core): GraphPosition {
  const extent = cy.extent();
  return {
    x: (extent.x1 + extent.x2) / 2,
    y: (extent.y1 + extent.y2) / 2
  };
}

function clamp(value: number, min: number, max: number): number {
  if (min > max) return min;
  return Math.min(Math.max(value, min), max);
}

function overlapsNode(
  left: number,
  top: number,
  width: number,
  height: number,
  nodeX: number,
  nodeY: number
): boolean {
  const nodeLeft = nodeX - GRAPH_NODE_WIDTH / 2;
  const nodeRight = nodeX + GRAPH_NODE_WIDTH / 2;
  const nodeTop = nodeY - GRAPH_NODE_HEIGHT / 2;
  const nodeBottom = nodeY + GRAPH_NODE_HEIGHT / 2;

  return !(
    left + width <= nodeLeft ||
    left >= nodeRight ||
    top + height <= nodeTop ||
    top >= nodeBottom
  );
}

function placePopover(
  nodeX: number,
  nodeY: number,
  shellWidth: number,
  shellHeight: number,
  popoverWidth: number,
  popoverHeight: number
): { left: number; top: number } {
  const minLeft = POPOVER_MARGIN;
  const maxLeft = shellWidth - POPOVER_MARGIN - popoverWidth;
  const minTop = POPOVER_MARGIN;
  const maxTop = shellHeight - POPOVER_MARGIN - popoverHeight;
  const candidates = [
    {
      left: nodeX - popoverWidth / 2,
      top: nodeY - GRAPH_NODE_HEIGHT / 2 - POPOVER_GAP - popoverHeight
    },
    {
      left: nodeX + GRAPH_NODE_WIDTH / 2 + POPOVER_GAP,
      top: nodeY - popoverHeight / 2
    },
    {
      left: nodeX - popoverWidth / 2,
      top: nodeY + GRAPH_NODE_HEIGHT / 2 + POPOVER_GAP
    },
    {
      left: nodeX - GRAPH_NODE_WIDTH / 2 - POPOVER_GAP - popoverWidth,
      top: nodeY - popoverHeight / 2
    }
  ];

  for (const candidate of candidates) {
    if (
      candidate.left >= minLeft &&
      candidate.left <= maxLeft &&
      candidate.top >= minTop &&
      candidate.top <= maxTop
    ) {
      return candidate;
    }
  }

  const clampedCandidates = candidates.map((candidate) => ({
    left: clamp(candidate.left, minLeft, maxLeft),
    top: clamp(candidate.top, minTop, maxTop)
  }));
  const nonOverlappingCandidate = clampedCandidates.find(
    (candidate) =>
      !overlapsNode(candidate.left, candidate.top, popoverWidth, popoverHeight, nodeX, nodeY)
  );

  return nonOverlappingCandidate ?? clampedCandidates[0] ?? { left: minLeft, top: minTop };
}

type ElementSnapshot = {
  group: "nodes" | "edges";
  data: Record<string, string>;
  position?: GraphPosition;
};

function snapshotElement(element: ElementDefinition): ElementSnapshot {
  const data = Object.fromEntries(
    Object.entries((element.data ?? {}) as Record<string, unknown>).map(([key, value]) => [
      key,
      String(value ?? "")
    ])
  );

  return element.group === "nodes"
    ? {
        group: "nodes",
        data,
        position: element.position ? { x: element.position.x, y: element.position.y } : undefined
      }
    : { group: "edges", data };
}

function sameIds(
  previous: Map<string, ElementSnapshot> | null,
  next: Map<string, ElementSnapshot>
): boolean {
  if (!previous || previous.size !== next.size) return false;
  for (const id of next.keys()) {
    if (!previous.has(id)) return false;
  }
  return true;
}

function dataChanged(previous: ElementSnapshot, next: ElementSnapshot): boolean {
  const previousKeys = Object.keys(previous.data);
  const nextKeys = Object.keys(next.data);
  if (previous.group !== next.group || previousKeys.length !== nextKeys.length) {
    return true;
  }

  for (const key of nextKeys) {
    if (previous.data[key] !== next.data[key]) return true;
  }

  return false;
}

function positionChanged(
  previous: GraphPosition | undefined,
  next: GraphPosition | undefined
): boolean {
  if (!previous && !next) return false;
  if (!previous || !next) return true;
  return previous.x !== next.x || previous.y !== next.y;
}

function setElementData(element: SingularElementReturnValue, nextData: Record<string, string>) {
  for (const [key, value] of Object.entries(nextData)) {
    element.data(key, value);
  }
}

function syncElements(
  cy: Core,
  elements: ElementDefinition[],
  previousSnapshots: Map<string, ElementSnapshot> | null
) {
  const nextSnapshots = new Map(
    elements.map((element) => {
      const id = String((element.data as { id: string }).id);
      return [id, snapshotElement(element)] as const;
    })
  );
  const idsStable = sameIds(previousSnapshots, nextSnapshots);

  cy.batch(() => {
    if (!previousSnapshots) {
      if (elements.length > 0) {
        cy.add(elements);
      }
      return;
    }

    for (const id of previousSnapshots.keys()) {
      if (!nextSnapshots.has(id)) {
        const element = cy.$id(id);
        if (element.nonempty()) {
          element.remove();
        }
      }
    }

    const elementsToAdd: ElementDefinition[] = [];

    for (const element of elements) {
      const id = String((element.data as { id: string }).id);
      const nextSnapshot = nextSnapshots.get(id);
      if (!nextSnapshot) continue;

      const existing = cy.$id(id);
      if (existing.empty()) {
        elementsToAdd.push(element);
        continue;
      }

      const previousSnapshot = previousSnapshots.get(id);
      if (!previousSnapshot) continue;

      if (dataChanged(previousSnapshot, nextSnapshot)) {
        setElementData(existing, nextSnapshot.data);
      }

      if (
        idsStable &&
        nextSnapshot.group === "nodes" &&
        positionChanged(previousSnapshot.position, nextSnapshot.position) &&
        nextSnapshot.position
      ) {
        existing.position(nextSnapshot.position);
      }
    }

    if (elementsToAdd.length > 0) {
      cy.add(elementsToAdd);
    }
  });

  return {
    nextSnapshots,
    needsInitialFit: !previousSnapshots && elements.length > 0,
    idsStable
  };
}

export default function GraphViewer(props: {
  graph: GraphDto | null;
  catalog: GraphTypeCatalogDto | null;
  visibleNodeTypeIds: Set<string>;
  selected: GraphSelection | null;
  centerNodeRequest: GraphCenterRequest | null;
  fitRequestId: number;
  onSelect: (selection: GraphSelection | null) => void;
  onNodePositionChange: (nodeId: string, position: GraphPosition) => void;
  onViewportCenterChange: (position: GraphPosition) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasShellRef = useRef<HTMLDivElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const elementSnapshotsRef = useRef<Map<string, ElementSnapshot> | null>(null);
  const fitTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const lastFitRequestIdRef = useRef(0);
  const onSelectRef = useRef(props.onSelect);
  const onNodePositionChangeRef = useRef(props.onNodePositionChange);
  const onViewportCenterChangeRef = useRef(props.onViewportCenterChange);
  const [hoveredNode, setHoveredNode] = useState<{
    name: string;
    description: string;
    x: number;
    y: number;
  } | null>(null);

  useEffect(() => {
    onSelectRef.current = props.onSelect;
    onNodePositionChangeRef.current = props.onNodePositionChange;
    onViewportCenterChangeRef.current = props.onViewportCenterChange;
  }, [props.onNodePositionChange, props.onSelect, props.onViewportCenterChange]);

  const elements = useMemo<ElementDefinition[]>(() => {
    if (!props.graph) return [];

    const nodeTypes = new Map(
      (props.catalog?.nodeTypes ?? []).map((nodeType) => [nodeType.id, nodeType])
    );
    const edgeTypes = new Map(
      (props.catalog?.edgeTypes ?? []).map((edgeType) => [edgeType.id, edgeType])
    );
    const visibleNodes = props.graph.nodes.filter((node) =>
      props.visibleNodeTypeIds.has(node.nodeTypeId)
    );
    const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));

    const nodeElements: ElementDefinition[] = visibleNodes.map((node, index) => {
      const nodeType = nodeTypes.get(node.nodeTypeId);
      return {
        group: "nodes",
        data: {
          id: node.id,
          name: node.name,
          description: node.description ?? "",
          label: buildInstanceLabel(typeDisplayName(nodeType, node.nodeTypeId), node.name),
          color: nodeType?.color || DEFAULT_NODE_COLOR,
          shape: cytoscapeShape(nodeType?.shape)
        },
        position: node.position ?? fallbackPosition(index)
      };
    });

    const edgeElements: ElementDefinition[] = props.graph.edges
      .filter(
        (edge) => visibleNodeIds.has(edge.sourceNodeId) && visibleNodeIds.has(edge.targetNodeId)
      )
      .map((edge) => {
        const edgeType = edgeTypes.get(edge.edgeTypeId);
        return {
          group: "edges",
          data: {
            id: edge.id,
            source: edge.sourceNodeId,
            target: edge.targetNodeId,
            label: buildInstanceLabel(typeDisplayName(edgeType, edge.edgeTypeId), edge.name),
            lineStyle: edgeLineStyle(edgeType?.style),
            sourceArrow: edgeArrow(edgeType?.sourceEnd),
            targetArrow: edgeArrow(edgeType?.targetEnd)
          }
        };
      });

    return [...nodeElements, ...edgeElements];
  }, [props.catalog, props.graph, props.visibleNodeTypeIds]);

  function fitGraph(cy: Core) {
    cy.resize();
    cy.fit(undefined, GRAPH_FIT_PADDING);
    onViewportCenterChangeRef.current(viewportCenter(cy));
  }

  useLayoutEffect(() => {
    const shell = canvasShellRef.current;
    const popover = popoverRef.current;
    if (!hoveredNode || !shell || !popover) return;

    const shellRect = shell.getBoundingClientRect();
    const popoverRect = popover.getBoundingClientRect();
    const { left, top } = placePopover(
      hoveredNode.x,
      hoveredNode.y,
      shellRect.width,
      shellRect.height,
      popoverRect.width,
      popoverRect.height
    );

    popover.style.left = `${left}px`;
    popover.style.top = `${top}px`;
    popover.style.visibility = "visible";
  }, [hoveredNode]);

  useEffect(() => {
    if (!containerRef.current || cyRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      wheelSensitivity: 2.5,
      layout: { name: "preset" },
      style: GRAPH_STYLES
    });
    const notifyViewportCenter = () => {
      onViewportCenterChangeRef.current(viewportCenter(cy));
    };
    const updateHoveredNode = (event: EventObject) => {
      const node = event.target as NodeSingular;
      const description = String(node.data("description") ?? "").trim();
      if (!description) {
        setHoveredNode(null);
        return;
      }

      const position = node.renderedPosition();
      setHoveredNode({
        name: String(node.data("name") ?? node.id()),
        description,
        x: position.x,
        y: position.y
      });
    };

    cy.on("tap", (event: EventObject) => {
      if (event.target === cy) {
        setHoveredNode(null);
        onSelectRef.current(null);
      }
    });
    cy.on("tap", "node", (event: EventObject) => {
      onSelectRef.current({ kind: "node", id: (event.target as NodeSingular).id() });
    });
    cy.on("tap", "edge", (event: EventObject) => {
      onSelectRef.current({ kind: "edge", id: (event.target as EdgeSingular).id() });
    });
    cy.on("dragfree", "node", (event: EventObject) => {
      const node = event.target as NodeSingular;
      const position = node.position();
      setHoveredNode(null);
      onNodePositionChangeRef.current(node.id(), {
        x: position.x,
        y: position.y
      });
    });
    cy.on("mouseover mousemove", "node", updateHoveredNode);
    cy.on("mouseout", "node", () => setHoveredNode(null));
    cy.on("pan zoom resize", notifyViewportCenter);

    cyRef.current = cy;
    notifyViewportCenter();

    const resizeObserver =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            cy.resize();
            notifyViewportCenter();
          });
    resizeObserver?.observe(containerRef.current);

    return () => {
      resizeObserver?.disconnect();
      cy.destroy();
      cyRef.current = null;
      elementSnapshotsRef.current = null;
      lastFitRequestIdRef.current = 0;
      if (fitTimeoutRef.current) {
        window.clearTimeout(fitTimeoutRef.current);
        fitTimeoutRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    elementSnapshotsRef.current = syncElements(
      cy,
      elements,
      elementSnapshotsRef.current
    ).nextSnapshots;
  }, [elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (
      !cy ||
      props.fitRequestId === 0 ||
      props.fitRequestId === lastFitRequestIdRef.current ||
      elements.length === 0
    ) {
      return;
    }

    if (fitTimeoutRef.current) {
      window.clearTimeout(fitTimeoutRef.current);
    }

    fitTimeoutRef.current = window.setTimeout(() => {
      fitTimeoutRef.current = null;
      if (cy.destroyed()) return;
      fitGraph(cy);
      lastFitRequestIdRef.current = props.fitRequestId;
    }, 0);
  }, [elements.length, props.fitRequestId]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.elements().unselect();
    if (!props.selected) return;

    const element = cy.$id(props.selected.id);
    if (element.nonempty()) {
      element.select();
    }
  }, [props.selected]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !props.centerNodeRequest) return;

    const element = cy.$id(props.centerNodeRequest.nodeId);
    if (element.nonempty()) {
      cy.animate(
        {
          center: { eles: element },
          zoom: Math.max(cy.zoom(), 1)
        },
        { duration: 180 }
      );
    }
  }, [props.centerNodeRequest]);

  function fit() {
    const cy = cyRef.current;
    if (!cy) return;
    fitGraph(cy);
  }

  return (
    <section className="graph-viewer" aria-label="Graph viewer">
      <div className="graph-viewer__controls" aria-label="Graph controls">
        <button className="btn btn--secondary btn--compact" type="button" onClick={fit}>
          Zoom to Fit
        </button>
      </div>
      <div
        className="graph-viewer__canvas-shell"
        ref={canvasShellRef}
        data-testid="graph-canvas-shell"
      >
        <div className="graph-viewer__canvas" ref={containerRef} data-testid="graph-canvas" />
        {hoveredNode ? (
          <div
            className="graph-viewer__popover"
            role="tooltip"
            ref={popoverRef}
            style={{
              left: "0px",
              top: "0px",
              visibility: "hidden"
            }}
          >
            <p className="graph-viewer__popover-title">{hoveredNode.name}</p>
            <p className="graph-viewer__popover-description">{hoveredNode.description}</p>
          </div>
        ) : null}
      </div>
      {elements.length === 0 ? (
        <div className="graph-viewer__empty">
          <p className="muted">No visible graph elements.</p>
        </div>
      ) : null}
    </section>
  );
}
