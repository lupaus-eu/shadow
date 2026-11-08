import type { AllowedConnection, ConnectionType, GraphConnection, GraphNode, NodeType } from "../client";

/**
 * The plain data the canvas draws. It knows nothing about versions, lines or events: whoever supplies it (today `useGraphState`)
 * decides where the graph comes from, and the canvas only receives it and reports edits.
 */
export type GraphMarkers = {
  /** Ids of nodes and connections the shown state added, and of those it changed. They are on the canvas and get a mark. */
  added: string[];
  updated: string[];
  /** Ids of elements the shown state removed; they are not on the canvas, the list is for a change list. */
  removed: string[];
};

export type GraphData = {
  nodes: GraphNode[];
  connections: GraphConnection[];
  nodeTypes: NodeType[];
  connectionTypes: ConnectionType[];
  allowedConnections: AllowedConnection[];
  markers: GraphMarkers;
};

/** One change the person made on the canvas. Every change passes through `GraphModeling.applyEdit`. */
export type GraphEdit =
  | { kind: "node.move"; moves: { id: string; x: number; y: number }[] }
  | { kind: "node.create"; nodeTypeId: string; name: string; x: number; y: number }
  | { kind: "node.update"; id: string; name: string; description: string | null }
  | { kind: "node.delete"; id: string }
  | { kind: "connection.create"; connectionTypeId: string; sourceId: string; targetId: string }
  | { kind: "connection.delete"; id: string };

/** Sends an edit to the server. It rejects when the server refuses; the canvas then reverts the optimistic change. */
export type GraphEditSender = (edit: GraphEdit) => Promise<void>;

export const noMarkers: GraphMarkers = { added: [], updated: [], removed: [] };
