import { apiBaseUrl, AuthenticationRequiredError } from "../auth-client";
import type { ChainHint, Refusal } from "./timeline";

export type ModelSummary = { id: string; name: string; description: string | null; version: number; nodes: number };
export type NodeType = { id: string; key: string; name: string; color: string; shape: string; version: number };
export type ConnectionType = { id: string; key: string; name: string; style: string; source_end: string; target_end: string; version: number };
export type AllowedConnection = { connection_type_id: string; source_node_type_id: string; target_node_type_id: string };
export type GraphNode = { id: string; node_type_id: string; name: string; description: string | null; x: number; y: number };
export type GraphConnection = { id: string; connection_type_id: string; source_node_id: string; target_node_id: string };
/** The Base line or a Scenario of a model (`GET …/lines`); `version` is the stale check of a rename or delete. */
export type ModelLine = {
  id: string; name: string; description: string | null; kind: "base" | "scenario"; parent_line_id: string | null; branch_event_id: string | null; version: number; event_count: number; latest_event_date: string | null;
  /** Set when the state a Scenario starts from changed; cleared by `acknowledgeStart`. */
  start_changed_at?: string | null; created_by_user_account_id?: string | null;
};
/** An event of a line; `version` is what a canvas edit sends as `expected_version`. */
export type LineEvent = {
  id: string; line_id: string; occurred_on: string; title: string; version: number; planned: boolean; change_count: number;
  note?: string | null; change_counts?: Record<string, number>; /** Scenarios that start from this event. */ branches?: { line_id: string; name: string }[];
};
/** One change of an event, in order. */
export type EventChange = { position: number; op: string; element_id: string | null; payload: Record<string, unknown> };
/** The graph a line shows after its last event. */
export type Graph = { event: LineEvent | null; node_types: NodeType[]; connection_types: ConnectionType[]; allowed_connections: AllowedConnection[]; nodes: GraphNode[]; connections: GraphConnection[] };

/** A write was refused because the row changed since it was read (HTTP 409 with `latest_version`). */
export class StaleVersionError extends Error {}
/** A write was refused by a rule of the model (HTTP 409 duplicate or 422); `detail` is the structured answer (`reason` and its fields). */
export class RuleError extends Error {
  constructor(message: string, readonly detail: Refusal = {}) { super(message); }
  get reason(): string | undefined { return this.detail.reason; }
}
/** The person's role does not allow the write (HTTP 403). */
export class ForbiddenError extends Error {}
/** An edit would break a later event or Scenario (HTTP 422 `chain_broken`); `cause` is the machine-readable reason and `hint` the structured explanation. The edit was not saved. */
export class ChainBrokenError extends RuleError {
  constructor(readonly cause: string, readonly hint: ChainHint | null = null, detail: Refusal = { reason: "chain_broken" }) { super("chain_broken", detail); }
}

const modelsUrl = (organizationId: string) => `${apiBaseUrl}/api/v1/organizations/${organizationId}/models`;

