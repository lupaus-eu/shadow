import type Canvas from "diagram-js/lib/core/Canvas.js";
import type ElementRegistry from "diagram-js/lib/core/ElementRegistry.js";
import type EventBus from "diagram-js/lib/core/EventBus.js";
import Minimap from "diagram-js-minimap";

import type { GraphNavigation } from "./diagram/GraphNavigation";
import { isNodeElement, type GraphElement } from "./diagram/model";

type MinimapClass = { new (config: object, injector: unknown, eventBus: EventBus, canvas: unknown, registry: ElementRegistry): MinimapInstance };
type MinimapInstance = {
  _parent: HTMLElement;
  _dirty: boolean;
  _createElement(element: GraphElement): unknown;
  _rebuild(): void;
  _update(): void;
  isOpen(): boolean;
  toggle(open?: boolean): void;
};
/** The minimap as the rest of the canvas sees it. */
export type GraphMinimap = { open(): void; close(): void; isOpen(): boolean; refresh(): void };

type Services = { get(name: string, strict?: boolean): unknown };

/**
 * Adds the `diagram-js-minimap` view to a running diagram. This file is the only one that imports the package, and `ShadowCanvas` loads
 * it with `import()`, so the minimap is a chunk of its own and not part of the page's first load. Three things are ours: the library's
 * `canvas.viewbox(box)` calls (a click or drag on the minimap) are turned into `GraphNavigation.setView`, so the view moves like every
 * other view change (zoom limits, remembered view); nodes of a hidden type and their connections are left out of the picture, as on the
 * canvas (`refresh` after the type filter changes); and the whole minimap is `aria-hidden`, a decorative picture (the node list is the
 * text alternative). The library's own toggle is hidden: the toolbar has the labelled button.
 */
export function attachMinimap(services: Services, open: boolean): GraphMinimap {
  const canvas = services.get("canvas") as Canvas;
  const navigation = services.get("graphNavigation") as GraphNavigation;
  const registry = services.get("elementRegistry") as ElementRegistry;
  const eventBus = services.get("eventBus") as EventBus;
  const hidden = (element: GraphElement) => !!canvas.hasMarker(element as never, "shadow-hidden");

  const routed = new Proxy(canvas, {
    get(target, property) {
      if (property === "viewbox") {
        return (box?: { x: number; y: number; width: number; height: number }) => {
          if (!box) return target.viewbox();
          const size = navigation.size();
          if (size.width > 0 && box.width > 0) navigation.setView({ x: box.x, y: box.y, scale: size.width / box.width });
          return undefined;
        };
      }
      const value = Reflect.get(target, property, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });

  // The package's default export is a diagram-js module declaration: `minimap: ["type", Minimap]`.
  const Constructor = (Minimap as unknown as { minimap: [string, MinimapClass] }).minimap[1];
  const minimap = new Constructor({ open, debounceDelay: 60 }, { get: (name: string, strict?: boolean) => services.get(name, strict) }, eventBus, routed, registry);
  const create = minimap._createElement.bind(minimap);
  minimap._createElement = (element: GraphElement) => {
    // A connection is hidden with the type of either end; `shadow-hidden` is on it already, and on a node of a hidden type.
    if ((isNodeElement(element) || element.waypoints) && hidden(element)) return undefined;
    return create(element);
  };
  minimap._parent.setAttribute("aria-hidden", "true");
  minimap._parent.dataset.testid = "canvas-minimap";
  // Elements were added before the minimap existed: the first opening builds the picture.
  minimap._dirty = true;
  if (minimap.isOpen()) { minimap._rebuild(); minimap._dirty = false; minimap._update(); }

  return {
    open: () => minimap.toggle(true),
    close: () => minimap.toggle(false),
    isOpen: () => !!minimap.isOpen(),
    refresh() {
      if (minimap.isOpen()) { minimap._rebuild(); minimap._update(); } else minimap._dirty = true;
    },
  };
}
