import type Canvas from "diagram-js/lib/core/Canvas.js";
import type EventBus from "diagram-js/lib/core/EventBus.js";

import { isConnectionElement, isNodeElement, type GraphElement, type RegistryLike } from "./model";
import {
  fitView, panView, pinchView, prefersReducedMotion, sameView, stepScale, tweenView, unionBounds, wheelFactor, zoomAround,
  type PinchStart, type Point, type Size, type View,
} from "../view";

type ZoomScrollLike = { _handleWheel: (event: WheelEvent) => void; _enabled: boolean };

/**
 * The one place that moves the view. Background drag (`moveCanvas`) and space + drag (`hand-tool`) come from the library; this service
 * adds what the library does not give: wheel and pinch zoom between 10 % and 400 % around the pointer (the library's own wheel zoom
 * stops at 20 % and scrolls on a plain wheel), touch pan and pinch, Fit with padding, 100 %, zoom steps, and animation that respects
 * `prefers-reduced-motion`. Every view change, from the mouse, the toolbar or a key, goes through `setView`, which clamps the zoom.
 */
export class GraphNavigation {
  static $inject = ["canvas", "eventBus", "zoomScroll", "elementRegistry"];

  private stop: (() => void) | null = null;
  /** Where the running animation ends. Steps and zooms started while it runs continue from here, so quick clicks add up. */
  private pending: View | null = null;
  private applying = false;
  /** Overridable in tests; true under `prefers-reduced-motion`. */
  reducedMotion: () => boolean = () => prefersReducedMotion();

  constructor(private readonly canvas: Canvas, eventBus: EventBus, zoomScroll: ZoomScrollLike, private readonly registry: RegistryLike) {
    // The library binds `_handleWheel` when the pointer enters the drawing; replacing it here, before that, is all it takes.
    zoomScroll._handleWheel = (event) => {
      if (!zoomScroll._enabled) return;
      event.preventDefault();
      const box = canvas.getContainer().getBoundingClientRect();
      this.zoomBy(wheelFactor(event.deltaY, event.deltaMode, event.ctrlKey || event.metaKey), { x: event.clientX - box.left, y: event.clientY - box.top });
    };
    // Any move of the view that is not ours (a drag, a wheel) ends an animation in progress.
    eventBus.on("canvas.viewbox.changing", () => { if (!this.applying) this.cancel(); });
    const unbindTouch = this.bindTouch(canvas.getContainer());
    const unbindGrab = this.bindGrab(canvas.getContainer());
    eventBus.on("diagram.destroy", () => { this.cancel(); unbindTouch(); unbindGrab(); });
  }

  private spaceHeld = false;

  /** Space is held: a press on the drawing pans instead of selecting or dragging. `GraphKeys` calls this from the keyboard service. */
  setSpaceHeld(held: boolean): void {
    this.spaceHeld = held;
    this.canvas.getContainer().style.cursor = held ? "grab" : "";
  }

  size(): Size { return this.canvas.getSize(); }

  /** The current view, read from the diagram (so it is right after a drag too). */
  getView(): View {
    const box = this.canvas.viewbox();
    return { x: box.x, y: box.y, scale: box.scale };
  }

  /** Shows `view`. The zoom is clamped; with `animate` the change eases unless the person prefers reduced motion. */
  setView(view: View, animate = false): void {
    const size = this.size();
    if (size.width <= 0 || size.height <= 0) return;
    this.cancel();
    const target = { ...view, scale: zoomAround(view, view.scale, { x: 0, y: 0 }).scale };
    const apply = (next: View) => {
      this.applying = true;
      try { this.canvas.viewbox({ x: next.x, y: next.y, width: size.width / next.scale, height: size.height / next.scale }); } finally { this.applying = false; }
    };
    const from = this.getView();
    if (!animate || sameView(from, target)) { apply(target); return; }
    this.pending = target;
    this.stop = tweenView(from, target, (next) => { if (next === target) this.pending = null; apply(next); }, { reduced: this.reducedMotion() });
  }

  /** Stops an animation where it is. */
  cancel(): void { this.stop?.(); this.stop = null; this.pending = null; }

  /** The view a relative change starts from: the end of a running animation, otherwise the view as it is. */
  private base(): View { return this.pending ?? this.getView(); }

  private centre(): Point { const { width, height } = this.size(); return { x: width / 2, y: height / 2 }; }

  /** Zooms by a factor around a point (default the centre of the drawing area). */
  zoomBy(factor: number, anchor: Point = this.centre(), animate = false): void {
    const view = this.getView();
    this.setView(zoomAround(view, view.scale * factor, anchor), animate);
  }

  /** One zoom step in or out around the centre. */
  zoomStep(direction: 1 | -1, animate = true): void {
    const view = this.base();
    this.setView(zoomAround(view, stepScale(view.scale, direction), this.centre()), animate);
  }

  /** The point of the canvas at the centre of what is in view (where a new node goes). */
  viewCentre(): Point {
    const box = this.canvas.viewbox();
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  }

  /** Scale 1 around the centre of the drawing area. */
  actualSize(animate = true): void { this.zoomTo(1, animate); }

