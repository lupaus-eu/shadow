import BaseLayouter from "diagram-js/lib/layout/BaseLayouter.js";
import { getMid } from "diagram-js/lib/layout/LayoutUtil.js";

import type { GraphElement } from "./model";
import { parallelShift } from "./shapes";

type Point = { x: number; y: number };
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

  layoutConnection(connection: never, // eslint-disable-next-line @typescript-eslint/no-explicit-any
  hints?: { source?: any; target?: any; connectionStart?: any; connectionEnd?: any }) {
    const link = connection as unknown as GraphElement;
    const source = hints?.source ?? link.source;
    const target = hints?.target ?? link.target;
    // The library passes `false` for the end it did not move, and the moved end's new anchor; only a real point counts as a hint.
    const given = (hint: unknown): Point | undefined => (hint && typeof hint === "object" && Number.isFinite((hint as Point).x) && Number.isFinite((hint as Point).y) ? (hint as Point) : undefined);
    const startHint = given(hints?.connectionStart);
    const endHint = given(hints?.connectionEnd);
    let start = startHint ?? getMid(source);
    let end = endHint ?? getMid(target);
    // A connection being drawn by hand (an end that is not a node's centre) is left straight. A moved node's anchor is its new centre, so that is no reason to skip the sideways shift.
    const atCentre = (hint: Point | undefined, node: unknown) => !hint || (!!node && Math.hypot(hint.x - getMid(node as never).x, hint.y - getMid(node as never).y) < 1);
    if (atCentre(startHint, link.source) && atCentre(endHint, link.target) && link.source && link.target) {
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
