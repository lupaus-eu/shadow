import type { Bounds } from "./view";

/**
 * Distribute: the arithmetic of "equal gaps", on plain boxes. The library's `distribute-elements` is not used because it counts a
 * 5 unit margin inside every box when it measures the space and it groups boxes whose ranges overlap, so with four or more nodes the gaps
 * come out a few units unequal (verified in tests/canvas/tools.test.ts). Here every node is its own step: the nodes are put in order along
 * the axis, the first and the last stay where they are, and the free space between them is shared in equal gaps.
 */
export type Box = Bounds & { id: string };
export type Axis = "horizontal" | "vertical";

/**
 * The new top left corner of every box, or null when there is nothing to do: fewer than three boxes, or no free space between the outer
 * two (they overlap or touch with the others in between), where equal gaps would pile the nodes up. Gaps are whole units: the cumulative
 * position is rounded, so no gap differs from another by more than one unit.
 */
export function distributePlaces(boxes: readonly Box[], axis: Axis): Map<string, { x: number; y: number }> | null {
  if (boxes.length < 3) return null;
  const start = (box: Box) => (axis === "horizontal" ? box.x : box.y);
  const size = (box: Box) => (axis === "horizontal" ? box.width : box.height);
  const sorted = [...boxes].sort((a, b) => start(a) - start(b) || a.id.localeCompare(b.id));
  const first = sorted[0], last = sorted[sorted.length - 1];
  const middle = sorted.slice(1, -1);
  const free = start(last) - (start(first) + size(first)) - middle.reduce((total, box) => total + size(box), 0);
  if (free <= 0) return null;
  const gap = free / (sorted.length - 1);
  const places = new Map<string, { x: number; y: number }>();
  let cursor = start(first) + size(first);
  for (const box of sorted) {
    if (box !== first && box !== last) {
      cursor += gap;
      const at = Math.round(cursor);
      places.set(box.id, axis === "horizontal" ? { x: at, y: box.y } : { x: box.x, y: at });
      cursor += size(box);
    }
  }
  return places;
}
