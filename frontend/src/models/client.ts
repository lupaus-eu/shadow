import { apiBaseUrl, AuthenticationRequiredError } from "../auth-client";

export type ModelSummary = { id: string; name: string; description: string | null; version: number; nodes: number };
export type NodeType = { id: string; key: string; name: string; color: string; shape: string; version: number };
export type ConnectionType = { id: string; key: string; name: string; style: string; source_end: string; target_end: string; version: number };
export type AllowedConnection = { connection_type_id: string; source_node_type_id: string; target_node_type_id: string };
export type GraphNode = { id: string; node_type_id: string; name: string; description: string | null; x: number; y: number };
export type GraphConnection = { id: string; connection_type_id: string; source_node_id: string; target_node_id: string };
export type ModelVersion = { id: string; name: string; description: string | null; is_baseline: boolean; base_version_id: string | null; version: number };
/** An event of a line; `version` is what a canvas edit sends as `expected_version`. */
export type LineEvent = { id: string; line_id: string; occurred_on: string; title: string; version: number; planned: boolean; change_count: number };
/** The graph a line shows after its last event (a line has the id of the version it came from until the line picker arrives, ticket 09 of the model timeline). */
export type Graph = { event: LineEvent | null; node_types: NodeType[]; connection_types: ConnectionType[]; allowed_connections: AllowedConnection[]; nodes: GraphNode[]; connections: GraphConnection[] };

/** A write was refused because the row changed since it was read (HTTP 409 with `latest_version`). */
export class StaleVersionError extends Error {}
/** A write was refused by a rule of the model (HTTP 409 duplicate or 422). */
export class RuleError extends Error {}
/** An edit would break a later event or Scenario (HTTP 422 `chain_broken`); `cause` is the machine-readable reason. The edit was not saved. */
export class ChainBrokenError extends RuleError {
  constructor(readonly cause: string) { super("chain_broken"); }
}

const modelsUrl = (organizationId: string) => `${apiBaseUrl}/api/v1/organizations/${organizationId}/models`;

async function call(url: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(url, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 409) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { latest_version?: number } } | null)?.detail;
    throw detail?.latest_version !== undefined ? new StaleVersionError() : new RuleError("conflict");
  }
  if (response.status === 422) {
    const detail = ((await response.json().catch(() => null)) as { detail?: { reason?: string; cause?: string } } | null)?.detail;
    throw detail?.reason === "chain_broken" ? new ChainBrokenError(detail.cause ?? "unknown") : new RuleError("rule");
  }
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

type LineState = Omit<Graph, "event"> & { event: LineEvent | null };

/** The graph after the line's last event (any event, planned or not, as that is the one a canvas edit changes). */
export async function loadGraph(organizationId: string, modelId: string, lineId: string, signal?: AbortSignal): Promise<Graph> {
  const line = `${modelsUrl(organizationId)}/${modelId}/lines/${lineId}`;
  const events: LineEvent[] = await (await call(`${line}/events`, { signal })).json();
  const last = events[events.length - 1];
  const state: LineState = await (await call(`${line}/state${last ? `?event_id=${last.id}` : ""}`, { signal })).json();
  return { event: state.event, node_types: state.node_types, connection_types: state.connection_types, allowed_connections: state.allowed_connections, nodes: state.nodes, connections: state.connections };
}

/** A line with no events yet (a new Scenario) gets one to hold the canvas edits; the date is today. */
export async function createEditsEvent(organizationId: string, modelId: string, lineId: string, title: string): Promise<LineEvent> {
  const now = new Date();
  const occurredOn = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  return (await call(`${modelsUrl(organizationId)}/${modelId}/lines/${lineId}/events`, { method: "POST", ...json({ occurred_on: occurredOn, title, changes: [] }) })).json();
}

