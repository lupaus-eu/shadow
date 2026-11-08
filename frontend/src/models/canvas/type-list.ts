import type { GraphNode, NodeType } from "../client";
import type { GraphData } from "./graph-types";

/** One node type of the left panel with its nodes, sorted by name. A type without nodes is still a group (it keeps its "+"). */
export type TypeGroup = { type: NodeType; nodes: GraphNode[] };

/** What the drawing shows of the panel's choices: the types whose nodes are hidden, and (while a search is active) the ids that match. */
export type CanvasFilter = { hiddenTypeIds: ReadonlySet<string>; matchIds: ReadonlySet<string> | null };
export const noFilter: CanvasFilter = { hiddenTypeIds: new Set(), matchIds: null };

const collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });
const byName = (a: { name: string; id: string }, b: { name: string; id: string }) => collator.compare(a.name, b.name) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);

/** Groups nodes by their type, types sorted by name and nodes by name (then id, so the order is stable). Nodes of an unknown type are left out. */
export function groupNodes(graph: Pick<GraphData, "nodes" | "nodeTypes">): TypeGroup[] {
  const groups = new Map<string, TypeGroup>(graph.nodeTypes.map((type) => [type.id, { type, nodes: [] }]));
  for (const node of graph.nodes) groups.get(node.node_type_id)?.nodes.push(node);
  return [...groups.values()].map((group) => ({ type: group.type, nodes: group.nodes.sort(byName) })).sort((a, b) => byName(a.type, b.type));
}

/** The types the panel offers as visible: every type, minus the hidden ones. */
export const visibleTypeCount = (groups: TypeGroup[], hidden: ReadonlySet<string>): number => groups.filter((group) => !hidden.has(group.type.id)).length;

/** A type id set after one checkbox change. */
export function toggleType(hidden: ReadonlySet<string>, typeId: string): Set<string> {
  const next = new Set(hidden);
  if (!next.delete(typeId)) next.add(typeId);
  return next;
}

/** Select all shows every type, Deselect all hides every type. */
export const showAllTypes = (): Set<string> => new Set();
export const hideAllTypes = (groups: TypeGroup[]): Set<string> => new Set(groups.map((group) => group.type.id));

/** True when a node is drawn: its type is not hidden. */
export const isNodeVisible = (node: Pick<GraphNode, "node_type_id">, hidden: ReadonlySet<string>): boolean => !hidden.has(node.node_type_id);

/** A search term compared case-insensitively on trimmed text; empty means no search. */
export const normaliseQuery = (query: string): string => query.trim().toLocaleLowerCase();

/** The nodes whose name contains the query, in panel order (type, then name). Nodes of hidden types never match. Null when there is no query. */
export function searchMatches(groups: TypeGroup[], query: string, hidden: ReadonlySet<string>): GraphNode[] | null {
  const wanted = normaliseQuery(query);
  if (!wanted) return null;
  return groups.filter((group) => !hidden.has(group.type.id)).flatMap((group) => group.nodes.filter((node) => node.name.toLocaleLowerCase().includes(wanted)));
}

/** Where a new node goes until drawing it by hand arrives: a grid of 8 columns, indexed by how many nodes there already are. */
export function nextPlacement(count: number): { x: number; y: number } {
  return { x: 30 + (count % 8) * 170, y: 30 + (Math.floor(count / 8) % 14) * 60 };
}

/** Whether a group is open: a search opens the groups that hold a match; otherwise the person's choice, and a type without nodes starts closed. */
export function isGroupOpen(group: TypeGroup, collapse: Readonly<Record<string, boolean>>, matches: ReadonlySet<string> | null): boolean {
  if (matches) return group.nodes.some((node) => matches.has(node.id));
  return !(collapse[group.type.id] ?? group.nodes.length === 0);
}
