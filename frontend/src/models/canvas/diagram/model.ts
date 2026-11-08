import type { ConnectionType, GraphConnection, GraphNode, NodeType } from "../../client";

/** "added" and "updated" mark an element the shown state changed; null is unchanged. */
export type ChangeMark = "added" | "updated" | null;

/** What a node shape carries in `businessObject`. `pending` is an optimistic element the server has not confirmed yet. */
export type NodeObject = { kind: "node"; node: GraphNode; nodeType: NodeType | undefined; change: ChangeMark; pending?: boolean };
export type ConnectionObject = { kind: "connection"; connection: GraphConnection; connectionType: ConnectionType | undefined; change: ChangeMark; pending?: boolean };
export type ElementObject = NodeObject | ConnectionObject;

/** The part of a diagram-js shape or connection the Shadow modules touch. */
export type GraphElement = {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  businessObject: ElementObject;
  parent?: unknown;
  waypoints?: { x: number; y: number }[];
  source?: GraphElement;
  target?: GraphElement;
  incoming: GraphElement[];
  outgoing: GraphElement[];
};

export const isNodeElement = (element: unknown): element is GraphElement & { businessObject: NodeObject } =>
  (element as GraphElement | undefined)?.businessObject?.kind === "node";
export const isConnectionElement = (element: unknown): element is GraphElement & { businessObject: ConnectionObject } =>
  (element as GraphElement | undefined)?.businessObject?.kind === "connection";

let pendingCounter = 0;
/** An id for an element drawn before the server has confirmed it; it is replaced by the real element on the next load. */
export const pendingId = () => `pending-${++pendingCounter}`;

/** The part of `elementRegistry` the Shadow modules use, typed with Shadow's elements. */
export type RegistryLike = { get(id: string): GraphElement | undefined; filter(fn: (element: GraphElement) => boolean): GraphElement[] };
