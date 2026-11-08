import type { ConnectionType, GraphConnection, GraphNode } from "../client";
import { connectionOptions, type ConnectionRefusal } from "./diagram/GraphRules";
import type { GraphData } from "./graph-types";

/** Pure helpers for drawing: where a new node goes, what a delete takes with it, which connections two nodes may have. */

export type Point = { x: number; y: number };

/** How far a new node is moved aside when another node sits where it would go (so a row of new nodes does not stack on one spot). */
export const SPOT_STEP = 24;

/**
 * The top-left of a new node: `wanted` (the centre of the view) unless a node is already within a step of it, then the next free spot
 * down and to the right. The first node of a view is exactly at the centre.
 */
export function freeSpot(wanted: Point, taken: Point[]): Point {
  for (let step = 0; step < 100; step++) {
    const spot = { x: wanted.x + step * SPOT_STEP, y: wanted.y + step * SPOT_STEP };
    if (!taken.some((other) => Math.abs(other.x - spot.x) < SPOT_STEP && Math.abs(other.y - spot.y) < SPOT_STEP)) return spot;
  }
  return wanted;
}

export type DeleteSummary = {
  nodes: GraphNode[];
  /** Every connection that goes: the selected ones and those touching a deleted node, once each. */
  connections: { connection: GraphConnection; type: ConnectionType | undefined; source: GraphNode | undefined; target: GraphNode | undefined; selected: boolean }[];
  /** The selected connections that touch no deleted node (the ones sent on their own). */
  alone: string[];
};

/** What deleting a set takes with it. Ids that are not in the graph are ignored. */
export function deleteSummary(graph: GraphData, nodeIds: Iterable<string>, connectionIds: Iterable<string>): DeleteSummary {
  const nodeSet = new Set(nodeIds);
  const connectionSet = new Set(connectionIds);
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const types = new Map(graph.connectionTypes.map((type) => [type.id, type]));
  const nodes = graph.nodes.filter((node) => nodeSet.has(node.id));
  const going = graph.connections.filter((item) => connectionSet.has(item.id) || nodeSet.has(item.source_node_id) || nodeSet.has(item.target_node_id));
  return {
    nodes,
    connections: going.map((connection) => ({ connection, type: types.get(connection.connection_type_id), source: byId.get(connection.source_node_id), target: byId.get(connection.target_node_id), selected: connectionSet.has(connection.id) })),
    alone: going.filter((item) => connectionSet.has(item.id) && !nodeSet.has(item.source_node_id) && !nodeSet.has(item.target_node_id)).map((item) => item.id),
  };
}

export type ConnectionPlan =
  | { kind: "create"; connectionTypeId: string }
  /** More than one type fits: the person picks. */
  | { kind: "choose"; types: ConnectionType[] }
  | { kind: "refused"; cause: ConnectionRefusal; sourceType: string | undefined; targetType: string | undefined };

/**
 * What to do when the person has joined two nodes: refuse (self, not allowed, duplicate), create at once (one type fits, or `preset`
 * names the type and it fits) or ask which type. With a `preset` only that type is considered, so its refusal says why that one failed.
 */
export function planConnection(graph: GraphData, sourceId: string, targetId: string, preset?: string | null): ConnectionPlan {
  const source = graph.nodes.find((node) => node.id === sourceId);
  const target = graph.nodes.find((node) => node.id === targetId);
  const typeName = (node: GraphNode | undefined) => graph.nodeTypes.find((type) => type.id === node?.node_type_id)?.name;
  const names = { sourceType: typeName(source), targetType: typeName(target) };
  if (!source || !target) return { kind: "refused", cause: "not_allowed", ...names };
  const allowed = new Set(graph.allowedConnections.map((item) => `${item.connection_type_id}|${item.source_node_type_id}|${item.target_node_type_id}`));
  const options = connectionOptions({
    allowed,
    connectionTypeIds: preset ? [preset] : graph.connectionTypes.map((type) => type.id),
    source: { id: source.id, nodeTypeId: source.node_type_id },
    target: { id: target.id, nodeTypeId: target.node_type_id },
    existing: graph.connections.map((item) => ({ id: item.id, connectionTypeId: item.connection_type_id, sourceId: item.source_node_id, targetId: item.target_node_id })),
  });
  if (options.refusal) return { kind: "refused", cause: options.refusal, ...names };
  if (options.types.length === 1) return { kind: "create", connectionTypeId: options.types[0] };
  const typeById = new Map(graph.connectionTypes.map((type) => [type.id, type]));
  return { kind: "choose", types: options.types.map((id) => typeById.get(id)).filter((type): type is ConnectionType => !!type) };
}
