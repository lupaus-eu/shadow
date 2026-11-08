import type { AllowedConnection, ConnectionType, NodeType } from "../../client";
import RuleProvider from "diagram-js/lib/features/rules/RuleProvider.js";
import type EventBus from "diagram-js/lib/core/EventBus.js";

import type { GraphData } from "../graph-types";
import { isConnectionElement, isNodeElement, type GraphElement, type RegistryLike } from "./model";

export type ConnectionRefusal = "not_allowed" | "self" | "duplicate";
export type ConnectionCheck = { allowed: true } | { allowed: false; cause: ConnectionRefusal };

export const connectionKey = (connectionTypeId: string, sourceNodeTypeId: string, targetNodeTypeId: string) => `${connectionTypeId}|${sourceNodeTypeId}|${targetNodeTypeId}`;

/**
 * Whether a connection may be drawn: never from a node to itself, only for a (connection type, source node type, target node type)
 * the metamodel allows, and never a second one of the same type between the same two nodes. The cause lets the interface word the refusal.
 */
export function checkConnection(input: {
  allowed: ReadonlySet<string>;
  connectionTypeId: string;
  source: { id: string; nodeTypeId: string };
  target: { id: string; nodeTypeId: string };
  existing: Iterable<{ id?: string; connectionTypeId: string; sourceId: string; targetId: string }>;
  /** A connection that is being re-routed does not count as a duplicate of itself. */
  ignoreId?: string;
}): ConnectionCheck {
  if (input.source.id === input.target.id) return { allowed: false, cause: "self" };
  if (!input.allowed.has(connectionKey(input.connectionTypeId, input.source.nodeTypeId, input.target.nodeTypeId))) return { allowed: false, cause: "not_allowed" };
  for (const item of input.existing) {
    if (input.ignoreId !== undefined && item.id === input.ignoreId) continue;
    if (item.connectionTypeId === input.connectionTypeId && item.sourceId === input.source.id && item.targetId === input.target.id) return { allowed: false, cause: "duplicate" };
  }
  return { allowed: true };
}

export type ConnectionOptions = { types: string[]; refusal: null } | { types: []; refusal: ConnectionRefusal };

/**
 * The connection types that may join two nodes, in the order of `connectionTypeIds`: those the metamodel allows from the source's node
 * type to the target's and that the two nodes do not have already. When there are none, `refusal` says why (a node joined to itself;
 * no type allowed between these node types; every allowed type exists already), so the interface can word one of three reasons.
 */
export function connectionOptions(input: {
  allowed: ReadonlySet<string>;
  connectionTypeIds: Iterable<string>;
  source: { id: string; nodeTypeId: string };
  target: { id: string; nodeTypeId: string };
  existing: Iterable<{ id?: string; connectionTypeId: string; sourceId: string; targetId: string }>;
}): ConnectionOptions {
  if (input.source.id === input.target.id) return { types: [], refusal: "self" };
  const existing = [...input.existing];
  const permitted = [...input.connectionTypeIds].filter((typeId) => input.allowed.has(connectionKey(typeId, input.source.nodeTypeId, input.target.nodeTypeId)));
  if (permitted.length === 0) return { types: [], refusal: "not_allowed" };
  const free = permitted.filter((typeId) => checkConnection({ allowed: input.allowed, connectionTypeId: typeId, source: input.source, target: input.target, existing }).allowed);
  return free.length === 0 ? { types: [], refusal: "duplicate" } : { types: free, refusal: null };
}

export const allowedKeys = (allowed: readonly AllowedConnection[]) => new Set(allowed.map((item) => connectionKey(item.connection_type_id, item.source_node_type_id, item.target_node_type_id)));

/** What the rules need to know about the graph and the person. Updated by the importer on every load. */
export class GraphContext {
  readOnly = false;
  allowed: ReadonlySet<string> = new Set();
  connectionTypes: ConnectionType[] = [];
  nodeTypes: NodeType[] = [];
  update(data: Pick<GraphData, "allowedConnections"> & Partial<Pick<GraphData, "connectionTypes" | "nodeTypes">>, readOnly: boolean) {
    this.allowed = allowedKeys(data.allowedConnections);
    this.connectionTypes = data.connectionTypes ?? [];
    this.nodeTypes = data.nodeTypes ?? [];
    this.readOnly = readOnly;
  }
}

/** Every action that changes the diagram. A read-only Organization may do none of them. */
const EDITING = ["elements.move", "shape.move", "shape.create", "shape.append", "elements.create", "elements.delete", "connection.create", "connection.reconnect", "connection.start", "shape.resize"];

/** diagram-js rules for the Shadow graph: the Metamodel decides connections, a read-only Organization cannot edit, nodes keep their size. */
export class GraphRules extends RuleProvider {
  static $inject = ["eventBus", "graphContext", "elementRegistry"];

  constructor(eventBus: EventBus, private readonly context: GraphContext, private readonly registry: RegistryLike) {
    super(eventBus);
  }

  /** The types that may join two nodes, or why none may (see `connectionOptions`). A connection being re-routed is `ignore`d when looking for duplicates. */
  options(source: GraphElement, target: GraphElement, ignoreId?: string): ConnectionOptions {
    if (!isNodeElement(source) || !isNodeElement(target)) return { types: [], refusal: "not_allowed" };
    return connectionOptions({
      allowed: this.context.allowed,
      connectionTypeIds: this.context.connectionTypes.map((type) => type.id),
      source: { id: source.id, nodeTypeId: source.businessObject.node.node_type_id },
      target: { id: target.id, nodeTypeId: target.businessObject.node.node_type_id },
      existing: source.outgoing.filter(isConnectionElement).filter((item) => item.id !== ignoreId).map((item) => ({ connectionTypeId: item.businessObject.connection.connection_type_id, sourceId: item.source?.id ?? "", targetId: item.target?.id ?? "" })),
    });
  }

  /** The check behind `connection.create` and `connection.reconnect`; also usable directly to get the cause of a refusal. */
  checkConnection(connectionTypeId: string, source: GraphElement, target: GraphElement, ignoreId?: string): ConnectionCheck {
    if (!isNodeElement(source) || !isNodeElement(target)) return { allowed: false, cause: "not_allowed" };
    return checkConnection({
      allowed: this.context.allowed,
      connectionTypeId,
      source: { id: source.id, nodeTypeId: source.businessObject.node.node_type_id },
      target: { id: target.id, nodeTypeId: target.businessObject.node.node_type_id },
      existing: source.outgoing.filter(isConnectionElement).filter((item) => item.id !== ignoreId).map((item) => ({ connectionTypeId: item.businessObject.connection.connection_type_id, sourceId: item.source?.id ?? "", targetId: item.target?.id ?? "" })),
    });
  }

  init() {
    this.addRule(EDITING, 2000, () => (this.context.readOnly ? false : undefined));
    this.addRule("shape.resize", 1000, () => false);
    this.addRule(["connection.create", "connection.reconnect"], 1000, (context: { source?: GraphElement; target?: GraphElement; connection?: GraphElement }) => {
      const typeId = context.connection?.businessObject && isConnectionElement(context.connection) ? context.connection.businessObject.connection.connection_type_id : null;
      if (!context.source || !context.target) return false;
      // Without a type (the library's connect gesture, before the person has picked one) the nodes may be joined when any type may.
      if (!typeId) return this.options(context.source, context.target).types.length > 0;
      return this.checkConnection(typeId, context.source, context.target).allowed;
    });
  }
}
