import type { ElkNode } from "elkjs/lib/elk-api";

import type { Bounds, Point } from "./view";

/**
 * Automatic layout of the Structure canvas: the plain mapping from the drawn graph to the input of `elkjs` and from its answer to node
 * positions, and `computeLayout`, which loads `elkjs` (the layered algorithm) only when called, as a chunk of its own. Nothing here knows
 * diagram-js; `GraphTools` reads the drawn nodes, calls this and applies the result as one move.
 */
export type LayoutNode = { id: string; width: number; height: number };
export type LayoutEdge = { id: string; source: string; target: string };

/** Space between nodes of a layer, and between layers (canvas units). Wide enough for a connection label between two layers. */
export const NODE_SPACING = 40;
export const LAYER_SPACING = 90;
export const COMPONENT_SPACING = 60;

export const LAYOUT_OPTIONS: Record<string, string> = {
  "elk.algorithm": "layered",
  "elk.direction": "RIGHT",
  "elk.spacing.nodeNode": String(NODE_SPACING),
  "elk.layered.spacing.nodeNodeBetweenLayers": String(LAYER_SPACING),
  "elk.spacing.componentComponent": String(COMPONENT_SPACING),
  "elk.separateConnectedComponents": "true",
  "elk.padding": "[top=0,left=0,bottom=0,right=0]",
};

/** The input graph of the layout. Connections to a node that is not in the list, and connections from a node to itself, are left out (they cannot affect the placement). */
export function toElkGraph(nodes: readonly LayoutNode[], edges: readonly LayoutEdge[]): ElkNode {
  const ids = new Set(nodes.map((node) => node.id));
  return {
    id: "root",
    layoutOptions: { ...LAYOUT_OPTIONS },
    children: nodes.map((node) => ({ id: node.id, width: node.width, height: node.height })),
    edges: edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target) && edge.source !== edge.target).map((edge) => ({ id: edge.id, sources: [edge.source], targets: [edge.target] })),
  };
}

/** The top left corner of each laid-out node, in whole units, relative to the layout's own origin. */
export function fromElkGraph(result: ElkNode): Map<string, Point> {
  const positions = new Map<string, Point>();
  for (const child of result.children ?? []) positions.set(child.id, { x: Math.round(child.x ?? 0), y: Math.round(child.y ?? 0) });
  return positions;
}

/** Moves the layout so its top left corner is at `anchor` (the corner of where the graph is now), so the graph does not jump away from where the person was working. */
export function placeLayout(positions: ReadonlyMap<string, Point>, anchor: Point): Map<string, Point> {
  let left = Infinity, top = Infinity;
  for (const at of positions.values()) { left = Math.min(left, at.x); top = Math.min(top, at.y); }
  const placed = new Map<string, Point>();
  if (left === Infinity) return placed;
  for (const [id, at] of positions) placed.set(id, { x: Math.round(anchor.x + at.x - left), y: Math.round(anchor.y + at.y - top) });
  return placed;
}

/** True when no two boxes overlap (touching edges do not count). */
export function hasNoOverlap(boxes: readonly Bounds[]): boolean {
  for (let a = 0; a < boxes.length; a++) {
    for (let b = a + 1; b < boxes.length; b++) {
      const p = boxes[a], q = boxes[b];
      if (p.x < q.x + q.width && q.x < p.x + p.width && p.y < q.y + q.height && q.y < p.y + p.height) return false;
    }
  }
  return true;
}

/** Lays the graph out with `elkjs` (loaded now, as its own chunk) and returns the top left corner of every node, relative to the layout's origin. */
export async function computeLayout(nodes: readonly LayoutNode[], edges: readonly LayoutEdge[]): Promise<Map<string, Point>> {
  if (nodes.length === 0) return new Map();
  const { default: ELK } = await import("elkjs/lib/elk.bundled.js");
  const elk = new ELK();
  return fromElkGraph(await elk.layout(toElkGraph(nodes, edges)));
}
