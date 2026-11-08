/**
 * The View of the Structure canvas: where the drawing is panned and how far it is zoomed. Everything here is plain arithmetic and
 * state, with no diagram-js and no DOM, so the limits and the "keep or reset" rules can be tested alone. `GraphNavigation` applies
 * the results to the diagram; `useCanvasView` keeps them for as long as the same line is open.
 */

/** Zoom limits: 10 % to 400 %. */
export const MIN_ZOOM = 0.1;
export const MAX_ZOOM = 4;
/** One toolbar or keyboard zoom step. */
export const ZOOM_STEP = 1.25;
/** Space kept free around the graph by Fit, in screen pixels. */
export const FIT_PADDING = 48;
/** How long Fit, 100 % and the zoom steps animate when motion is allowed. */
export const VIEW_ANIMATION_MS = 160;

/** `x` and `y` are the canvas coordinates at the top left corner of the drawing area; `scale` 1 is 100 %. */
export type View = { x: number; y: number; scale: number };
export type Size = { width: number; height: number };
export type Bounds = { x: number; y: number; width: number; height: number };
export type Point = { x: number; y: number };

export const clampZoom = (scale: number): number => (Number.isFinite(scale) ? Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, scale)) : 1);

/** The number the toolbar shows. */
export const zoomPercent = (scale: number): number => Math.round(scale * 100);

export const sameView = (a: View, b: View, tolerance = 0.001): boolean =>
  Math.abs(a.scale - b.scale) < tolerance && Math.abs(a.x - b.x) < tolerance * 10 && Math.abs(a.y - b.y) < tolerance * 10;

/** The scale one zoom step away, within the limits. */
export const stepScale = (scale: number, direction: 1 | -1): number => clampZoom(direction > 0 ? scale * ZOOM_STEP : scale / ZOOM_STEP);

/** Zooms to `scale` (clamped) keeping the canvas point under `anchor` (pixels from the top left of the drawing area) where it is. */
export function zoomAround(view: View, scale: number, anchor: Point): View {
  const next = clampZoom(scale);
  return { scale: next, x: view.x + anchor.x / view.scale - anchor.x / next, y: view.y + anchor.y / view.scale - anchor.y / next };
}

/** Moves the drawing by `dx`, `dy` screen pixels (positive moves the content right and down). */
export const panView = (view: View, dx: number, dy: number): View => ({ ...view, x: view.x - dx / view.scale, y: view.y - dy / view.scale });

/** The zoom factor of one wheel event: smooth and capped, whatever the unit the device reports (pixels, lines or pages). A pinch arrives as a wheel with ctrl held and is more sensitive. */
export function wheelFactor(deltaY: number, deltaMode: number, pinch: boolean): number {
  const unit = deltaMode === 1 ? 16 : deltaMode === 2 ? 100 : 1;
  const delta = Math.max(-240, Math.min(240, deltaY * unit));
  return Math.exp(-delta * (pinch ? 0.01 : 0.0015));
}

/**
 * The view that shows `bounds` (the whole graph) with `padding` around it. It never zooms in past 100 % (a single node does not
 * fill the screen) and never out past the limit. No bounds (an empty graph) gives 100 % at the origin; no size yet gives null.
 */
export function fitView(bounds: Bounds | null, size: Size, padding = FIT_PADDING, maxScale = 1): View | null {
  if (size.width <= 0 || size.height <= 0) return null;
  if (!bounds) return { x: 0, y: 0, scale: 1 };
  const scale = clampZoom(Math.min(maxScale, Math.max(1, size.width - 2 * padding) / Math.max(1, bounds.width), Math.max(1, size.height - 2 * padding) / Math.max(1, bounds.height)));
  return { scale, x: bounds.x + bounds.width / 2 - size.width / (2 * scale), y: bounds.y + bounds.height / 2 - size.height / (2 * scale) };
}

/** The union of rectangles, or null when there are none. */
export function unionBounds(rectangles: Iterable<Bounds>): Bounds | null {
  let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
  for (const rectangle of rectangles) {
    left = Math.min(left, rectangle.x);
    top = Math.min(top, rectangle.y);
    right = Math.max(right, rectangle.x + rectangle.width);
    bottom = Math.max(bottom, rectangle.y + rectangle.height);
  }
  return left === Infinity ? null : { x: left, y: top, width: right - left, height: bottom - top };
}

/** A two-finger gesture at its start: the view then, the midpoint of the fingers and the distance between them. */
export type PinchStart = { view: View; mid: Point; distance: number };

/** The view while two fingers move: zoom by the change of distance, and keep the canvas point that was under the starting midpoint under the current one (so the fingers also pan). */
export function pinchView(start: PinchStart, now: { mid: Point; distance: number }): View {
  const scale = clampZoom(start.view.scale * (start.distance > 0 ? now.distance / start.distance : 1));
  const cx = start.view.x + start.mid.x / start.view.scale;
  const cy = start.view.y + start.mid.y / start.view.scale;
  return { scale, x: cx - now.mid.x / scale, y: cy - now.mid.y / scale };
}

/** True when the person asked the system for less motion. */
export function prefersReducedMotion(match: ((query: string) => { matches: boolean }) | undefined = typeof globalThis.matchMedia === "function" ? globalThis.matchMedia.bind(globalThis) : undefined): boolean {
  try { return match?.("(prefers-reduced-motion: reduce)").matches === true; } catch { return false; }
}

type Clock = { now(): number; request(callback: (time: number) => void): number; cancel(handle: number): void };
const browserClock = (): Clock => ({ now: () => performance.now(), request: (callback) => requestAnimationFrame(callback), cancel: (handle) => cancelAnimationFrame(handle) });

/**
 * Moves from one view to another. With reduced motion (or a zero duration) it jumps to the end at once and never schedules a frame;
 * otherwise it eases over `duration` ms. Returns a function that stops the animation where it is.
 */
export function tweenView(from: View, to: View, apply: (view: View) => void, options: { reduced?: boolean; duration?: number; clock?: Clock } = {}): () => void {
  const duration = options.duration ?? VIEW_ANIMATION_MS;
  if ((options.reduced ?? prefersReducedMotion()) || duration <= 0) { apply(to); return () => undefined; }
  const clock = options.clock ?? browserClock();
  const start = clock.now();
  let handle = 0;
  let stopped = false;
  const frame = () => {
    if (stopped) return;
    const progress = Math.min(1, (clock.now() - start) / duration);
    const eased = 1 - (1 - progress) ** 3;
    if (progress >= 1) { apply(to); return; }
    apply({ scale: from.scale * (to.scale / from.scale) ** eased, x: from.x + (to.x - from.x) * eased, y: from.y + (to.y - from.y) * eased });
    handle = clock.request(frame);
  };
  handle = clock.request(frame);
  return () => { stopped = true; clock.cancel(handle); };
}

/**
 * What one open line remembers of its view: the last view and whether the automatic fit has happened. A memory belongs to one key
 * (organization, model and line); a different key, or leaving the Structure tab, means a new memory, which is how the view resets.
 */
export class ViewMemory {
  private current: View | null = null;
  private done = false;

  constructor(readonly key: string) {}

  /** The last view to come back to (after a remount of the canvas), or null. */
  get view(): View | null { return this.current ? { ...this.current } : null; }
  /** True once the line's first load has been fitted. */
  get fitted(): boolean { return this.done; }

  remember(view: View): void { this.current = { x: view.x, y: view.y, scale: clampZoom(view.scale) }; }
  markFitted(): void { this.done = true; }
}
