import BaseLayouter from "diagram-js/lib/layout/BaseLayouter.js";
import { getMid } from "diagram-js/lib/layout/LayoutUtil.js";

import type { GraphElement } from "./model";
import { parallelShift } from "./shapes";

type Docking = { getCroppedWaypoints(connection: unknown): { x: number; y: number }[] };

/** The key of a pair of nodes, the same for both directions. */
export const pairKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`);

/** Every connection between two nodes, in either direction, in a stable order (by id), so each keeps its own side. */
export function parallelConnections(source: GraphElement, target: GraphElement): GraphElement[] {
  const all = new Set<GraphElement>([...(source.incoming ?? []), ...(source.outgoing ?? []), ...(target.incoming ?? []), ...(target.outgoing ?? [])]);
  return [...all].filter((item) => (item.source === source && item.target === target) || (item.source === target && item.target === source)).sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

/**
 * A connection is a straight line from the middle of the source to the middle of the target, cropped where it meets each shape's border.
 * Connections between the same two nodes (either direction) are moved sideways in even steps so they stay apart and their labels do not
 * sit on each other; a single connection stays on the line between the centres.
 */
export class GraphLayouter extends BaseLayouter {
  static $inject = ["connectionDocking"];

  constructor(private readonly docking: Docking) {
    super();
  }

  layoutConnection(connection: never, hints?: { source?: never; target?: never; connectionStart?: never; connectionEnd?: never }) {
    const link = connection as unknown as GraphElement;
    const source = hints?.source ?? (link.source as never);
    const target = hints?.target ?? (link.target as never);
    let start = hints?.connectionStart ?? getMid(source);
    let end = hints?.connectionEnd ?? getMid(target);
    // A connection being drawn by hand (no hints about the pair, or an end that is not a node's centre) is left straight.
    if (!hints?.connectionStart && !hints?.connectionEnd && link.source && link.target) {
      const siblings = parallelConnections(link.source, link.target);
      const index = siblings.indexOf(link);
      if (siblings.length > 1 && index >= 0) {
        // The pair is always measured from the node with the smaller id, so a connection back lands on the other side.
        const forward = link.source.id < link.target.id;
        const a = forward ? start : end;
        const b = forward ? end : start;
        const shift = parallelShift(index, siblings.length, a, b);
        start = { x: start.x + shift.x, y: start.y + shift.y };
        end = { x: end.x + shift.x, y: end.y + shift.y };
      }
    }
    return this.docking.getCroppedWaypoints({ waypoints: [start, end], source, target });
  }
}
