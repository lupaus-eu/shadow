import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  bulkUpdatePositions,
  createGraphEdge,
  createGraphNode,
  deleteGraphEdge,
  deleteGraphNode,
  fetchGraph,
  fetchGraphTypeCatalog,
  updateGraphEdge,
  updateGraphNode
} from "../../api/orgTwinStructure";
import type {
  BulkPositionUpdateRequest,
  GraphDto,
  GraphEdgeCreateRequest,
  GraphEdgeUpdateRequest,
  GraphNodeDto,
  GraphNodeUpdateRequest,
  GraphPosition,
  GraphTypeCatalogDto,
  NodeTypeMetadataDto
} from "../../api/orgTwinStructure";
import { fetchOrgStates } from "../../api/scenarios";
import Alert from "../../components/Alert";
import { useWorkspaceSelection } from "../../workspace/WorkspaceSelectionContext";
import EdgeForm from "./EdgeForm";
import type { EdgeFormCreatePayload } from "./EdgeForm";
import GraphEditorToolbar, { EditorModeSelector } from "./GraphEditorToolbar";
import type { StructureMode } from "./GraphEditorToolbar";
import GraphViewer from "./GraphViewer";
import type { GraphCenterRequest, GraphSelection } from "./GraphViewer";
import { endsInOrgState, nextOrgStateTargetDate } from "./lifetime";
import NodeForm from "./NodeForm";
import type { NodeFormCreatePayload } from "./NodeForm";
import NodeList from "./NodeList";
import TimeseriePanel from "./TimeseriePanel";

type PendingPosition = BulkPositionUpdateRequest["positions"][number];
type CreateEdgeDraft = {
  sourceNodeId: string;
  targetNodeId: string;
  clickedNodeIds: string[];
};

const EMPTY_CREATE_EDGE_DRAFT: CreateEdgeDraft = {
  sourceNodeId: "",
  targetNodeId: "",
  clickedNodeIds: []
};

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function replaceNode(graph: GraphDto, node: GraphDto["nodes"][number]): GraphDto {
  const exists = graph.nodes.some((item) => item.id === node.id);
  return {
    ...graph,
    nodes: exists
      ? graph.nodes.map((item) => (item.id === node.id ? node : item))
      : [...graph.nodes, node]
  };
}

function replaceEdge(graph: GraphDto, edge: GraphDto["edges"][number]): GraphDto {
  const exists = graph.edges.some((item) => item.id === edge.id);
  return {
    ...graph,
    edges: exists
      ? graph.edges.map((item) => (item.id === edge.id ? edge : item))
      : [...graph.edges, edge]
  };
}

function slugPart(value: string): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return slug || "item";
}

function uniqueGraphKey(prefix: "edge" | "node", name: string, existingKeys: Set<string>): string {
  const base = `${prefix}_${slugPart(name)}`;
  let candidate = base;
  let suffix = 2;

  while (existingKeys.has(candidate)) {
    candidate = `${base}_${suffix}`;
    suffix += 1;
  }

  return candidate;
}

function collapsedEmptyNodeTypeIds(graph: GraphDto, catalog: GraphTypeCatalogDto): Set<string> {
  const usedNodeTypeIds = new Set(graph.nodes.map((node) => node.nodeTypeId));
  return new Set(
    catalog.nodeTypes
      .map((nodeType) => nodeType.id)
      .filter((nodeTypeId) => !usedNodeTypeIds.has(nodeTypeId))
  );
}

function positionsEqual(
  left: GraphPosition | null | undefined,
  right: GraphPosition | null | undefined
): boolean {
  if (!left && !right) return true;
  if (!left || !right) return false;
  return left.x === right.x && left.y === right.y;
}

function mergePositionUpdate(current: GraphDto | null, updated: GraphDto): GraphDto {
  if (!current) return updated;

  const updatedNodesById = new Map(updated.nodes.map((node) => [node.id, node]));
  const mergedNodes = current.nodes.map((node) => {
    const nextNode = updatedNodesById.get(node.id);
    if (!nextNode) return node;
    return positionsEqual(node.position, nextNode.position)
      ? node
      : { ...node, position: nextNode.position };
  });

  return {
    ...current,
    id: updated.id,
    name: updated.name,
    description: updated.description,
    nodes: mergedNodes
  };
}

