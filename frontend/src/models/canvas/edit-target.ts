import type { GraphMarkers } from "./graph-types";

/**
 * Which change the canvas shows and edits. The shown change is the edit target, whichever it is (an earlier one, a planned one, the last);
 * only the person's right to write the line and the subscription decide whether the canvas is writable.
 */
export function canvasWritable(input: { subscriptionWritable: boolean; canWriteLine: boolean }): boolean {
  return input.subscriptionWritable && input.canWriteLine;
}

/** The change the state is loaded for: the line's last change is the default and is found by the loader, so it is not asked for by id. */
export function sourceChangeId(changeIsLast: boolean, shown: { id: string } | null | undefined): string | null {
  return changeIsLast ? null : shown?.id ?? null;
}

/** The undo history belongs to one change: it is forgotten when the shown change changes to another (the first change of an empty line is no change). */
export function shouldClearHistory(previousChangeId: string | null, changeId: string | null): boolean {
  return !!previousChangeId && !!changeId && previousChangeId !== changeId;
}

/** The numbers of the legend: what the shown change added, changed or re-routed, and removed. */
export function markCounts(markers: GraphMarkers): { added: number; updated: number; removed: number; any: boolean } {
  const added = markers.added.length;
  const updated = markers.updated.length;
  const removed = markers.removed.length;
  return { added, updated, removed, any: added + updated + removed > 0 };
}
