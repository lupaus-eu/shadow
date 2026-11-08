/** Where the hover popover of a node goes. Pure arithmetic in screen pixels, so it is easy to test; `GraphPopover` measures and applies it. */

export type Box = { x: number; y: number; width: number; height: number };
export type Size = { width: number; height: number };
export type Side = "right" | "left" | "below" | "above";
export type Placement = { /** Top-left corner of the popover, relative to the top-left corner of the drawing area. */ x: number; y: number; side: Side };

/** Gap between the node and the popover, and the least distance kept to the edge of the drawing area, in pixels. */
export const POPOVER_GAP = 8;
export const POPOVER_MARGIN = 6;
/** The widest the popover is drawn. */
export const POPOVER_MAX_WIDTH = 320;

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(value, high));

/** The width the popover may have inside an area of this width. */
export const popoverWidth = (areaWidth: number) => Math.max(0, Math.min(POPOVER_MAX_WIDTH, areaWidth - 2 * POPOVER_MARGIN));

/**
 * Puts a popover of `size` beside `target` (both relative to the drawing area of size `area`): to the right when it fits, else to the left,
 * below, above; when none fits whole, the side with the most room. It is then moved so that it lies inside the area with `POPOVER_MARGIN`
 * to spare (and starts at the margin when it is bigger than the area).
 */
export function placePopover(target: Box, size: Size, area: Size, gap = POPOVER_GAP, margin = POPOVER_MARGIN): Placement {
  const room = {
    right: area.width - margin - (target.x + target.width + gap),
    left: target.x - gap - margin,
    below: area.height - margin - (target.y + target.height + gap),
    above: target.y - gap - margin,
  };
  const need: Record<Side, number> = { right: size.width, left: size.width, below: size.height, above: size.height };
  const order: Side[] = ["right", "left", "below", "above"];
  const side = order.find((candidate) => room[candidate] >= need[candidate]) ?? order.reduce((best, candidate) => (room[candidate] - need[candidate] > room[best] - need[best] ? candidate : best));
  let x: number;
  let y: number;
  if (side === "right") { x = target.x + target.width + gap; y = target.y; }
  else if (side === "left") { x = target.x - gap - size.width; y = target.y; }
  else if (side === "below") { x = target.x; y = target.y + target.height + gap; }
  else { x = target.x; y = target.y - gap - size.height; }
  const maxX = area.width - margin - size.width;
  const maxY = area.height - margin - size.height;
  return { x: clamp(x, margin, Math.max(margin, maxX)), y: clamp(y, margin, Math.max(margin, maxY)), side };
}
