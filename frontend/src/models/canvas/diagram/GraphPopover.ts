import type Canvas from "diagram-js/lib/core/Canvas.js";
import type ElementRegistry from "diagram-js/lib/core/ElementRegistry.js";
import type EventBus from "diagram-js/lib/core/EventBus.js";
import type Overlays from "diagram-js/lib/features/overlays/Overlays.js";

import { placePopover, popoverWidth } from "../popover";
import { isNodeElement, type GraphElement } from "./model";

/** How long the pointer rests on a node before its popover opens (a keyboard focus opens it at once). */
export const POPOVER_DELAY_MS = 250;
const OVERLAY_TYPE = "shadow-popover";

type Shown = { elementId: string; overlayId: string; html: HTMLElement; via: "hover" | "focus"; scale: number };

let counter = 0;

/**
 * The hover popover of a node: its full name, type and description, in an `overlays` overlay beside the node. The overlay layer follows
 * pan and zoom with the drawing; the popover is placed on whichever side of the node has room (see `placePopover`) so it stays inside the
 * drawing area, and it is not scaled, so its text stays readable at any zoom. It opens after a short hover or at once on keyboard focus of a
 * node (the node then points to it with `aria-describedby`), and closes when the pointer leaves, focus leaves, Esc is pressed, the drawing
 * is panned, a drag starts or the node changes or goes. The node being named (draft) and the naming input never get one. The popover takes
 * no pointer events, so it never gets in the way of the drawing.
 */
export class GraphPopover {
  static $inject = ["eventBus", "canvas", "overlays", "elementRegistry"];

  private shown: Shown | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private dragging = false;

  constructor(
    private readonly eventBus: EventBus,
    private readonly canvas: Canvas,
    private readonly overlays: Overlays,
    private readonly registry: ElementRegistry,
  ) {
    const bus = eventBus as unknown as { on(event: string | string[], handler: (event: never) => unknown): void };
    bus.on("element.hover", ((event: { element: GraphElement }) => this.hover(event.element)) as never);
    bus.on("element.out", ((event: { element: GraphElement }) => this.leave(event.element)) as never);
    bus.on("element.dblclick", (() => this.hide()) as never);
    bus.on("drag.init", (() => { this.dragging = true; this.hide(); }) as never);
    bus.on("drag.cleanup", (() => { this.dragging = false; }) as never);
    // A change of the view: a pan closes the popover, a zoom keeps it and puts it again once the zoom has settled.
    bus.on("canvas.viewbox.changing", (() => { if (this.shown && this.canvas.viewbox().scale === this.shown.scale) this.hide(); }) as never);
    bus.on("canvas.viewbox.changed", (() => { const open = this.shown; if (open && this.canvas.viewbox().scale !== open.scale) this.refresh(); }) as never);
    bus.on("shape.remove", ((event: { element: GraphElement }) => { if (this.shown?.elementId === event.element.id) this.hide(); }) as never);
    bus.on("elements.changed", ((event: { elements: GraphElement[] }) => { if (this.shown && event.elements.some((element) => element.id === this.shown?.elementId)) this.refresh(); }) as never);
    bus.on("diagram.destroy", (() => { this.hide(); this.container.removeEventListener("focusin", this.onFocusIn); this.container.removeEventListener("focusout", this.onFocusOut); this.container.removeEventListener("keydown", this.onKeyDown); }) as never);
    this.container.addEventListener("focusin", this.onFocusIn);
    this.container.addEventListener("focusout", this.onFocusOut);
    this.container.addEventListener("keydown", this.onKeyDown);
  }

  private get container(): HTMLElement {
    return this.canvas.getContainer() as HTMLElement;
  }

  /** The id of the node whose popover is open (for tests). */
  get openFor(): string | null {
    return this.shown?.elementId ?? null;
  }

  private readonly onFocusIn = (event: FocusEvent) => {
    const element = this.nodeOf(event.target);
    if (element) this.show(element, "focus");
  };

  private readonly onFocusOut = (event: FocusEvent) => {
    if (this.shown?.via !== "focus") return;
    const next = this.nodeOf(event.relatedTarget);
    if (!next || next.id !== this.shown.elementId) this.hide();
  };

  private readonly onKeyDown = (event: KeyboardEvent) => {
    // Esc dismisses it (and still reaches the canvas keymap); F2 starts naming the node in place.
    if (event.key === "Escape" || event.key === "F2") this.hide();
  };