  zoomTo(scale: number, animate = true): void {
    this.setView(zoomAround(this.base(), scale, this.centre()), animate);
  }

  /** The rectangle that holds every node (the connections run between nodes, so they are inside), or null when there are none. */
  graphBounds() {
    // Nodes hidden by the type panel are not part of what Fit shows.
    const nodes = this.registry.filter((element) => isNodeElement(element) && !this.canvas.hasMarker(element as never, "shadow-hidden"));
    return unionBounds(nodes.map((node: GraphElement) => ({ x: node.x, y: node.y, width: node.width, height: node.height })));
  }

  /** Shows the whole graph with padding (never past 100 %). */
  fit(animate = true): void {
    const target = fitView(this.graphBounds(), this.size());
    if (target) this.setView(target, animate);
  }

  /** Pans by screen pixels (positive moves the content right and down). */
  pan(dx: number, dy: number): void { this.setView(panView(this.base(), dx, dy)); }

  /** Centres the drawing area on a point of the canvas. */
  centreOn(point: Point, animate = true): void {
    const view = this.base();
    const { width, height } = this.size();
    this.setView({ scale: view.scale, x: point.x - width / (2 * view.scale), y: point.y - height / (2 * view.scale) }, animate);
  }

  /** Centres on a point and zooms in to at least `minScale` (a view that is already closer keeps its zoom). Eases unless reduced motion. */
  focus(point: Point, minScale = 1, animate = true): void {
    const view = this.base();
    const scale = Math.max(view.scale, minScale);
    const { width, height } = this.size();
    this.setView({ scale, x: point.x - width / (2 * scale), y: point.y - height / (2 * scale) }, animate);
  }

  /**
   * Space + drag: with Space held, pressing the primary button anywhere on the drawing (a node too) and moving pans. The library's hand
   * tool would pan on pointer movement alone and end at the first press, so `GraphKeys` keeps Space away from it.
   */
  private bindGrab(container: HTMLElement): () => void {
    let last: Point | null = null;
    const move = (event: MouseEvent) => {
      if (!last) return;
      this.pan(event.clientX - last.x, event.clientY - last.y);
      last = { x: event.clientX, y: event.clientY };
      event.preventDefault();
    };
    const end = () => {
      last = null;
      container.style.cursor = this.spaceHeld ? "grab" : "";
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", end);
    };
    const down = (event: MouseEvent) => {
      if (!this.spaceHeld || event.button !== 0) return;
      event.stopPropagation();
      event.preventDefault();
      this.cancel();
      last = { x: event.clientX, y: event.clientY };
      container.style.cursor = "grabbing";
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", end);
    };
    container.addEventListener("mousedown", down, true);
    return () => { container.removeEventListener("mousedown", down, true); end(); };
  }

  /**
   * Touch: one finger on the background pans, two fingers zoom and pan together. The library's own pan and zoom listen to the mouse
   * and the wheel only, and touches on shapes are left alone.
   */
  private bindTouch(container: HTMLElement): () => void {
    const pointers = new Map<number, Point>();
    let pinch: PinchStart | null = null;
    let last: Point | null = null;
    const local = (event: PointerEvent): Point => { const box = container.getBoundingClientRect(); return { x: event.clientX - box.left, y: event.clientY - box.top }; };
    const onShape = (target: EventTarget | null) => {
      const id = (target as Element | null)?.closest?.("[data-element-id]")?.getAttribute("data-element-id");
      const element = id ? this.registry.get(id) : undefined;
      return !!element && (isNodeElement(element) || isConnectionElement(element));
    };
    const measure = () => {
      const [a, b] = [...pointers.values()];
      return { mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, distance: Math.hypot(a.x - b.x, a.y - b.y) };
    };
    const down = (event: PointerEvent) => {
      if (event.pointerType !== "touch") return;
      if (pointers.size === 0 && onShape(event.target)) return;
      pointers.set(event.pointerId, local(event));
      this.cancel();
      if (pointers.size === 2) pinch = { view: this.getView(), ...measure() };
      last = pointers.size === 1 ? local(event) : null;
    };
    const move = (event: PointerEvent) => {
      if (!pointers.has(event.pointerId)) return;
      const point = local(event);
      pointers.set(event.pointerId, point);
      if (pointers.size >= 2 && pinch) {
        this.setView(pinchView(pinch, measure()));
      } else if (pointers.size === 1 && last) {
        this.pan(point.x - last.x, point.y - last.y);
        last = point;
      }
      event.preventDefault();
    };
    const up = (event: PointerEvent) => {
      if (!pointers.delete(event.pointerId)) return;
      pinch = null;
      // A finger left of a pinch carries on as a pan from where it is.
      last = pointers.size === 1 ? [...pointers.values()][0] : null;
    };
    container.addEventListener("pointerdown", down);
    container.addEventListener("pointermove", move);
    container.addEventListener("pointerup", up);
    container.addEventListener("pointercancel", up);
    return () => {
      container.removeEventListener("pointerdown", down);
      container.removeEventListener("pointermove", move);
      container.removeEventListener("pointerup", up);
      container.removeEventListener("pointercancel", up);
    };
  }
}