export async function createVersion(organizationId: string, modelId: string, name: string, baseVersionId: string | null): Promise<ModelVersion> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/versions`, { method: "POST", ...json({ name, base_version_id: baseVersionId }) })).json();
}

export async function deleteVersion(organizationId: string, modelId: string, version: ModelVersion): Promise<void> {
  await call(`${modelsUrl(organizationId)}/${modelId}/versions/${version.id}?expected_version=${version.version}`, { method: "DELETE" });
}

// Canvas edits are changes inside an event; `event.version` is the stale check. Moving a node is a position of the line, not an edit.
const eventUrl = (organizationId: string, modelId: string, event: LineEvent) => `${modelsUrl(organizationId)}/${modelId}/events/${event.id}`;

export async function createNode(organizationId: string, modelId: string, event: LineEvent, input: { node_type_id: string; name: string; x: number; y: number }): Promise<GraphNode> {
  return ((await (await call(`${eventUrl(organizationId, modelId, event)}/nodes`, { method: "POST", ...json({ ...input, expected_version: event.version }) })).json()) as { node: GraphNode }).node;
}

export async function updateNode(organizationId: string, modelId: string, event: LineEvent, node: GraphNode, changes: { name?: string; description?: string | null; node_type_id?: string }): Promise<void> {
  await call(`${eventUrl(organizationId, modelId, event)}/nodes/${node.id}`, { method: "PATCH", ...json({ ...changes, expected_version: event.version }) });
}

export async function deleteNode(organizationId: string, modelId: string, event: LineEvent, node: GraphNode): Promise<void> {
  await call(`${eventUrl(organizationId, modelId, event)}/nodes/${node.id}?expected_version=${event.version}`, { method: "DELETE" });
}

export async function createConnection(organizationId: string, modelId: string, event: LineEvent, input: { connection_type_id: string; source_node_id: string; target_node_id: string }): Promise<void> {
  await call(`${eventUrl(organizationId, modelId, event)}/connections`, { method: "POST", ...json({ ...input, expected_version: event.version }) });
}

export async function deleteConnection(organizationId: string, modelId: string, event: LineEvent, connection: GraphConnection): Promise<void> {
  await call(`${eventUrl(organizationId, modelId, event)}/connections/${connection.id}?expected_version=${event.version}`, { method: "DELETE" });
}

export async function saveNodePositions(organizationId: string, modelId: string, lineId: string, positions: { node_id: string; x: number; y: number }[]): Promise<void> {
  await call(`${modelsUrl(organizationId)}/${modelId}/lines/${lineId}/positions`, { method: "PUT", ...json(positions) });
}

export async function loadVersions(organizationId: string, modelId: string): Promise<ModelVersion[]> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/versions`)).json();
}

export type Metric = { id: string; key: string; name: string; unit: string | null; node_id: string | null; formula: string | null; derived: boolean; version: number; values: number };
export type MetricInput = { key: string; name: string; unit: string | null; node_id: string | null; formula: string | null };
export type SeriesPoint = { period: string; value: number | null };
export type Series = { metric: Metric; points: SeriesPoint[] };

// A line has the id of the version it came from (model timeline ticket 04), so the tabs pass the selected version id until the line picker arrives (ticket 09).
const metricsUrl = (organizationId: string, modelId: string, lineId: string) => `${modelsUrl(organizationId)}/${modelId}/lines/${lineId}/metrics`;

export async function loadMetrics(organizationId: string, modelId: string, lineId: string): Promise<Metric[]> {
  return (await call(metricsUrl(organizationId, modelId, lineId))).json();
}

export async function createMetric(organizationId: string, modelId: string, lineId: string, input: MetricInput): Promise<Metric> {
  return (await call(metricsUrl(organizationId, modelId, lineId), { method: "POST", ...json(input) })).json();
}

export async function updateMetric(organizationId: string, modelId: string, lineId: string, metric: Metric, input: MetricInput): Promise<Metric> {
  return (await call(`${metricsUrl(organizationId, modelId, lineId)}/${metric.id}`, { method: "PATCH", ...json({ ...input, expected_version: metric.version }) })).json();
}

export async function deleteMetric(organizationId: string, modelId: string, lineId: string, metric: Metric): Promise<void> {
  await call(`${metricsUrl(organizationId, modelId, lineId)}/${metric.id}?expected_version=${metric.version}`, { method: "DELETE" });
}

export async function loadSeries(organizationId: string, modelId: string, lineId: string, metricId: string): Promise<Series> {
  return (await call(`${metricsUrl(organizationId, modelId, lineId)}/${metricId}/series`)).json();
}