function edgeTypesForCreateSelection(
  graph: GraphDto | null,
  catalog: GraphTypeCatalogDto | null,
  selection: Pick<CreateEdgeDraft, "sourceNodeId" | "targetNodeId">
) {
  const edgeTypes = catalog?.edgeTypes ?? [];
  if (!graph || !catalog) return edgeTypes;
  if (!selection.sourceNodeId || !selection.targetNodeId) return edgeTypes;

  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const sourceNodeTypeId = nodesById.get(selection.sourceNodeId)?.nodeTypeId;
  const targetNodeTypeId = nodesById.get(selection.targetNodeId)?.nodeTypeId;
  if (!sourceNodeTypeId || !targetNodeTypeId) return [];

  const allowedEdgeTypeIds = new Set(
    catalog.allowedConnections
      .filter(
        (allowedConnection) =>
          allowedConnection.sourceNodeTypeId === sourceNodeTypeId &&
          allowedConnection.targetNodeTypeId === targetNodeTypeId
      )
      .map((allowedConnection) => allowedConnection.edgeTypeId)
  );

  return edgeTypes.filter((edgeType) => allowedEdgeTypeIds.has(edgeType.id));
}

function trimmed(value: string | null | undefined): string {
  return value?.trim() ?? "";
}

function nodeTypeHasTimeserieMetadata(nodeType: NodeTypeMetadataDto | undefined): boolean {
  if (!nodeType) return false;
  return Boolean(
    trimmed(nodeType.timeserieId) ||
    trimmed(nodeType.timeserieSecondaryId) ||
    trimmed(nodeType.timeserieIdRule)
  );
}

function isMetricNodeType(nodeType: NodeTypeMetadataDto | undefined, fallbackId: string) {
  const values = [fallbackId, nodeType?.id, nodeType?.name, nodeType?.displayName]
    .map((value) => trimmed(value).toLowerCase())
    .filter(Boolean);

  return values.some((value) => value.includes("metric"));
}

function nodeSupportsTimeserie(
  node: GraphNodeDto | null,
  nodeType: NodeTypeMetadataDto | undefined
): boolean {
  if (!node) return false;
  return Boolean(
    trimmed(node.timeserieId) ||
    trimmed(node.timeserieSecondaryId) ||
    nodeTypeHasTimeserieMetadata(nodeType) ||
    isMetricNodeType(nodeType, node.nodeTypeId)
  );
}

