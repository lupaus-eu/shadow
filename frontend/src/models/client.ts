import { apiBaseUrl, AuthenticationRequiredError } from "../auth-client";

export type ModelSummary = { id: string; name: string; description: string | null; version: number; nodes: number };
export type NodeType = { id: string; key: string; name: string; color: string; shape: string };
export type ConnectionType = { id: string; key: string; name: string; style: string; source_end: string; target_end: string };
export type AllowedConnection = { connection_type_id: string; source_node_type_id: string; target_node_type_id: string };
export type GraphNode = { id: string; node_type_id: string; name: string; description: string | null; x: number; y: number; version: number };
export type GraphConnection = { id: string; connection_type_id: string; source_node_id: string; target_node_id: string; version: number };
export type Graph = { model: ModelSummary; node_types: NodeType[]; connection_types: ConnectionType[]; allowed_connections: AllowedConnection[]; nodes: GraphNode[]; connections: GraphConnection[] };

/** A write was refused because the row changed since it was read (HTTP 409 with `latest_version`). */
export class StaleVersionError extends Error {}
/** A write was refused by a rule of the model (HTTP 409 duplicate or 422). */
export class RuleError extends Error {}

const modelsUrl = (organizationId: string) => `${apiBaseUrl}/api/v1/organizations/${organizationId}/models`;

async function call(url: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(url, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 409) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { latest_version?: number } } | null)?.detail;
    throw detail?.latest_version !== undefined ? new StaleVersionError() : new RuleError("conflict");
  }
  if (response.status === 422) throw new RuleError("rule");
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response;
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

export async function loadModels(organizationId: string, signal?: AbortSignal): Promise<ModelSummary[]> {
  return (await call(modelsUrl(organizationId), { signal })).json();
}

export async function createModel(organizationId: string, name: string, description: string | null): Promise<ModelSummary> {
  return (await call(modelsUrl(organizationId), { method: "POST", ...json({ name, description }) })).json();
}

export async function renameModel(organizationId: string, model: ModelSummary, name: string, description: string | null): Promise<ModelSummary> {
  return (await call(`${modelsUrl(organizationId)}/${model.id}`, { method: "PATCH", ...json({ name, description, expected_version: model.version }) })).json();
}

export async function deleteModel(organizationId: string, model: ModelSummary): Promise<void> {
  await call(`${modelsUrl(organizationId)}/${model.id}?expected_version=${model.version}`, { method: "DELETE" });
}

export async function loadGraph(organizationId: string, modelId: string, signal?: AbortSignal): Promise<Graph> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}`, { signal })).json();
}

export async function createNode(organizationId: string, modelId: string, input: { node_type_id: string; name: string; x: number; y: number }): Promise<GraphNode> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/nodes`, { method: "POST", ...json(input) })).json();
}

export async function updateNode(organizationId: string, modelId: string, node: GraphNode, changes: { name?: string; description?: string | null; x?: number; y?: number }): Promise<GraphNode> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/nodes/${node.id}`, { method: "PATCH", ...json({ ...changes, expected_version: node.version }) })).json();
}

export async function deleteNode(organizationId: string, modelId: string, node: GraphNode): Promise<void> {
  await call(`${modelsUrl(organizationId)}/${modelId}/nodes/${node.id}?expected_version=${node.version}`, { method: "DELETE" });
}

export async function createConnection(organizationId: string, modelId: string, input: { connection_type_id: string; source_node_id: string; target_node_id: string }): Promise<GraphConnection> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/connections`, { method: "POST", ...json(input) })).json();
}

export async function deleteConnection(organizationId: string, modelId: string, connection: GraphConnection): Promise<void> {
  await call(`${modelsUrl(organizationId)}/${modelId}/connections/${connection.id}?expected_version=${connection.version}`, { method: "DELETE" });
}
