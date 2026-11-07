import { apiBaseUrl, AuthenticationRequiredError } from "../auth-client";

export type ModelSummary = { id: string; name: string; description: string | null; version: number; nodes: number };
export type NodeType = { id: string; key: string; name: string; color: string; shape: string; version: number };
export type ConnectionType = { id: string; key: string; name: string; style: string; source_end: string; target_end: string; version: number };
export type AllowedConnection = { connection_type_id: string; source_node_type_id: string; target_node_type_id: string };
export type GraphNode = { id: string; node_type_id: string; name: string; description: string | null; x: number; y: number; version: number };
export type GraphConnection = { id: string; connection_type_id: string; source_node_id: string; target_node_id: string; version: number };
export type ModelVersion = { id: string; name: string; description: string | null; is_baseline: boolean; base_version_id: string | null; version: number };
export type NodeChange = { node_id: string; name: string; fields: string[] };
export type ConnectionChange = { connection_id: string; connection_type_id: string; source: string; target: string };
export type VersionChanges = { version: ModelVersion; base: ModelVersion | null; added_nodes: NodeChange[]; removed_nodes: NodeChange[]; changed_nodes: NodeChange[]; added_connections: ConnectionChange[]; removed_connections: ConnectionChange[] };
export type Graph = { model: ModelSummary; version: ModelVersion; versions: ModelVersion[]; node_types: NodeType[]; connection_types: ConnectionType[]; allowed_connections: AllowedConnection[]; nodes: GraphNode[]; connections: GraphConnection[] };

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

export async function loadGraph(organizationId: string, modelId: string, versionId?: string | null, signal?: AbortSignal): Promise<Graph> {
  const query = versionId ? `?version_id=${versionId}` : "";
  return (await call(`${modelsUrl(organizationId)}/${modelId}${query}`, { signal })).json();
}

export async function createVersion(organizationId: string, modelId: string, name: string, baseVersionId: string | null): Promise<ModelVersion> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/versions`, { method: "POST", ...json({ name, base_version_id: baseVersionId }) })).json();
}

export async function deleteVersion(organizationId: string, modelId: string, version: ModelVersion): Promise<void> {
  await call(`${modelsUrl(organizationId)}/${modelId}/versions/${version.id}?expected_version=${version.version}`, { method: "DELETE" });
}

export async function loadVersionChanges(organizationId: string, modelId: string, versionId: string): Promise<VersionChanges> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/versions/${versionId}/changes`)).json();
}

export async function createNode(organizationId: string, modelId: string, input: { node_type_id: string; name: string; x: number; y: number; version_id?: string }): Promise<GraphNode> {
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

export async function loadVersions(organizationId: string, modelId: string): Promise<ModelVersion[]> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/versions`)).json();
}

export type Metric = { id: string; key: string; name: string; unit: string | null; node_id: string | null; formula: string | null; derived: boolean; version: number; values: number };
export type MetricInput = { key: string; name: string; unit: string | null; node_id: string | null; formula: string | null };
export type SeriesPoint = { period: string; value: number | null };
export type Series = { metric: Metric; points: SeriesPoint[] };

const metricsUrl = (organizationId: string, modelId: string, versionId: string) => `${modelsUrl(organizationId)}/${modelId}/versions/${versionId}/metrics`;

export async function loadMetrics(organizationId: string, modelId: string, versionId: string): Promise<Metric[]> {
  return (await call(metricsUrl(organizationId, modelId, versionId))).json();
}

export async function createMetric(organizationId: string, modelId: string, versionId: string, input: MetricInput): Promise<Metric> {
  return (await call(metricsUrl(organizationId, modelId, versionId), { method: "POST", ...json(input) })).json();
}

export async function updateMetric(organizationId: string, modelId: string, versionId: string, metric: Metric, input: MetricInput): Promise<Metric> {
  return (await call(`${metricsUrl(organizationId, modelId, versionId)}/${metric.id}`, { method: "PATCH", ...json({ ...input, expected_version: metric.version }) })).json();
}

export async function deleteMetric(organizationId: string, modelId: string, versionId: string, metric: Metric): Promise<void> {
  await call(`${metricsUrl(organizationId, modelId, versionId)}/${metric.id}?expected_version=${metric.version}`, { method: "DELETE" });
}

export async function loadSeries(organizationId: string, modelId: string, versionId: string, metricId: string): Promise<Series> {
  return (await call(`${metricsUrl(organizationId, modelId, versionId)}/${metricId}/series`)).json();
}

export async function saveValues(organizationId: string, modelId: string, versionId: string, metricId: string, values: SeriesPoint[]): Promise<Series> {
  return (await call(`${metricsUrl(organizationId, modelId, versionId)}/${metricId}/values`, { method: "PUT", ...json({ values }) })).json();
}

export type SimulationMethod = "linear" | "seasonal" | "holt" | "prophet";
export type Adjustment = { metric_key: string; change_pct: number };
export type Simulation = { id: string; version_id: string; name: string; method: SimulationMethod; horizon_months: number; adjustments: Adjustment[]; skipped: Record<string, string>; history_end: string | null; created_at: string };
export type ForecastPoint = { period: string; value: number; lower: number | null; upper: number | null };
export type MetricResult = { key: string; name: string; unit: string | null; derived: boolean; history: { period: string; value: number }[]; forecast: ForecastPoint[] };
export type SimulationResult = { simulation: Simulation; metrics: MetricResult[] };

const simulationsUrl = (organizationId: string, modelId: string, versionId: string) => `${modelsUrl(organizationId)}/${modelId}/versions/${versionId}/simulations`;

export async function loadSimulations(organizationId: string, modelId: string, versionId: string): Promise<Simulation[]> {
  return (await call(simulationsUrl(organizationId, modelId, versionId))).json();
}

export async function runSimulation(organizationId: string, modelId: string, versionId: string, input: { name: string; method: SimulationMethod; horizon_months: number; adjustments: Adjustment[] }): Promise<SimulationResult> {
  return (await call(simulationsUrl(organizationId, modelId, versionId), { method: "POST", ...json(input) })).json();
}

export async function loadSimulation(organizationId: string, modelId: string, versionId: string, simulationId: string): Promise<SimulationResult> {
  return (await call(`${simulationsUrl(organizationId, modelId, versionId)}/${simulationId}`)).json();
}

export async function deleteSimulation(organizationId: string, modelId: string, versionId: string, simulationId: string): Promise<void> {
  await call(`${simulationsUrl(organizationId, modelId, versionId)}/${simulationId}`, { method: "DELETE" });
}

export type Finding = { key: string; name: string; unit: string | null; derived: boolean; start: number | null; end: number | null; change_pct: number | null; trend: string; turns_negative: string | null; band_ratio: number | null; versus: number | null };
export type RecommendationStatus = "proposed" | "accepted" | "dismissed";
export type Recommendation = { id: string; kind: string; severity: "high" | "medium" | "low"; metric_key: string; title: string; rationale: string; status: RecommendationStatus; version: number };
export type Analysis = { ai_available: boolean; ai_summary: string | null; ai_generated_at: string | null; simulation: Simulation; compared_to: Simulation | null; findings: Finding[]; recommendations: Recommendation[] };

const analysisUrl = (organizationId: string, modelId: string, simulationId: string, compareTo: string | null) => `${modelsUrl(organizationId)}/${modelId}/simulations/${simulationId}/analysis${compareTo ? `?compare_to=${compareTo}` : ""}`;

export async function loadAnalysis(organizationId: string, modelId: string, simulationId: string, compareTo: string | null): Promise<Analysis> {
  return (await call(analysisUrl(organizationId, modelId, simulationId, compareTo))).json();
}

export async function generateAnalysis(organizationId: string, modelId: string, simulationId: string, compareTo: string | null): Promise<Analysis> {
  return (await call(analysisUrl(organizationId, modelId, simulationId, compareTo), { method: "POST" })).json();
}

export async function decideRecommendation(organizationId: string, modelId: string, simulationId: string, recommendation: Recommendation, status: RecommendationStatus): Promise<Recommendation> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/simulations/${simulationId}/recommendations/${recommendation.id}`, { method: "PATCH", ...json({ status, expected_version: recommendation.version }) })).json();
}

