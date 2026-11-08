import AlignElementsModule from "diagram-js/lib/features/align-elements/index.js";
import ConnectModule from "diagram-js/lib/features/connect/index.js";
import ConnectionPreviewModule from "diagram-js/lib/features/connection-preview/index.js";
import ContextPadModule from "diagram-js/lib/features/context-pad/index.js";
import GridSnappingModule from "diagram-js/lib/features/grid-snapping/index.js";
import HandToolModule from "diagram-js/lib/features/hand-tool/index.js";
import KeyboardModule from "diagram-js/lib/features/keyboard/index.js";
import LassoToolModule from "diagram-js/lib/features/lasso-tool/index.js";
import ModelingModule from "diagram-js/lib/features/modeling/index.js";
import MoveCanvasModule from "diagram-js/lib/navigation/movecanvas/index.js";
import MoveModule from "diagram-js/lib/features/move/index.js";
import OutlineModule from "diagram-js/lib/features/outline/index.js";
import OverlaysModule from "diagram-js/lib/features/overlays/index.js";
import SelectionModule from "diagram-js/lib/features/selection/index.js";
import ZoomScrollModule from "diagram-js/lib/navigation/zoomscroll/index.js";
import CroppingConnectionDocking from "diagram-js/lib/layout/CroppingConnectionDocking.js";

import { GraphContextPad } from "./GraphContextPad";
import { GraphDrawing } from "./GraphDrawing";
import { GraphFilter } from "./GraphFilter";
import { GraphImporter } from "./GraphImporter";
import { GraphKeys } from "./GraphKeys";
import { GraphLayouter } from "./GraphLayouter";
import { GraphModeling } from "./GraphModeling";
import { GraphNavigation } from "./GraphNavigation";
import { GraphPopover } from "./GraphPopover";
import { GraphRenderer } from "./GraphRenderer";
import { GraphTools } from "./GraphTools";
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
 * (`graphModeling`), how the view moves (`graphNavigation`), which keys do what (`graphKeys`), what the type panel hides or dims (`graphFilter`), and the pointer drawing: connect, lasso, the context pad and naming in place (`graphDrawing`, `graphContextPad`), and the hover popover of a node (`graphPopover`). The library's own modules supply selection,
 * move, background drag and space + drag panning, the keyboard service, the command stack and the rules registry, and `align-elements`
 * and `grid-snapping`, which `graphTools` drives together with our own distribute and the automatic layout. Create, palette and editor
 * actions join in the tickets that need them; the minimap is added after load by `attachMinimap` (`../minimap.ts`) so its code is a chunk of its own.
 * A Diagram made from this module should be given `gridSnapping: { active: false }`: snapping is off until the person turns it on.
 */
export const shadowGraphModule = {
  __depends__: [ModelingModule, SelectionModule, MoveModule, OutlineModule, MoveCanvasModule, ZoomScrollModule, KeyboardModule, HandToolModule, ConnectModule, ConnectionPreviewModule, ContextPadModule, LassoToolModule, OverlaysModule, AlignElementsModule, GridSnappingModule],
  __init__: ["graphRenderer", "graphRules", "graphModeling", "graphMoveTarget", "graphNavigation", "graphDrawing", "graphContextPad", "graphKeys", "graphPopover", "graphTools"],
  graphContext: ["type", GraphContext],
  graphRenderer: ["type", GraphRenderer],
  graphRules: ["type", GraphRules],
  graphModeling: ["type", GraphModeling],
  graphImporter: ["type", GraphImporter],
  graphFilter: ["type", GraphFilter],
  graphMoveTarget: ["type", GraphMoveTarget],
  graphNavigation: ["type", GraphNavigation],
  graphDrawing: ["type", GraphDrawing],
  graphContextPad: ["type", GraphContextPad],
  graphKeys: ["type", GraphKeys],
  graphPopover: ["type", GraphPopover],
  graphTools: ["type", GraphTools],
  layouter: ["type", GraphLayouter],
  connectionDocking: ["type", CroppingConnectionDocking],
};

export type { GraphFilter };
export { EditRefused, MOVE_SAVE_DELAY_MS } from "./GraphModeling";
export type { GraphImporter, GraphModeling, GraphRules };
export { checkConnection, connectionKey, type ConnectionRefusal } from "./GraphRules";