export async function saveValues(organizationId: string, modelId: string, lineId: string, metricId: string, values: SeriesPoint[]): Promise<Series> {
  return (await call(`${metricsUrl(organizationId, modelId, lineId)}/${metricId}/values`, { method: "PUT", ...json({ values }) })).json();
}

export type SimulationMethod = "linear" | "seasonal" | "holt" | "prophet";
export type Adjustment = { metric_key: string; change_pct: number };
export type Simulation = { id: string; line_id: string; name: string; method: SimulationMethod; horizon_months: number; adjustments: Adjustment[]; skipped: Record<string, string>; history_end: string | null; created_at: string };
export type ForecastPoint = { period: string; value: number; lower: number | null; upper: number | null };
export type MetricResult = { key: string; name: string; unit: string | null; derived: boolean; history: { period: string; value: number }[]; forecast: ForecastPoint[] };
export type SimulationResult = { simulation: Simulation; metrics: MetricResult[] };

const simulationsUrl = (organizationId: string, modelId: string, lineId: string) => `${modelsUrl(organizationId)}/${modelId}/lines/${lineId}/simulations`;

export async function loadSimulations(organizationId: string, modelId: string, lineId: string): Promise<Simulation[]> {
  return (await call(simulationsUrl(organizationId, modelId, lineId))).json();
}

export async function runSimulation(organizationId: string, modelId: string, lineId: string, input: { name: string; method: SimulationMethod; horizon_months: number; adjustments: Adjustment[] }): Promise<SimulationResult> {
  return (await call(simulationsUrl(organizationId, modelId, lineId), { method: "POST", ...json(input) })).json();
}

export async function loadSimulation(organizationId: string, modelId: string, lineId: string, simulationId: string): Promise<SimulationResult> {
  return (await call(`${simulationsUrl(organizationId, modelId, lineId)}/${simulationId}`)).json();
}

export async function deleteSimulation(organizationId: string, modelId: string, lineId: string, simulationId: string): Promise<void> {
  await call(`${simulationsUrl(organizationId, modelId, lineId)}/${simulationId}`, { method: "DELETE" });
}

export type Finding = { key: string; name: string; unit: string | null; derived: boolean; start: number | null; end: number | null; change_pct: number | null; trend: string; turns_negative: string | null; band_ratio: number | null; versus: number | null };
export type RecommendationStatus = "proposed" | "accepted" | "dismissed";
export type Recommendation = { id: string; kind: string; severity: "high" | "medium" | "low"; metric_key: string; title: string; rationale: string; status: RecommendationStatus; version: number };
export type Analysis = { summary: string | null; summary_at: string | null; summary_author: string | null; simulation: Simulation; compared_to: Simulation | null; findings: Finding[]; recommendations: Recommendation[] };

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

export type ImportReport = { metrics: number; values: number; unknown_metrics: string[]; derived_metrics: string[]; invalid_cells: number };

/** Sends a CSV or Excel file as the request body; the server reports what it applied and what it skipped. */
export async function importValues(organizationId: string, modelId: string, lineId: string, file: File): Promise<ImportReport> {
  const response = await fetch(`${modelsUrl(organizationId)}/${modelId}/lines/${lineId}/metrics/import?filename=${encodeURIComponent(file.name)}`, { method: "POST", credentials: "include", body: file, headers: { "Content-Type": "application/octet-stream" } });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 422) throw new RuleError(((await response.json().catch(() => null)) as { detail?: string } | null)?.detail ?? "rule");
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

async function download(url: string, fallbackName: string): Promise<void> {
  const response = await fetch(url, { credentials: "include" });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await response.blob());
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}

export const exportValues = (organizationId: string, modelId: string, lineId: string, format: "csv" | "xlsx") => download(`${modelsUrl(organizationId)}/${modelId}/lines/${lineId}/metrics/export?format=${format}`, `metrics.${format}`);
export const exportAnalysis = (organizationId: string, modelId: string, simulationId: string, compareTo: string | null) => download(`${modelsUrl(organizationId)}/${modelId}/simulations/${simulationId}/analysis/export${compareTo ? `?compare_to=${compareTo}` : ""}`, "analysis.xlsx");
