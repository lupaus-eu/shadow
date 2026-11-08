import BaseLayouter from "diagram-js/lib/layout/BaseLayouter.js";
import { getMid } from "diagram-js/lib/layout/LayoutUtil.js";

type Docking = { getCroppedWaypoints(connection: unknown): { x: number; y: number }[] };

/** A connection is a straight line from the middle of the source to the middle of the target, cropped where it meets each shape's border. */
export class GraphLayouter extends BaseLayouter {
  static $inject = ["connectionDocking"];

  constructor(private readonly docking: Docking) {
    super();
  }

  layoutConnection(connection: never, hints?: { source?: never; target?: never; connectionStart?: never; connectionEnd?: never }) {
    const link = connection as { source: never; target: never };
    const source = hints?.source ?? link.source;
    const target = hints?.target ?? link.target;
    const waypoints = [hints?.connectionStart ?? getMid(source), hints?.connectionEnd ?? getMid(target)];
    return this.docking.getCroppedWaypoints({ waypoints, source, target });
  }
}
