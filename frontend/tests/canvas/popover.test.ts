import { describe, expect, it } from "vitest";

import { POPOVER_GAP, POPOVER_MARGIN, placePopover, popoverWidth } from "../../src/models/canvas/popover.ts";

const area = { width: 800, height: 600 };
const size = { width: 200, height: 80 };
const inside = (place: { x: number; y: number }) => place.x >= POPOVER_MARGIN && place.y >= POPOVER_MARGIN && place.x + size.width <= area.width - POPOVER_MARGIN && place.y + size.height <= area.height - POPOVER_MARGIN;

describe("placePopover", () => {
  it("goes to the right of a node when there is room, level with its top", () => {
    const place = placePopover({ x: 100, y: 100, width: 160, height: 56 }, size, area);
    expect(place).toEqual({ x: 100 + 160 + POPOVER_GAP, y: 100, side: "right" });
  });

  it("goes to the left of a node near the right edge", () => {
    const place = placePopover({ x: 600, y: 100, width: 160, height: 56 }, size, area);
    expect(place.side).toBe("left");
    expect(place.x).toBe(600 - POPOVER_GAP - size.width);
    expect(inside(place)).toBe(true);
  });

  it("goes below, then above, when neither side has room", () => {
    const wide = { width: 760, height: 80 };
    expect(placePopover({ x: 20, y: 100, width: 760, height: 56 }, wide, area).side).toBe("below");
    expect(placePopover({ x: 20, y: 500, width: 760, height: 56 }, wide, area).side).toBe("above");
  });

  it("is moved up when it would run off the bottom", () => {
    const place = placePopover({ x: 100, y: 570, width: 160, height: 56 }, size, area);
    expect(place.side).toBe("right");
    expect(place.y).toBe(area.height - POPOVER_MARGIN - size.height);
    expect(inside(place)).toBe(true);
  });

  it("stays inside for a node partly outside the area, in every corner", () => {
    for (const [x, y] of [[-100, -30], [760, -30], [-100, 580], [760, 580], [350, 250]]) {
      expect(inside(placePopover({ x, y, width: 160, height: 56 }, size, area))).toBe(true);
    }
  });

  it("starts at the margin when the popover is bigger than the area", () => {
    const place = placePopover({ x: 10, y: 10, width: 160, height: 56 }, { width: 900, height: 700 }, area);
    expect(place.x).toBe(POPOVER_MARGIN);
    expect(place.y).toBe(POPOVER_MARGIN);
  });
});

describe("popoverWidth", () => {
  it("is at most 320 and leaves the margin on both sides of a narrow area", () => {
    expect(popoverWidth(1200)).toBe(320);
    expect(popoverWidth(300)).toBe(300 - 2 * POPOVER_MARGIN);
    expect(popoverWidth(4)).toBe(0);
  });
});
