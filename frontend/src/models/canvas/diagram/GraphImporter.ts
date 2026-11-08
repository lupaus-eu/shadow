import type Canvas from "diagram-js/lib/core/Canvas.js";
import type ElementFactory from "diagram-js/lib/core/ElementFactory.js";
import type EventBus from "diagram-js/lib/core/EventBus.js";

import type { ConnectionType, GraphConnection, GraphNode, NodeType } from "../../client";
import type { GraphData } from "../graph-types";
import type { GraphContext } from "./GraphRules";
import type { GraphModeling } from "./GraphModeling";
import { isConnectionElement, isNodeElement, type ChangeMark, type ConnectionObject, type GraphElement, type NodeObject, type RegistryLike } from "./model";
import { NODE_HEIGHT, NODE_WIDTH } from "./shapes";

type Layouter = { layoutConnection(connection: unknown): { x: number; y: number }[] };

export type ImportSummary = { added: number; updated: number; removed: number };

const sameNode = (a: GraphNode, b: GraphNode) => a.name === b.name && a.description === b.description && a.node_type_id === b.node_type_id && a.x === b.x && a.y === b.y;
const sameNodeType = (a: NodeType | undefined, b: NodeType | undefined) => a === b || (!!a && !!b && a.id === b.id && a.name === b.name && a.color === b.color && a.shape === b.shape);
const sameConnection = (a: GraphConnection, b: GraphConnection) => a.connection_type_id === b.connection_type_id && a.source_node_id === b.source_node_id && a.target_node_id === b.target_node_id;
const sameConnectionType = (a: ConnectionType | undefined, b: ConnectionType | undefined) =>
  a === b || (!!a && !!b && a.id === b.id && a.name === b.name && a.style === b.style && a.source_end === b.source_end && a.target_end === b.target_end);

/**
 * Turns plain graph data into shapes and connections and keeps the diagram equal to it. The diagram is never rebuilt: a load adds the
 * elements that are new, removes those that are gone and redraws only those whose data changed, so zoom, scroll and selection stay.
 * Optimistic elements (`pending`) are not in the data and disappear on the first load after their edit; a node with an unsent move keeps
 * its place until the move has been saved.
 */
export class GraphImporter {
  static $inject = ["canvas", "elementRegistry", "elementFactory", "eventBus", "layouter", "graphContext", "graphModeling"];

  constructor(
    private readonly canvas: Canvas,
    private readonly registry: RegistryLike,
    private readonly factory: ElementFactory,
    private readonly eventBus: EventBus,
    private readonly layouter: Layouter,
    private readonly context: GraphContext,
    private readonly modeling: GraphModeling,
  ) {}

  update(data: GraphData, readOnly = false): ImportSummary {
    this.context.update(data, readOnly);
    const nodeTypes = new Map(data.nodeTypes.map((type) => [type.id, type]));
    const connectionTypes = new Map(data.connectionTypes.map((type) => [type.id, type]));
    const marks = new Map<string, ChangeMark>();
    for (const id of data.markers.updated) marks.set(id, "updated");
    for (const id of data.markers.added) marks.set(id, "added");
    const nodeIds = new Set(data.nodes.map((node) => node.id));
    const connectionIds = new Set(data.connections.map((connection) => connection.id));
    const root = this.canvas.getRootElement();
    const elements = this.registry.filter((element) => !!element.parent);
    const summary: ImportSummary = { added: 0, updated: 0, removed: 0 };
    const changed = new Set<GraphElement>();
    const relayout = new Set<GraphElement>();

    // Gone: connections first (a shape that goes takes none with it here), then shapes.
    for (const element of elements.filter(isConnectionElement)) {
      if (connectionIds.has(element.id)) continue;
      this.detach(element);
      summary.removed++;
    }
    for (const element of elements.filter(isNodeElement)) {
      if (nodeIds.has(element.id) || element.businessObject.draft) continue;
      for (const connection of [...element.incoming, ...element.outgoing]) this.detach(connection);
      this.canvas.removeShape(element as never);
      summary.removed++;
    }

    for (const node of data.nodes) {
      const nodeType = nodeTypes.get(node.node_type_id);
      const change = marks.get(node.id) ?? null;
      const existing = this.registry.get(node.id);
      if (!existing) {
        const businessObject: NodeObject = { kind: "node", node, nodeType, change };
        const shape = this.factory.createShape({ id: node.id, x: node.x, y: node.y, width: NODE_WIDTH, height: NODE_HEIGHT, businessObject } as never) as unknown as GraphElement;
        this.canvas.addShape(shape as never, root);
        summary.added++;
        continue;
      }
      if (!isNodeElement(existing)) continue;
      const current = existing.businessObject;
      const moved = !this.modeling.hasUnsavedMove(node.id) && (existing.x !== node.x || existing.y !== node.y);
      const dataChanged = !sameNode(current.node, node) || !sameNodeType(current.nodeType, nodeType) || current.change !== change || current.pending;
      if (!moved && !dataChanged) continue;
      existing.businessObject = { kind: "node", node, nodeType, change };
      if (moved) {
        existing.x = node.x;
        existing.y = node.y;
        for (const connection of [...existing.incoming, ...existing.outgoing]) relayout.add(connection);
      }
      changed.add(existing);
      summary.updated++;
    }

    for (const connection of data.connections) {
      const connectionType = connectionTypes.get(connection.connection_type_id);
      const change = marks.get(connection.id) ?? null;
      const existing = this.registry.get(connection.id);
      if (!existing) {
        const source = this.registry.get(connection.source_node_id);
        const target = this.registry.get(connection.target_node_id);
        if (!source || !target) continue;
        const businessObject: ConnectionObject = { kind: "connection", connection, connectionType, change };
        const created = this.factory.createConnection({ id: connection.id, source, target, businessObject } as never) as unknown as GraphElement;
        created.waypoints = this.layouter.layoutConnection(created);
        this.canvas.addConnection(created as never, root);
        summary.added++;
        continue;
      }
      if (!isConnectionElement(existing)) continue;
      const current = existing.businessObject;
      if (sameConnection(current.connection, connection) && sameConnectionType(current.connectionType, connectionType) && current.change === change && !current.pending) continue;
      existing.businessObject = { kind: "connection", connection, connectionType, change };
      changed.add(existing);
      summary.updated++;
    }

    for (const connection of relayout) {
      if (!connection.source || !connection.target) continue;
      connection.waypoints = this.layouter.layoutConnection(connection);
      changed.add(connection);
    }
    if (changed.size > 0) this.eventBus.fire("elements.changed", { elements: [...changed] });
    this.applyMarkers(marks);
    return summary;
  }

  /** Removes a connection from the canvas and from its shapes' incoming and outgoing lists (the canvas alone leaves those behind). */
  private detach(connection: GraphElement) {
    this.canvas.removeConnection(connection as never);
    connection.source = undefined;
    connection.target = undefined;
  }

  /** The "added" and "updated" classes on the elements' groups, for CSS; the badge in the renderer is the part that does not depend on colour. */
  private applyMarkers(marks: Map<string, ChangeMark>) {
    for (const element of this.registry.filter((item) => !!item.parent)) {
      const mark = marks.get(element.id) ?? null;
      for (const name of ["added", "updated"] as const) {
        const marker = `shadow-${name}`;
        const has = this.canvas.hasMarker(element as never, marker);
        if (mark === name && !has) this.canvas.addMarker(element as never, marker);
        if (mark !== name && has) this.canvas.removeMarker(element as never, marker);
      }
    }
  }
}
