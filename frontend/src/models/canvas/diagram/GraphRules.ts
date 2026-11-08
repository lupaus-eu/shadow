import type { AllowedConnection } from "../../client";
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
  existing: Iterable<{ connectionTypeId: string; sourceId: string; targetId: string }>;
}): ConnectionCheck {
  if (input.source.id === input.target.id) return { allowed: false, cause: "self" };
  if (!input.allowed.has(connectionKey(input.connectionTypeId, input.source.nodeTypeId, input.target.nodeTypeId))) return { allowed: false, cause: "not_allowed" };
  for (const item of input.existing) {
    if (item.connectionTypeId === input.connectionTypeId && item.sourceId === input.source.id && item.targetId === input.target.id) return { allowed: false, cause: "duplicate" };
  }
  return { allowed: true };
}

export const allowedKeys = (allowed: readonly AllowedConnection[]) => new Set(allowed.map((item) => connectionKey(item.connection_type_id, item.source_node_type_id, item.target_node_type_id)));

/** What the rules need to know about the graph and the person. Updated by the importer on every load. */
export class GraphContext {
  readOnly = false;
  allowed: ReadonlySet<string> = new Set();
  update(data: Pick<GraphData, "allowedConnections">, readOnly: boolean) {
    this.allowed = allowedKeys(data.allowedConnections);
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

  /** The check behind `connection.create` and `connection.reconnect`; also usable directly to get the cause of a refusal. */
  checkConnection(connectionTypeId: string, source: GraphElement, target: GraphElement): ConnectionCheck {
    if (!isNodeElement(source) || !isNodeElement(target)) return { allowed: false, cause: "not_allowed" };
    return checkConnection({
      allowed: this.context.allowed,
      connectionTypeId,
      source: { id: source.id, nodeTypeId: source.businessObject.node.node_type_id },
      target: { id: target.id, nodeTypeId: target.businessObject.node.node_type_id },
      existing: source.outgoing.filter(isConnectionElement).map((item) => ({ connectionTypeId: item.businessObject.connection.connection_type_id, sourceId: item.source?.id ?? "", targetId: item.target?.id ?? "" })),
    });
  }

  init() {
    this.addRule(EDITING, 2000, () => (this.context.readOnly ? false : undefined));
    this.addRule("shape.resize", 1000, () => false);
    this.addRule(["connection.create", "connection.reconnect"], 1000, (context: { source?: GraphElement; target?: GraphElement; connection?: GraphElement }) => {
      const typeId = context.connection?.businessObject && isConnectionElement(context.connection) ? context.connection.businessObject.connection.connection_type_id : null;
      if (!context.source || !context.target || !typeId) return false;
      return this.checkConnection(typeId, context.source, context.target).allowed;
    });
  }
}
