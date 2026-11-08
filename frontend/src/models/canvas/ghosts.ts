import { append, attr, classes, clear, create } from "tiny-svg";

import type { ConnectionType, GraphConnection, GraphNode, NodeType } from "../client";
import type { GraphData } from "./graph-types";
import { NODE_HEIGHT, NODE_WIDTH, shortenName } from "./diagram/shapes";

/**
 * Elements the shown change removed. They are not on the canvas as shapes: they are outlines in a layer of their own, so they cannot be
 * selected, moved, connected or deleted, only looked at. The "-" badge and the dashed outline are the marks (not colour alone), and each
 * ghost has a `<title>` for assistive technology; `ghostSummary` lists the same elements as text.
 */
export type GhostSummary = { nodes: string[]; connections: string[] };

export function ghostSummary(data: GraphData): GhostSummary {
  const ghosts = data.ghosts;
  if (!ghosts) return { nodes: [], connections: [] };
  const names = new Map([...data.nodes, ...ghosts.nodes].map((node) => [node.id, node.name]));
  const types = new Map(data.connectionTypes.map((type) => [type.id, type.name]));
  return {
    nodes: ghosts.nodes.map((node) => node.name),
    connections: ghosts.connections.map((connection) => `${names.get(connection.source_node_id) ?? "?"} → ${names.get(connection.target_node_id) ?? "?"} (${types.get(connection.connection_type_id) ?? "?"})`),
  };
}

const centre = (node: GraphNode) => ({ x: node.x + NODE_WIDTH / 2, y: node.y + NODE_HEIGHT / 2 });

function badge(parent: SVGElement, x: number, y: number) {
  const group = create("g");
  classes(group).add("shadow-change-badge");
  attr(group, { "data-change": "removed", transform: `translate(${x} ${y})` });
  const disc = create("circle");
  attr(disc, { r: 9 });
  append(group, disc);
  const glyph = create("text");
  attr(glyph, { y: 4, "text-anchor": "middle", "font-size": 13, "font-weight": 700 });
  glyph.textContent = "−";
  append(group, glyph);
  append(parent, group);
}

function drawNode(layer: SVGElement, node: GraphNode, type: NodeType | undefined) {
  const group = create("g");
  classes(group).add("shadow-ghost");
  attr(group, { "data-ghost": "node", "data-ghost-id": node.id, "pointer-events": "none" });
  const title = create("title");
  title.textContent = `${node.name}${type ? ` (${type.name})` : ""}`;
  append(group, title);
  const body = create("rect");
  attr(body, { x: node.x, y: node.y, width: NODE_WIDTH, height: NODE_HEIGHT, rx: 8, ry: 8 });
  classes(body).add("shadow-ghost-body");
  append(group, body);
  const label = create("text");
  attr(label, { x: node.x + NODE_WIDTH / 2, y: node.y + NODE_HEIGHT / 2 + 4, "text-anchor": "middle", "font-size": 12 });
  classes(label).add("shadow-ghost-label");
  label.textContent = shortenName(node.name);
  append(group, label);
  badge(group, node.x + NODE_WIDTH - 4, node.y + 4);
  append(layer, group);
}

function drawConnection(layer: SVGElement, connection: GraphConnection, ends: Map<string, GraphNode>, type: ConnectionType | undefined) {
  const source = ends.get(connection.source_node_id);
  const target = ends.get(connection.target_node_id);
  if (!source || !target) return;
  const from = centre(source);
  const to = centre(target);
  const group = create("g");
  classes(group).add("shadow-ghost");
  attr(group, { "data-ghost": "connection", "data-ghost-id": connection.id, "pointer-events": "none" });
  const line = create("line");
  attr(line, { x1: from.x, y1: from.y, x2: to.x, y2: to.y });
  classes(line).add("shadow-ghost-line");
  append(group, line);
  const label = create("text");
  attr(label, { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 - 6, "text-anchor": "middle", "font-size": 11 });
  classes(label).add("shadow-ghost-label");
  label.textContent = `− ${shortenName(type?.name ?? "")}`.trim();
  append(group, label);
  append(layer, group);
}

/** Redraws the ghost layer from the data: one outline per removed node, one dashed line per removed connection whose ends are known. */
export function drawGhosts(layer: SVGElement, data: GraphData) {
  clear(layer);
  const ghosts = data.ghosts;
  if (!ghosts) return;
  const types = new Map(data.nodeTypes.map((type) => [type.id, type]));
  const connectionTypes = new Map(data.connectionTypes.map((type) => [type.id, type]));
  const ends = new Map([...data.nodes, ...ghosts.nodes].map((node) => [node.id, node]));
  for (const connection of ghosts.connections) drawConnection(layer, connection, ends, connectionTypes.get(connection.connection_type_id));
  for (const node of ghosts.nodes) drawNode(layer, node, types.get(node.node_type_id));
}
