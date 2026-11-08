import type EventBus from "diagram-js/lib/core/EventBus.js";
import type Keyboard from "diagram-js/lib/features/keyboard/Keyboard.js";
import type Modeling from "diagram-js/lib/features/modeling/Modeling.js";
import type Selection from "diagram-js/lib/features/selection/Selection.js";

import { Keymap, navigationBindings } from "../keymap";
import type { GraphContext } from "./GraphRules";
import type { GraphNavigation } from "./GraphNavigation";
import { isNodeElement, type GraphElement } from "./model";

const KEY_PRIORITY = 1100;
/** How far an arrow moves the selected nodes, in screen pixels at the current zoom (and five times that with Shift). */
const MOVE_STEP_PX = 10;

/**
 * Connects the Shadow keymap to the diagram-js `keyboard` service and registers the navigation keys. Later tickets add their keys with
 * `graphKeys.keymap.register(...)`. Space belongs to the hand tool, except on a focused node where it selects, like Enter.
 */
export class GraphKeys {
  static $inject = ["keyboard", "eventBus", "graphNavigation", "selection", "modeling", "graphContext"];

  readonly keymap = new Keymap();

  constructor(
    keyboard: Keyboard,
    eventBus: EventBus,
    private readonly navigation: GraphNavigation,
    private readonly selection: Selection,
    private readonly modeling: Modeling,
    private readonly context: GraphContext,
  ) {
    for (const binding of navigationBindings({
      zoomStep: (direction) => this.navigation.zoomStep(direction),
      actualSize: () => this.navigation.actualSize(),
      fit: () => this.navigation.fit(),
      pan: (dx, dy) => this.navigation.pan(dx, dy),
      moveSelection: (dx, dy, large) => this.moveSelection(dx, dy, large),
    })) this.keymap.register(binding);

    keyboard.addListener(KEY_PRIORITY, (context: { keyEvent: KeyboardEvent }) => (this.keymap.handle(context.keyEvent) ? true : undefined));
    // Space is "grab" for the drawing (space + drag pans, see GraphNavigation); the library's own hand tool must not also react to it.
    // On a focused node the space is a click for the keyboard instead (see ShadowCanvas), and does not grab.
    keyboard.addListener(2000, (context: { keyEvent: KeyboardEvent }) => {
      const event = context.keyEvent;
      if (event.key !== " " || event.ctrlKey || event.metaKey || event.altKey) return undefined;
      if ((event.target as Element | null)?.closest?.("[role='button'][data-element-id]")) return false;
      this.navigation.setSpaceHeld(true);
      return true;
    });
    keyboard.addListener(2000, (context: { keyEvent: KeyboardEvent }) => {
      if (context.keyEvent.key !== " ") return undefined;
      this.navigation.setSpaceHeld(false);
      return undefined;
    }, "keyboard.keyup");
    // Losing focus while Space is down would otherwise leave the drawing grabbing.
    eventBus.on("canvas.focus.changed", (event: { focused: boolean }) => { if (!event.focused) this.navigation.setSpaceHeld(false); });
  }

  private moveSelection(dx: number, dy: number, large: boolean): boolean {
    if (this.context.readOnly) return false;
    const nodes = (this.selection.get() as unknown as GraphElement[]).filter(isNodeElement);
    if (nodes.length === 0) return false;
    const scale = this.navigation.getView().scale;
    const step = Math.max(1, Math.round((MOVE_STEP_PX * (large ? 5 : 1)) / scale));
    this.modeling.moveElements(nodes as never, { x: dx * step, y: dy * step });
    return true;
  }
}
