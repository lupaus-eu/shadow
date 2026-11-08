import type { GraphData } from "./graph-types";

/**
 * The text alternative of the canvas and its live region. Pure helpers: the page (`ModelCanvas`) supplies the texts and the state, and the
 * type list (`TypePanel`) is the focusable list of every node that reads them out.
 */

/** The same sentence said twice in a row is not announced again by a polite live region unless its text changes, so a trailing no-break space alternates. */
export function nextAnnouncement(previous: string, message: string): string {
  if (message === "") return "";
  return previous === message ? `${message} ` : message;
}

export type ConnectionTexts = { connOut(type: string, other: string): string; connIn(type: string, other: string): string };

/** One row per connection touching a node, saying its direction, type and the node at the other end, e.g. "outgoing Reports to: Support". */
export function nodeConnectionRows(graph: GraphData, nodeId: string, texts: ConnectionTexts): { id: string; label: string }[] {
  const names = new Map(graph.nodes.map((node) => [node.id, node.name]));
  const typeNames = new Map(graph.connectionTypes.map((type) => [type.id, type.name]));
  const rows: { id: string; label: string }[] = [];
  for (const connection of graph.connections) {
    const type = typeNames.get(connection.connection_type_id) ?? "?";
    if (connection.source_node_id === nodeId) rows.push({ id: connection.id, label: texts.connOut(type, names.get(connection.target_node_id) ?? "?") });
    if (connection.target_node_id === nodeId) rows.push({ id: connection.id, label: texts.connIn(type, names.get(connection.source_node_id) ?? "?") });
  }
  return rows;
}

export type SelectionTexts = {
  announceNode(name: string, type: string): string;
  announceConnection(type: string, from: string, to: string): string;
  announceMany(count: number): string;
};

/** What a change of selection says aloud; an empty selection says nothing. */
export function selectionAnnouncement(graph: GraphData, ids: readonly string[], texts: SelectionTexts): string {
  if (ids.length === 0) return "";
  if (ids.length > 1) return texts.announceMany(ids.length);
  const node = graph.nodes.find((item) => item.id === ids[0]);
  if (node) return texts.announceNode(node.name, graph.nodeTypes.find((type) => type.id === node.node_type_id)?.name ?? "");
  const connection = graph.connections.find((item) => item.id === ids[0]);
  if (!connection) return "";
  const name = (id: string) => graph.nodes.find((item) => item.id === id)?.name ?? "?";
  return texts.announceConnection(graph.connectionTypes.find((type) => type.id === connection.connection_type_id)?.name ?? "?", name(connection.source_node_id), name(connection.target_node_id));
}
