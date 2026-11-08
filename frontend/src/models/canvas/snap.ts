/**
 * Grid snapping of the Structure canvas: the grid size, the rounding, and whether the person has it on. The choice is a per-person
 * preference kept in the browser only (`shadow.canvas.snap`); every read and write is guarded, so blocked or full storage gives the
 * default (off) and the canvas still works.
 */
type Store = Pick<Storage, "getItem" | "setItem">;
export type Place = { x: number; y: number };

/** Grid spacing in canvas units (the same as diagram-js's own `grid-snapping`). */
export const GRID_SPACING = 10;

const key = "shadow.canvas.snap";

function browserStore(): Store | null {
  try { return globalThis.localStorage ?? null; } catch { return null; }
}

/** The nearest grid line. */
export const snapValue = (value: number, spacing = GRID_SPACING): number => Math.round(value / spacing) * spacing;

/** The move that takes a node whose top left corner is at `origin` by (about) `delta` and ends on the grid: what a drag does with snapping on. */
export function snapDelta(origin: Place, delta: Place, spacing = GRID_SPACING): Place {
  return { x: snapValue(origin.x + delta.x, spacing) - origin.x, y: snapValue(origin.y + delta.y, spacing) - origin.y };
}

/** Whether snapping is on; anything missing, malformed or blocked is off. */
export function readSnap(store: Store | null = browserStore()): boolean {
  try { return JSON.parse(store?.getItem(key) ?? "null") === true; } catch { return false; }
}

/** Remembers the choice; a blocked or full storage is ignored. */
export function writeSnap(on: boolean, store: Store | null = browserStore()): void {
  try { store?.setItem(key, JSON.stringify(on)); } catch { /* ignore */ }
}