  private nodeOf(target: EventTarget | null): (GraphElement & { businessObject: { kind: "node" } }) | null {
    const id = (target as Element | null)?.closest?.("[data-element-id]")?.getAttribute("data-element-id");
    const element = id ? this.registry.get(id) : undefined;
    return isNodeElement(element) ? (element as never) : null;
  }

  private hover(element: GraphElement | undefined) {
    this.cancelTimer();
    if (!element || !isNodeElement(element)) { this.hide(); return; }
    if (this.shown?.elementId === element.id) return;
    this.timer = setTimeout(() => { this.timer = null; this.show(element, "hover"); }, POPOVER_DELAY_MS);
  }

  private leave(element: GraphElement | undefined) {
    this.cancelTimer();
    if (element && this.shown?.elementId === element.id) this.hide();
  }

  private cancelTimer() {
    if (this.timer !== null) { clearTimeout(this.timer); this.timer = null; }
  }

  /** Opens the popover of a node; a node that is hidden by the type filter, a draft or one with the naming input open gets none. */
  show(element: GraphElement, via: Shown["via"] = "hover") {
    if (this.dragging || !isNodeElement(element)) return;
    if (this.shown?.elementId === element.id) { this.shown.via = via; return; }
    this.hide();
    if (element.businessObject.draft || this.container.querySelector(".shadow-editor")) return;
    const gfx = this.canvas.getGraphics(element as never) as SVGElement | undefined;
    if (!gfx || gfx.classList.contains("shadow-hidden")) return;

    const { node, nodeType } = element.businessObject;
    const id = `shadow-popover-${++counter}`;
    const html = document.createElement("div");
    html.id = id;
    html.setAttribute("role", "tooltip");
    html.className = "shadow-popover";
    const name = document.createElement("strong");
    name.className = "shadow-popover-name";
    name.textContent = node.name;
    html.append(name);
    if (nodeType?.name) {
      const type = document.createElement("span");
      type.className = "shadow-popover-type";
      type.textContent = nodeType.name;
      html.append(type);
    }
    if (node.description) {
      const description = document.createElement("p");
      description.className = "shadow-popover-description";
      description.textContent = node.description;
      html.append(description);
    }

    const view = this.canvas.viewbox();
    const scale = view.scale || 1;
    const area = { width: view.outer?.width ?? this.container.clientWidth, height: view.outer?.height ?? this.container.clientHeight };
    html.style.maxWidth = `${popoverWidth(area.width)}px`;
    const size = this.measure(html);
    const box = { x: (element.x - view.x) * scale, y: (element.y - view.y) * scale, width: element.width * scale, height: element.height * scale };
    const place = placePopover(box, size, area);
    // The overlay's offsets are in canvas units from the node's corner; the overlay is not scaled, so a screen offset is divided by the zoom.
    const overlayId = this.overlays.add(element as never, OVERLAY_TYPE, { position: { left: (place.x - box.x) / scale, top: (place.y - box.y) / scale }, html, scale: false } as never);
    html.dataset.side = place.side;
    gfx.setAttribute("aria-describedby", id);
    this.shown = { elementId: element.id, overlayId, html, via, scale };
  }

  /** The size the popover takes, measured while it is in the drawing but not visible. */
  private measure(html: HTMLElement): { width: number; height: number } {
    html.style.visibility = "hidden";
    html.style.position = "absolute";
    html.style.left = "0";
    html.style.top = "0";
    this.container.append(html);
    const size = { width: html.offsetWidth, height: html.offsetHeight };
    html.remove();
    html.style.visibility = "";
    html.style.position = "";
    html.style.left = "";
    html.style.top = "";
    return size;
  }

  /** Puts the popover of the open node again (its data changed, or the zoom did). */
  private refresh() {
    const open = this.shown;
    if (!open) return;
    const element = this.registry.get(open.elementId) as GraphElement | undefined;
    this.hide();
    if (element) this.show(element, open.via);
  }

  hide() {
    this.cancelTimer();
    const open = this.shown;
    if (!open) return;
    this.shown = null;
    this.overlays.remove(open.overlayId);
    const element = this.registry.get(open.elementId);
    if (element) (this.canvas.getGraphics(element as never) as SVGElement | undefined)?.removeAttribute("aria-describedby");
  }
}