async function call(url: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(url, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (response.status === 401) throw new AuthenticationRequiredError();
  if (response.status === 403) throw new ForbiddenError("forbidden");
  if (response.status === 409) {
    const detail = ((await response.json().catch(() => null)) as { detail?: Refusal & { latest_version?: number } } | null)?.detail;
    throw detail?.latest_version !== undefined ? new StaleVersionError() : new RuleError("conflict", typeof detail === "object" && detail ? detail : {});
  }
  if (response.status === 422) {
    const detail = ((await response.json().catch(() => null)) as { detail?: Refusal & { cause?: string; hint?: ChainHint } } | null)?.detail;
    const body = typeof detail === "object" && detail ? detail : {};
    throw body.reason === "chain_broken" ? new ChainBrokenError(body.cause ?? "unknown", body.hint ?? null, body) : new RuleError("rule", body);
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

type ElementList = { nodes?: { node: GraphNode }[]; connections?: { connection: GraphConnection }[] };
type LineStateResponse = Omit<Graph, "event"> & { event: LineEvent | null; added?: ElementList; updated?: ElementList; removed?: ElementList };
/** Ids of the nodes and connections the shown event added, updated and removed (the state route's `added`, `updated` and `removed`). */
export type StateChanges = { added: string[]; updated: string[]; removed: string[] };
/** The elements the shown event removed, with their data. */
export type StateGhosts = { nodes: GraphNode[]; connections: GraphConnection[] };
export type LineState = Graph & { changes: StateChanges; ghosts?: StateGhosts };

const changeIds = (list: ElementList | undefined) => [...(list?.nodes ?? []).map((item) => item.node.id), ...(list?.connections ?? []).map((item) => item.connection.id)];

/**
 * The graph of a line after one event (`eventId`), or after the line's last event when none is given (any event, planned or not, as that
 * is the one a canvas edit changes), with the ids the event changed.
 */
export async function loadLineState(organizationId: string, modelId: string, lineId: string, eventId?: string | null, signal?: AbortSignal): Promise<LineState> {
  const line = `${modelsUrl(organizationId)}/${modelId}/lines/${lineId}`;
  let shown = eventId ?? null;
  if (!shown) {
    const events: LineEvent[] = await (await call(`${line}/events`, { signal })).json();
    shown = events[events.length - 1]?.id ?? null;
  }
  const state: LineStateResponse = await (await call(`${line}/state${shown ? `?event_id=${shown}` : ""}`, { signal })).json();
  return {
    event: state.event, node_types: state.node_types, connection_types: state.connection_types, allowed_connections: state.allowed_connections, nodes: state.nodes, connections: state.connections,
    changes: { added: changeIds(state.added), updated: changeIds(state.updated), removed: changeIds(state.removed) },
    ghosts: { nodes: (state.removed?.nodes ?? []).map((item) => item.node), connections: (state.removed?.connections ?? []).map((item) => item.connection) },
  };
}

/** The graph after the line's last event. */
export async function loadGraph(organizationId: string, modelId: string, lineId: string, signal?: AbortSignal): Promise<Graph> {
  const { changes: _changes, ghosts: _ghosts, ...graph } = await loadLineState(organizationId, modelId, lineId, null, signal);
  return graph;
}

/** A line with no events yet (a new Scenario) gets one to hold the canvas edits; the date is today. */
export async function createEditsEvent(organizationId: string, modelId: string, lineId: string, title: string): Promise<LineEvent> {
  const now = new Date();
  const occurredOn = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  return (await call(`${modelsUrl(organizationId)}/${modelId}/lines/${lineId}/events`, { method: "POST", ...json({ occurred_on: occurredOn, title, changes: [] }) })).json();
}

export async function loadLines(organizationId: string, modelId: string): Promise<ModelLine[]> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/lines`)).json();
}

export async function createScenario(organizationId: string, modelId: string, name: string, branchEventId: string): Promise<ModelLine> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/lines`, { method: "POST", ...json({ name, branch_event_id: branchEventId }) })).json();
}

export async function loadEvents(organizationId: string, modelId: string, lineId: string, signal?: AbortSignal): Promise<LineEvent[]> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/lines/${lineId}/events`, { signal })).json();
}

export async function renameLine(organizationId: string, modelId: string, line: ModelLine, name: string): Promise<ModelLine> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/lines/${line.id}`, { method: "PATCH", ...json({ name, expected_version: line.version }) })).json();
}

/** Clears the Scenario's "its start changed" notice. */
export async function acknowledgeStart(organizationId: string, modelId: string, line: ModelLine): Promise<ModelLine> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/lines/${line.id}/acknowledge-start`, { method: "POST" })).json();
}

export type AdoptResult = { line: ModelLine; scenario: ModelLine | null; adopted_events: unknown[] | number; moved_scenarios: number };

export async function adoptLine(organizationId: string, modelId: string, line: ModelLine): Promise<AdoptResult> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/lines/${line.id}/adopt`, { method: "POST", ...json({ expected_version: line.version }) })).json();
}

export type EventInput = { occurred_on: string; title: string; note: string | null };
export type EventDetail = { event: LineEvent; changes: EventChange[]; names: Map<string, string> };

/** One event with its ordered changes, and the names of the elements they refer to (from the state after the event, incl. what it removed, and its own payloads). */
export async function loadEventDetail(organizationId: string, modelId: string, lineId: string, eventId: string): Promise<EventDetail> {
  const base = modelsUrl(organizationId);
  const [event, state] = await Promise.all([
    call(`${base}/${modelId}/events/${eventId}`).then((response) => response.json() as Promise<LineEvent & { changes: EventChange[] }>),
    call(`${base}/${modelId}/lines/${lineId}/state?event_id=${eventId}`).then((response) => response.json() as Promise<{ nodes?: GraphNode[]; node_types?: NodeType[]; connection_types?: ConnectionType[]; removed?: { nodes?: { node: GraphNode }[] }; updated?: { nodes?: { previous?: GraphNode | null }[] } }>),
  ]);
  const names = new Map<string, string>();
  for (const node of state.nodes ?? []) names.set(node.id, node.name);
  for (const item of state.removed?.nodes ?? []) names.set(item.node.id, item.node.name);
  for (const item of state.updated?.nodes ?? []) if (item.previous && !names.has(item.previous.id)) names.set(item.previous.id, item.previous.name);
  for (const type of [...(state.node_types ?? []), ...(state.connection_types ?? [])]) names.set(type.id, type.name);
  for (const change of event.changes) {
    const name = change.payload.name;
    if (change.element_id && typeof name === "string" && !names.has(change.element_id)) names.set(change.element_id, name);
  }
  const { changes, ...summary } = event;
  return { event: summary, changes: [...changes].sort((a, b) => a.position - b.position), names };
}

