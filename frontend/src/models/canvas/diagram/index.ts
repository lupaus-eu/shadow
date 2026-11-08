import ModelingModule from "diagram-js/lib/features/modeling/index.js";
import MoveCanvasModule from "diagram-js/lib/navigation/movecanvas/index.js";
import MoveModule from "diagram-js/lib/features/move/index.js";
import OutlineModule from "diagram-js/lib/features/outline/index.js";
import SelectionModule from "diagram-js/lib/features/selection/index.js";
import ZoomScrollModule from "diagram-js/lib/navigation/zoomscroll/index.js";
import CroppingConnectionDocking from "diagram-js/lib/layout/CroppingConnectionDocking.js";

import { GraphImporter } from "./GraphImporter";
import { GraphLayouter } from "./GraphLayouter";
import { GraphModeling } from "./GraphModeling";
import { GraphRenderer } from "./GraphRenderer";
import { GraphContext, GraphRules } from "./GraphRules";

/** Keeps a dragged node on the page instead of dropping it into the node under the pointer: nodes never contain other nodes. */
function GraphMoveTarget(this: unknown, eventBus: { on(event: string, priority: number, handler: (event: { context: { canExecute?: unknown; target?: unknown } }) => void): void }, canvas: { getRootElement(): unknown }) {
  eventBus.on("shape.move.move", 250, (event) => {
    if (event.context.canExecute) event.context.target = canvas.getRootElement();
  });
}
GraphMoveTarget.$inject = ["eventBus", "canvas"];

/**
 * The Shadow graph domain layer for diagram-js: how nodes and connections look (`graphRenderer`), where connections run (`layouter`,
 * `connectionDocking`), what is allowed (`graphRules`), how plain data becomes shapes (`graphImporter`) and how edits reach the server
 * (`graphModeling`). The library's own modules supply selection, move, canvas navigation, the command stack and the rules registry;
 * lasso, create, connect, context pad, palette, align, snapping, keyboard, overlays and the minimap join in the tickets that need them.
 */
export const shadowGraphModule = {
  __depends__: [ModelingModule, SelectionModule, MoveModule, OutlineModule, MoveCanvasModule, ZoomScrollModule],
  __init__: ["graphRenderer", "graphRules", "graphModeling", "graphMoveTarget"],
  graphContext: ["type", GraphContext],
  graphRenderer: ["type", GraphRenderer],
  graphRules: ["type", GraphRules],
  graphModeling: ["type", GraphModeling],
  graphImporter: ["type", GraphImporter],
  graphMoveTarget: ["type", GraphMoveTarget],
  layouter: ["type", GraphLayouter],
  connectionDocking: ["type", CroppingConnectionDocking],
};

export { EditRefused, MOVE_SAVE_DELAY_MS } from "./GraphModeling";
export type { GraphImporter, GraphModeling, GraphRules };
export { checkConnection, connectionKey, type ConnectionRefusal } from "./GraphRules";
