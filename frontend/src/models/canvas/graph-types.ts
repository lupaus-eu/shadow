import type { AllowedConnection, ConnectionType, GraphConnection, GraphNode, NodeType } from "../client";

/**
 * The plain data the canvas draws. It knows nothing about versions, lines or changes: whoever supplies it (today `useGraphState`)
 * decides where the graph comes from, and the canvas only receives it and reports edits.
 */
export type GraphMarkers = {
  /** Ids of nodes and connections the shown state added, and of those it changed. They are on the canvas and get a mark. */
  added: string[];
  updated: string[];
  /** Ids of elements the shown state removed; they are not on the canvas, the list is for a change list. */
  removed: string[];
};

/** Nodes and connections the shown state removed, with their data and last drawn place; drawn as outlines that cannot be edited. */
export type Ghosts = { nodes: GraphNode[]; connections: GraphConnection[] };

export type GraphData = {
  nodes: GraphNode[];
  connections: GraphConnection[];
  nodeTypes: NodeType[];
  connectionTypes: ConnectionType[];
  allowedConnections: AllowedConnection[];
  markers: GraphMarkers;
  ghosts?: Ghosts;
};

/**
 * One change the person made on the canvas. Every change passes through `GraphModeling.applyEdit`. `elements.delete` is the one compound
 * edit: nodes (and the connections touching them, which the server removes with them) and connections deleted together, one undo step.
 * `connection.reroute` points an existing connection at other nodes.
 */
export type GraphEdit =
  | { kind: "node.move"; moves: { id: string; x: number; y: number }[] }
  | { kind: "node.create"; nodeTypeId: string; name: string; description?: string | null; x: number; y: number }
  | { kind: "node.update"; id: string; name: string; description: string | null }
  | { kind: "node.delete"; id: string }
  | { kind: "connection.create"; connectionTypeId: string; sourceId: string; targetId: string }
  | { kind: "connection.delete"; id: string }
  | { kind: "connection.reroute"; id: string; sourceId: string; targetId: string }
  | { kind: "elements.delete"; nodeIds: string[]; connectionIds: string[] };

/** What a write tells back: the id the server gave a created element (a later undo of the creation deletes it). */
export type EditResult = { id?: string } | void;

/** Sends an edit to the server. It rejects when the server refuses; the canvas then reverts the optimistic change. */
export type GraphEditSender = (edit: GraphEdit) => Promise<EditResult>;

export const noMarkers: GraphMarkers = { added: [], updated: [], removed: [] };