export default function StructureTab(props: { orgId: string }) {
  const { selectedScenario, selectedOrgState } = useWorkspaceSelection();
  const [mode, setMode] = useState<StructureMode>("create");
  const [graph, setGraph] = useState<GraphDto | null>(null);
  const [catalog, setCatalog] = useState<GraphTypeCatalogDto | null>(null);
  // undefined while the scenario's org states are unknown, null without a later org state.
  const [nextTargetDate, setNextTargetDate] = useState<string | null | undefined>(undefined);
  const [selected, setSelected] = useState<GraphSelection | null>(null);
  const [centerNodeRequest, setCenterNodeRequest] = useState<GraphCenterRequest | null>(null);
  const [fitRequestId, setFitRequestId] = useState(0);
  const [createEdgeDraft, setCreateEdgeDraft] = useState<CreateEdgeDraft>(EMPTY_CREATE_EDGE_DRAFT);
  const [preferredCreateNodeTypeId, setPreferredCreateNodeTypeId] = useState("");
  const [visibleNodeTypeIds, setVisibleNodeTypeIds] = useState<Set<string>>(() => new Set());
  const [collapsedNodeTypeIds, setCollapsedNodeTypeIds] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(false);
  const [isMutatingEntity, setIsMutatingEntity] = useState(false);
  const [isPersistingPositions, setIsPersistingPositions] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");

  const pendingPositionsRef = useRef(new Map<string, PendingPosition>());
  const graphViewportCenterRef = useRef<GraphPosition>({ x: 0, y: 0 });
  const debounceTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const contextRef = useRef<{
    scenarioId: string;
    orgStateId: string;
  } | null>(null);

  const allNodeTypeIds = useMemo(() => {
    const ids = new Set<string>();
    for (const nodeType of catalog?.nodeTypes ?? []) ids.add(nodeType.id);
    for (const node of graph?.nodes ?? []) ids.add(node.nodeTypeId);
    return ids;
  }, [catalog, graph]);

  const selectedNode = useMemo(
    () =>
      selected?.kind === "node"
        ? (graph?.nodes.find((node) => node.id === selected.id) ?? null)
        : null,
    [graph, selected]
  );
  const selectedEdge = useMemo(
    () =>
      selected?.kind === "edge"
        ? (graph?.edges.find((edge) => edge.id === selected.id) ?? null)
        : null,
    [graph, selected]
  );
  const selectedNodeType = useMemo(
    () =>
      selectedNode
        ? catalog?.nodeTypes.find((nodeType) => nodeType.id === selectedNode.nodeTypeId)
        : undefined,
    [catalog, selectedNode]
  );
  const canUseTimeserieMode = nodeSupportsTimeserie(selectedNode, selectedNodeType);

  const clearPendingPositionCommit = useCallback(() => {
    pendingPositionsRef.current.clear();
    if (debounceTimerRef.current) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    const nextContext =
      selectedScenario && selectedOrgState
        ? {
            scenarioId: selectedScenario.id,
            orgStateId: selectedOrgState.id
          }
        : null;
    const currentContext = contextRef.current;
    const contextChanged =
      currentContext?.scenarioId !== nextContext?.scenarioId ||
      currentContext?.orgStateId !== nextContext?.orgStateId;

    if (contextChanged) {
      clearPendingPositionCommit();
    }

    contextRef.current = nextContext;
  }, [clearPendingPositionCommit, selectedOrgState, selectedScenario]);

  const loadStructure = useCallback(
    async (signal?: AbortSignal) => {
      if (!selectedScenario || !selectedOrgState) {
        setGraph(null);
        setCatalog(null);
        setNextTargetDate(undefined);
        setSelected(null);
        setCenterNodeRequest(null);
        setFitRequestId(0);
        setCreateEdgeDraft(EMPTY_CREATE_EDGE_DRAFT);
        setPreferredCreateNodeTypeId("");
        return;
      }

      try {
        setLoading(true);
        setLoadError("");
        setActionError("");
        const [nextGraph, nextCatalog, orgStates] = await Promise.all([
          fetchGraph(props.orgId, selectedScenario.id, selectedOrgState.id, signal),
          fetchGraphTypeCatalog(props.orgId, selectedScenario.id, selectedOrgState.id, signal),
          // The ending markers fall back to the selected state's date without the org states.
          fetchOrgStates(props.orgId, selectedScenario.id, signal).catch(() => null)
        ]);
        setGraph(nextGraph);
        setCatalog(nextCatalog);
        setNextTargetDate(
          orgStates ? nextOrgStateTargetDate(orgStates, selectedOrgState.targetDate) : undefined
        );
        setSelected(null);
        setCenterNodeRequest(null);
        setCreateEdgeDraft(EMPTY_CREATE_EDGE_DRAFT);
        setPreferredCreateNodeTypeId(
          nextCatalog.nodeTypes[0]?.id ?? nextGraph.nodes[0]?.nodeTypeId ?? ""
        );
        setCollapsedNodeTypeIds(collapsedEmptyNodeTypeIds(nextGraph, nextCatalog));
        setVisibleNodeTypeIds(
          new Set([
            ...nextCatalog.nodeTypes.map((nodeType) => nodeType.id),
            ...nextGraph.nodes.map((node) => node.nodeTypeId)
          ])
        );
        setFitRequestId((current) => current + 1);
      } catch (error) {
        const err = error as { name?: string };
        if (err.name === "AbortError") return;
        setLoadError(messageFromError(error));
        setGraph(null);
        setCatalog(null);
        setNextTargetDate(undefined);
        setSelected(null);
        setCenterNodeRequest(null);
        setCreateEdgeDraft(EMPTY_CREATE_EDGE_DRAFT);
        setPreferredCreateNodeTypeId("");
      } finally {
        setLoading(false);
      }
    },
    [props.orgId, selectedOrgState, selectedScenario]
  );

  useEffect(() => {
    const ac = new AbortController();
    void Promise.resolve().then(() => loadStructure(ac.signal));
    return () => ac.abort();
  }, [loadStructure]);

  useEffect(() => {
    return () => {
      clearPendingPositionCommit();
    };
  }, [clearPendingPositionCommit]);

  async function commitPendingPositions() {
    const context = contextRef.current;
    const positions = [...pendingPositionsRef.current.values()];
    pendingPositionsRef.current.clear();
    debounceTimerRef.current = null;
    if (!context || positions.length === 0) return;

    try {
      setIsPersistingPositions(true);
      setActionError("");
      const updated = await bulkUpdatePositions(
        props.orgId,
        context.scenarioId,
        context.orgStateId,
        { positions }
      );
      if (
        contextRef.current?.scenarioId !== context.scenarioId ||
        contextRef.current?.orgStateId !== context.orgStateId
      ) {
        return;
      }
      setGraph((current) => mergePositionUpdate(current, updated));
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setIsPersistingPositions(false);
    }
  }

  function schedulePositionCommit(nodeId: string, position: GraphPosition) {
    pendingPositionsRef.current.set(nodeId, {
      nodeId,
      x: position.x,
      y: position.y
    });

    setGraph((current) =>
      current
        ? {
            ...current,
            nodes: current.nodes.map((node) => (node.id === nodeId ? { ...node, position } : node))
          }
        : current
    );

    if (debounceTimerRef.current) {
      window.clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = window.setTimeout(() => {
      void commitPendingPositions();
    }, 400);
  }

  async function createNode(payload: NodeFormCreatePayload) {
    if (!selectedScenario || !selectedOrgState) return;
    const nodePayload = {
      ...payload,
      id: uniqueGraphKey(
        "node",
        payload.name,
        new Set((graph?.nodes ?? []).map((node) => node.id))
      ),
      position: graphViewportCenterRef.current
    };

    try {
      setIsMutatingEntity(true);
      // The form shows its own error; only an earlier page-level error is cleared.
      setActionError("");
      const node = await createGraphNode(
        props.orgId,
        selectedScenario.id,
        selectedOrgState.id,
        nodePayload
      );
      setGraph((current) => (current ? replaceNode(current, node) : current));
      setVisibleNodeTypeIds((current) => new Set(current).add(node.nodeTypeId));
      setSelected({ kind: "node", id: node.id });
    } finally {
      setIsMutatingEntity(false);
    }
  }

  async function updateNode(payload: GraphNodeUpdateRequest) {
    if (!selectedScenario || !selectedOrgState || !selectedNode) return;
    try {
      setIsMutatingEntity(true);
      setActionError("");
      const node = await updateGraphNode(
        props.orgId,
        selectedScenario.id,
        selectedOrgState.id,
        selectedNode.id,
        payload
      );
      setGraph((current) => (current ? replaceNode(current, node) : current));
      setVisibleNodeTypeIds((current) => new Set(current).add(node.nodeTypeId));
    } finally {
      setIsMutatingEntity(false);
    }
  }

  function clearDeletedTimeserieLinks(timeserieId: string) {
    setGraph((current) =>
      current
        ? {
            ...current,
            nodes: current.nodes.map((node) => ({
              ...node,
              timeserieId: node.timeserieId === timeserieId ? null : node.timeserieId,
              timeserieSecondaryId:
                node.timeserieSecondaryId === timeserieId ? null : node.timeserieSecondaryId
            }))
          }
        : current
    );
  }

  async function removeNode() {
    if (!selectedScenario || !selectedOrgState || !selectedNode) return;
    try {
      setIsMutatingEntity(true);
      setActionError("");
      await deleteGraphNode(props.orgId, selectedScenario.id, selectedOrgState.id, selectedNode.id);
      if (selectedNode.createDate === selectedOrgState.targetDate) {
        setGraph((current) =>
          current
            ? {
                ...current,
                nodes: current.nodes.filter((node) => node.id !== selectedNode.id),
                edges: current.edges.filter(
                  (edge) =>
                    edge.sourceNodeId !== selectedNode.id && edge.targetNodeId !== selectedNode.id
                )
              }
            : current
        );
      } else {
        const nextGraph = await fetchGraph(props.orgId, selectedScenario.id, selectedOrgState.id);
        if (
          contextRef.current?.scenarioId === selectedScenario.id &&
          contextRef.current.orgStateId === selectedOrgState.id
        ) {
          setGraph(nextGraph);
        }
      }
      setSelected(null);
    } catch (error) {
      setActionError(messageFromError(error));
      throw error;
    } finally {
      setIsMutatingEntity(false);
    }
  }

  async function createEdge(payload: EdgeFormCreatePayload) {
    if (!selectedScenario || !selectedOrgState) return;
    const edgePayload: GraphEdgeCreateRequest = {
      ...payload,
      id: uniqueGraphKey("edge", payload.name, new Set((graph?.edges ?? []).map((edge) => edge.id)))
    };

    try {
      setIsMutatingEntity(true);
      setActionError("");
      const edge = await createGraphEdge(
        props.orgId,
        selectedScenario.id,
        selectedOrgState.id,
        edgePayload
      );
      setGraph((current) => (current ? replaceEdge(current, edge) : current));
      setCreateEdgeDraft(EMPTY_CREATE_EDGE_DRAFT);
      setSelected({ kind: "edge", id: edge.id });
    } finally {
      setIsMutatingEntity(false);
    }
  }

  async function updateEdge(payload: GraphEdgeUpdateRequest) {
    if (!selectedScenario || !selectedOrgState || !selectedEdge) return;
    try {
      setIsMutatingEntity(true);
      setActionError("");
      const edge = await updateGraphEdge(
        props.orgId,
        selectedScenario.id,
        selectedOrgState.id,
        selectedEdge.id,
        payload
      );
      setGraph((current) => (current ? replaceEdge(current, edge) : current));
    } finally {
      setIsMutatingEntity(false);
    }
  }

  async function removeEdge() {
    if (!selectedScenario || !selectedOrgState || !selectedEdge) return;
    try {
      setIsMutatingEntity(true);
      setActionError("");
      await deleteGraphEdge(props.orgId, selectedScenario.id, selectedOrgState.id, selectedEdge.id);
      if (selectedEdge.createDate === selectedOrgState.targetDate) {
        setGraph((current) =>
          current
            ? {
                ...current,
                edges: current.edges.filter((edge) => edge.id !== selectedEdge.id)
              }
            : current
        );
      } else {
        const nextGraph = await fetchGraph(props.orgId, selectedScenario.id, selectedOrgState.id);
        if (
          contextRef.current?.scenarioId === selectedScenario.id &&
          contextRef.current.orgStateId === selectedOrgState.id
        ) {
          setGraph(nextGraph);
        }
      }
      setSelected(null);
    } catch (error) {
      setActionError(messageFromError(error));
      throw error;
    } finally {
      setIsMutatingEntity(false);
    }
  }

  function toggleVisibleNodeType(nodeTypeId: string) {
    setVisibleNodeTypeIds((current) => {
      const next = new Set(current);
      if (next.has(nodeTypeId)) next.delete(nodeTypeId);
      else next.add(nodeTypeId);
      return next;
    });
  }

  function toggleCollapsedNodeType(nodeTypeId: string) {
    setCollapsedNodeTypeIds((current) => {
      const next = new Set(current);
      if (next.has(nodeTypeId)) next.delete(nodeTypeId);
      else next.add(nodeTypeId);
      return next;
    });
  }

  function selectNodeFromList(nodeId: string) {
    setSelected({ kind: "node", id: nodeId });
    setCenterNodeRequest((current) => ({
      nodeId,
      requestId: (current?.requestId ?? 0) + 1
    }));
    setMode("edit");
  }

  function selectCreateNodeType(nodeTypeId: string) {
    setPreferredCreateNodeTypeId(nodeTypeId);
    setMode("create");
  }

  function updateCreateEdgeSelectionFromNode(nodeId: string) {
    setCreateEdgeDraft((current) => {
      if (current.clickedNodeIds.at(-1) === nodeId) {
        return current;
      }
      const nextClickedNodeIds = [...current.clickedNodeIds, nodeId].slice(-2);
      return {
        sourceNodeId: nextClickedNodeIds[0] ?? "",
        targetNodeId: nextClickedNodeIds[1] ?? "",
        clickedNodeIds: nextClickedNodeIds
      };
    });
  }

  function handleGraphSelection(selection: GraphSelection | null) {
    setSelected(selection);
    if (mode === "timeserie") {
      const nextNode =
        selection?.kind === "node"
          ? (graph?.nodes.find((node) => node.id === selection.id) ?? null)
          : null;
      const nextNodeType = nextNode
        ? catalog?.nodeTypes.find((nodeType) => nodeType.id === nextNode.nodeTypeId)
        : undefined;
      if (!nodeSupportsTimeserie(nextNode, nextNodeType)) {
        setMode("edit");
      }
    }
    if (mode === "create" && selection?.kind === "node") {
      updateCreateEdgeSelectionFromNode(selection.id);
    }
  }

  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];
  const nodeTypes = catalog?.nodeTypes ?? [];
  const edgeTypes = catalog?.edgeTypes ?? [];
  const createEdgeTypes = useMemo(
    () => edgeTypesForCreateSelection(graph, catalog, createEdgeDraft),
    [catalog, createEdgeDraft, graph]
  );
  const targetDate = selectedOrgState?.targetDate ?? "";
  const endingNodeIds = useMemo(
    () =>
      new Set(
        (graph?.nodes ?? [])
          .filter((node) => endsInOrgState(node.deleteDate, targetDate, nextTargetDate))
          .map((node) => node.id)
      ),
    [graph, nextTargetDate, targetDate]
  );
  const endingEdgeIds = useMemo(
    () =>
      new Set(
        (graph?.edges ?? [])
          .filter((edge) => endsInOrgState(edge.deleteDate, targetDate, nextTargetDate))
          .map((edge) => edge.id)
      ),
    [graph, nextTargetDate, targetDate]
  );

  return (
    <div className="structure-tab">
      <GraphEditorToolbar
        loading={loading}
        saving={isMutatingEntity || isPersistingPositions}
        nodeCount={nodes.length}
        edgeCount={edges.length}
        onRefresh={() => void loadStructure()}
      />

      {loadError ? (
        <Alert
          variant="danger"
          role="alert"
          title="Structure API error"
          onDismiss={() => setLoadError("")}
          message={loadError}
        />
      ) : null}
      {actionError ? (
        <Alert
          variant="danger"
          role="alert"
          title="Structure save error"
          onDismiss={() => setActionError("")}
          message={actionError}
        />
      ) : null}

      <div className="structure-workspace">
        <NodeList
          nodes={nodes}
          nodeTypes={nodeTypes}
          endingNodeIds={endingNodeIds}
          visibleNodeTypeIds={visibleNodeTypeIds}
          collapsedNodeTypeIds={collapsedNodeTypeIds}
          selectedNodeId={selected?.kind === "node" ? selected.id : null}
          onSelectNode={selectNodeFromList}
          onToggleVisibleNodeType={toggleVisibleNodeType}
          onSelectAllNodeTypes={() => setVisibleNodeTypeIds(new Set(allNodeTypeIds))}
          onDeselectAllNodeTypes={() => setVisibleNodeTypeIds(new Set())}
          onToggleCollapsedNodeType={toggleCollapsedNodeType}
          onCreateNodeOfType={selectCreateNodeType}
        />

        <GraphViewer
          graph={graph}
          catalog={catalog}
          visibleNodeTypeIds={visibleNodeTypeIds}
          endingNodeIds={endingNodeIds}
          endingEdgeIds={endingEdgeIds}
          selected={selected}
          centerNodeRequest={centerNodeRequest}
          fitRequestId={fitRequestId}
          onSelect={handleGraphSelection}
          onNodePositionChange={schedulePositionCommit}
          onViewportCenterChange={(position) => {
            graphViewportCenterRef.current = position;
          }}
        />

        <aside className="structure-editor-panel" aria-label="Structure editor">
          <section className="structure-editor-mode" aria-labelledby="structure-editor-mode-title">
            <h2 id="structure-editor-mode-title" className="section-title">
              Editor mode
            </h2>
            <EditorModeSelector
              mode={mode}
              showTimeserie={canUseTimeserieMode}
              onModeChange={setMode}
            />
          </section>

          {mode === "assistant" ? (
            <section className="detail-card">
              <div className="detail-card__header">
                <h2 className="section-title">AI Assistant</h2>
              </div>
              <p className="muted">Assistant support for structure editing will appear here.</p>
            </section>
          ) : mode === "create" ? (
            <div className="structure-editor-stack">
              <NodeForm
                key={`create-node:${nodeTypes.map((nodeType) => nodeType.id).join("|")}:${preferredCreateNodeTypeId}`}
                idPrefix="structure-create-node"
                title="Create node"
                node={null}
                nodeTypes={nodeTypes}
                preferredNodeTypeId={preferredCreateNodeTypeId}
                saving={isMutatingEntity}
                submitLabel="Create node"
                disabled={loading}
                onCreate={createNode}
              />
              <EdgeForm
                key={`create-edge:${edgeTypes.map((edgeType) => edgeType.id).join("|")}:${nodes.length}`}
                idPrefix="structure-create-edge"
                title="Create edge"
                edge={null}
                nodes={nodes}
                edgeTypes={createEdgeTypes}
                saving={isMutatingEntity}
                submitLabel="Create edge"
                disabled={loading}
                sourceNodeId={createEdgeDraft.sourceNodeId}
                targetNodeId={createEdgeDraft.targetNodeId}
                onSourceNodeIdChange={(nodeId) =>
                  setCreateEdgeDraft((current) => ({ ...current, sourceNodeId: nodeId }))
                }
                onTargetNodeIdChange={(nodeId) =>
                  setCreateEdgeDraft((current) => ({ ...current, targetNodeId: nodeId }))
                }
                nodeClickHint={
                  createEdgeDraft.clickedNodeIds.length === 0
                    ? "Click two nodes to connect, or use the dropdown menus..."
                    : undefined
                }
                onCreate={createEdge}
              />
            </div>
          ) : mode === "timeserie" && canUseTimeserieMode && selectedNode ? (
            <TimeseriePanel
              key={
                `timeserie-node:${selectedScenario?.id ?? ""}:${selectedNode.id}:` +
                `${selectedNode.timeserieId ?? ""}:` +
                `${selectedNode.timeserieSecondaryId ?? ""}`
              }
              orgId={props.orgId}
              scenarioId={selectedScenario?.id ?? ""}
              node={selectedNode}
              nodeType={selectedNodeType}
              nodes={graph?.nodes ?? []}
              edges={graph?.edges ?? []}
              nodeTypes={catalog?.nodeTypes ?? []}
              edgeTypes={catalog?.edgeTypes ?? []}
              saving={isMutatingEntity}
              disabled={loading || !selectedScenario}
              onUpdateLinks={updateNode}
              onTimeserieDeleted={clearDeletedTimeserieLinks}
            />
          ) : selectedNode ? (
            <NodeForm
              key={`edit-node:${selectedNode.id}`}
              idPrefix="structure-edit-node"
              title="Edit node"
              node={selectedNode}
              nodeTypes={nodeTypes}
              lifetime={{ targetDate, ending: endingNodeIds.has(selectedNode.id) }}
              saving={isMutatingEntity}
              submitLabel="Save node"
              disabled={loading}
              onUpdate={updateNode}
              onDelete={removeNode}
            />
          ) : selectedEdge ? (
            <EdgeForm
              key={`edit-edge:${selectedEdge.id}`}
              idPrefix="structure-edit-edge"
              title="Edit edge"
              edge={selectedEdge}
              nodes={nodes}
              edgeTypes={edgeTypes}
              lifetime={{ targetDate, ending: endingEdgeIds.has(selectedEdge.id) }}
              saving={isMutatingEntity}
              submitLabel="Save edge"
              disabled={loading}
              onUpdate={updateEdge}
              onDelete={removeEdge}
            />
          ) : (
            <section className="detail-card">
              <div className="detail-card__header">
                <h2 className="section-title">Selection</h2>
              </div>
              <p className="muted">Select a node or edge to edit its metadata.</p>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