export async function createEvent(organizationId: string, modelId: string, lineId: string, input: EventInput): Promise<LineEvent> {
  return (await call(`${modelsUrl(organizationId)}/${modelId}/lines/${lineId}/events`, { method: "POST", ...json({ ...input, changes: [] }) })).json();
}

export async function updateEvent(organizationId: string, modelId: string, event: LineEvent, input: EventInput): Promise<LineEvent> {
  return (await call(`${eventUrl(organizationId, modelId, event)}`, { method: "PATCH", ...json({ ...input, expected_version: event.version }) })).json();
}

export async function deleteEvent(organizationId: string, modelId: string, event: LineEvent): Promise<void> {
  await call(`${eventUrl(organizationId, modelId, event)}?expected_version=${event.version}`, { method: "DELETE" });
}

export async function deleteLine(organizationId: string, modelId: string, line: ModelLine): Promise<void> {
  await call(`${modelsUrl(organizationId)}/${modelId}/lines/${line.id}?expected_version=${line.version}`, { method: "DELETE" });
}

// Canvas edits are changes inside an event; `event.version` is the stale check. Moving a node is a position of the line, not an edit.
const eventUrl = (organizationId: string, modelId: string, event: LineEvent) => `${modelsUrl(organizationId)}/${modelId}/events/${event.id}`;

export async function createNode(organizationId: string, modelId: string, event: LineEvent, input: { node_type_id: string; name: string; description?: string | null; x: number; y: number }): Promise<GraphNode> {
  return ((await (await call(`${eventUrl(organizationId, modelId, event)}/nodes`, { method: "POST", ...json({ ...input, expected_version: event.version }) })).json()) as { node: GraphNode }).node;
}

export async function updateNode(organizationId: string, modelId: string, event: LineEvent, node: GraphNode, changes: { name?: string; description?: string | null; node_type_id?: string }): Promise<void> {
  await call(`${eventUrl(organizationId, modelId, event)}/nodes/${node.id}`, { method: "PATCH", ...json({ ...changes, expected_version: event.version }) });
}

export async function deleteNode(organizationId: string, modelId: string, event: LineEvent, node: GraphNode): Promise<void> {
  await call(`${eventUrl(organizationId, modelId, event)}/nodes/${node.id}?expected_version=${event.version}`, { method: "DELETE" });
}

/** Creates a connection and returns its id (the element id the later edits and undo refer to). */
export async function createConnection(organizationId: string, modelId: string, event: LineEvent, input: { connection_type_id: string; source_node_id: string; target_node_id: string }): Promise<{ id: string }> {
  const body = (await (await call(`${eventUrl(organizationId, modelId, event)}/connections`, { method: "POST", ...json({ ...input, expected_version: event.version }) })).json()) as { id?: string; connection?: { id: string } };
  return { id: (body.connection?.id ?? body.id) as string };
}

/** Re-routes a connection: another source and/or target node. */
export async function updateConnection(organizationId: string, modelId: string, event: LineEvent, connection: GraphConnection, changes: { source_node_id?: string; target_node_id?: string; connection_type_id?: string }): Promise<void> {
  await call(`${eventUrl(organizationId, modelId, event)}/connections/${connection.id}`, { method: "PATCH", ...json({ ...changes, expected_version: event.version }) });
}

export async function deleteConnection(organizationId: string, modelId: string, event: LineEvent, connection: GraphConnection): Promise<void> {
  await call(`${eventUrl(organizationId, modelId, event)}/connections/${connection.id}?expected_version=${event.version}`, { method: "DELETE" });
}

export async function saveNodePositions(organizationId: string, modelId: string, lineId: string, positions: { node_id: string; x: number; y: number }[]): Promise<void> {
  await call(`${modelsUrl(organizationId)}/${modelId}/lines/${lineId}/positions`, { method: "PUT", ...json(positions) });
}

export type Metric = { id: string; key: string; name: string; unit: string | null; node_id: string | null; formula: string | null; derived: boolean; version: number; values: number };
export type MetricInput = { key: string; name: string; unit: string | null; node_id: string | null; formula: string | null };
export type SeriesPoint = { period: string; value: number | null };
export type Series = { metric: Metric; points: SeriesPoint[] };

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
