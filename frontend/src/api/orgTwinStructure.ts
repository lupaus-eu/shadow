export type JsonObject = Record<string, unknown>;

export type GraphPosition = {
  x: number;
  y: number;
};

export type GraphNodeDto = {
  id: string;
  name: string;
  description: string;
  nodeTypeId: string;
  createDate: string | null;
  position: GraphPosition | null;
  attributes: JsonObject;
};

export type GraphEdgeDto = {
  id: string;
  name: string;
  description: string;
  edgeTypeId: string;
  sourceNodeId: string;
  targetNodeId: string;
  createDate: string | null;
  attributes: JsonObject;
};

export type GraphDto = {
  id: string;
  name: string;
  description: string;
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
};

export type NodeTypeMetadataDto = {
  id: string;
  name: string | null;
  displayName: string;
  color: string | null;
  shape: string | null;
};

export type EdgeTypeMetadataDto = {
  id: string;
  name: string | null;
  displayName: string;
  style: string | null;
  sourceEnd: string | null;
  targetEnd: string | null;
};

export type AllowedConnectionMetadataDto = {
  edgeTypeId: string;
  sourceNodeTypeId: string;
  targetNodeTypeId: string;
};

export type GraphTypeCatalogDto = {
  nodeTypes: NodeTypeMetadataDto[];
  edgeTypes: EdgeTypeMetadataDto[];
  allowedConnections: AllowedConnectionMetadataDto[];
};

export type GraphNodeCreateRequest = {
  id: string;
  name: string;
  description?: string | null;
  nodeTypeId: string;
  position?: GraphPosition | null;
  attributes?: JsonObject;
};

export type GraphNodeUpdateRequest = {
  name?: string;
  description?: string | null;
  nodeTypeId?: string;
  position?: GraphPosition | null;
  attributes?: JsonObject;
};

export type GraphEdgeCreateRequest = {
  id: string;
  name: string;
  description?: string | null;
  edgeTypeId: string;
  sourceNodeId: string;
  targetNodeId: string;
  attributes?: JsonObject;
};

export type GraphEdgeUpdateRequest = {
  name?: string;
  description?: string | null;
  edgeTypeId?: string;
  sourceNodeId?: string;
  targetNodeId?: string;
  attributes?: JsonObject;
};

export type BulkPositionUpdateRequest = {
  positions: Array<GraphPosition & { nodeId: string }>;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail ? `API request failed (${status}). ${detail}` : `API request failed (${status}).`);
    this.name = "ApiError";
    this.status = status;
  }
}

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ?? "";

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) return path;
  return `${API_BASE_URL.replace(/\/+$/, "")}${path}`;
}

async function requestJson<T>(
  path: string,
  init?: RequestInit,
  signal?: AbortSignal
): Promise<T> {
  const res = await fetch(buildApiUrl(path), {
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...init?.headers
    },
    ...init,
    signal
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

function graphPath(orgId: string, scenarioId: string, orgStateId: string) {
  return (
    `/api/v1/organisations/${encodeURIComponent(orgId)}` +
    `/scenarios/${encodeURIComponent(scenarioId)}` +
    `/org-states/${encodeURIComponent(orgStateId)}/graph`
  );
}

export async function fetchGraph(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  signal?: AbortSignal
): Promise<GraphDto> {
  return requestJson<GraphDto>(
    graphPath(orgId, scenarioId, orgStateId),
    { method: "GET" },
    signal
  );
}

export async function fetchGraphTypeCatalog(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  signal?: AbortSignal
): Promise<GraphTypeCatalogDto> {
  return requestJson<GraphTypeCatalogDto>(
    `${graphPath(orgId, scenarioId, orgStateId)}/types`,
    { method: "GET" },
    signal
  );
}

export async function createGraphNode(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  payload: GraphNodeCreateRequest,
  signal?: AbortSignal
): Promise<GraphNodeDto> {
  return requestJson<GraphNodeDto>(
    `${graphPath(orgId, scenarioId, orgStateId)}/nodes`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    signal
  );
}

export async function updateGraphNode(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  nodeId: string,
  payload: GraphNodeUpdateRequest,
  signal?: AbortSignal
): Promise<GraphNodeDto> {
  return requestJson<GraphNodeDto>(
    `${graphPath(orgId, scenarioId, orgStateId)}/nodes/${encodeURIComponent(nodeId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    },
    signal
  );
}

export async function deleteGraphNode(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  nodeId: string,
  signal?: AbortSignal
): Promise<void> {
  return requestJson<void>(
    `${graphPath(orgId, scenarioId, orgStateId)}/nodes/${encodeURIComponent(nodeId)}`,
    { method: "DELETE" },
    signal
  );
}

export async function createGraphEdge(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  payload: GraphEdgeCreateRequest,
  signal?: AbortSignal
): Promise<GraphEdgeDto> {
  return requestJson<GraphEdgeDto>(
    `${graphPath(orgId, scenarioId, orgStateId)}/edges`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    signal
  );
}

export async function updateGraphEdge(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  edgeId: string,
  payload: GraphEdgeUpdateRequest,
  signal?: AbortSignal
): Promise<GraphEdgeDto> {
  return requestJson<GraphEdgeDto>(
    `${graphPath(orgId, scenarioId, orgStateId)}/edges/${encodeURIComponent(edgeId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    },
    signal
  );
}

export async function deleteGraphEdge(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  edgeId: string,
  signal?: AbortSignal
): Promise<void> {
  return requestJson<void>(
    `${graphPath(orgId, scenarioId, orgStateId)}/edges/${encodeURIComponent(edgeId)}`,
    { method: "DELETE" },
    signal
  );
}

export async function bulkUpdatePositions(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  payload: BulkPositionUpdateRequest,
  signal?: AbortSignal
): Promise<GraphDto> {
  return requestJson<GraphDto>(
    `${graphPath(orgId, scenarioId, orgStateId)}/positions`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    },
    signal
  );
}