const typesUrl = (organizationId: string, modelId: string, kind: "node-types" | "connection-types") => `${modelsUrl(organizationId)}/${modelId}/${kind}`;

export async function createNodeType(organizationId: string, modelId: string, input: { name: string; color: string }): Promise<NodeType> {
  return (await call(typesUrl(organizationId, modelId, "node-types"), { method: "POST", ...json(input) })).json();
}

export async function updateNodeType(organizationId: string, modelId: string, type: NodeType, changes: { name?: string; color?: string }): Promise<NodeType> {
  return (await call(`${typesUrl(organizationId, modelId, "node-types")}/${type.id}`, { method: "PATCH", ...json({ ...changes, expected_version: type.version }) })).json();
}

export async function deleteNodeType(organizationId: string, modelId: string, type: NodeType): Promise<void> {
  await call(`${typesUrl(organizationId, modelId, "node-types")}/${type.id}?expected_version=${type.version}`, { method: "DELETE" });
}

export async function createConnectionType(organizationId: string, modelId: string, input: { name: string; style: string; source_end: string; target_end: string }): Promise<ConnectionType> {
  return (await call(typesUrl(organizationId, modelId, "connection-types"), { method: "POST", ...json(input) })).json();
}

export async function updateConnectionType(organizationId: string, modelId: string, type: ConnectionType, changes: { name?: string; style?: string; source_end?: string; target_end?: string }): Promise<ConnectionType> {
  return (await call(`${typesUrl(organizationId, modelId, "connection-types")}/${type.id}`, { method: "PATCH", ...json({ ...changes, expected_version: type.version }) })).json();
}

export async function deleteConnectionType(organizationId: string, modelId: string, type: ConnectionType): Promise<void> {
  await call(`${typesUrl(organizationId, modelId, "connection-types")}/${type.id}?expected_version=${type.version}`, { method: "DELETE" });
}

export async function allowConnection(organizationId: string, modelId: string, rule: AllowedConnection): Promise<void> {
  await call(`${modelsUrl(organizationId)}/${modelId}/allowed-connections`, { method: "POST", ...json(rule) });
}

export async function disallowConnection(organizationId: string, modelId: string, rule: AllowedConnection): Promise<void> {
  await call(`${modelsUrl(organizationId)}/${modelId}/allowed-connections?${new URLSearchParams(rule)}`, { method: "DELETE" });
}

export async function generateAiAnalysis(organizationId: string, modelId: string, simulationId: string, compareTo: string | null, language: string): Promise<Analysis> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/simulations/${simulationId}/analysis/ai`, { method: "POST", ...json({ language, compare_to: compareTo }) })).json();
}

export type MergeResult = { base: ModelVersion; added_nodes: number; removed_nodes: number; changed_nodes: number; added_connections: number; removed_connections: number; skipped_connections: number };

export async function mergeVersion(organizationId: string, modelId: string, version: ModelVersion): Promise<MergeResult> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/versions/${version.id}/merge`, { method: "POST", ...json({ expected_version: version.version }) })).json();
}
