import type { GraphMarkers } from "./graph-types";

/**
 * Which event the canvas shows and edits. The shown event is the edit target, whichever it is (an earlier one, a planned one, the last);
 * only the person's right to write the line and the subscription decide whether the canvas is writable.
 */
export function canvasWritable(input: { subscriptionWritable: boolean; canWriteLine: boolean }): boolean {
  return input.subscriptionWritable && input.canWriteLine;
}

/** The event the state is loaded for: the line's last event is the default and is found by the loader, so it is not asked for by id. */
export function sourceEventId(eventIsLast: boolean, shown: { id: string } | null | undefined): string | null {
  return eventIsLast ? null : shown?.id ?? null;
}

/** The undo history belongs to one event: it is forgotten when the shown event changes to another (the first event of an empty line is no change). */
export function shouldClearHistory(previousEventId: string | null, eventId: string | null): boolean {
  return !!previousEventId && !!eventId && previousEventId !== eventId;
}

/** The numbers of the legend: what the shown event added, changed or re-routed, and removed. */
export function markCounts(markers: GraphMarkers): { added: number; updated: number; removed: number; any: boolean } {
  const added = markers.added.length;
  const updated = markers.updated.length;
  const removed = markers.removed.length;
  return { added, updated, removed, any: added + updated + removed > 0 };
}
