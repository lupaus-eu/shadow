import { describe, expect, it } from "vitest";

import { distributePlaces, type Box } from "../../src/models/canvas/arrange.ts";
import { GRID_SPACING, readSnap, snapDelta, snapValue, writeSnap } from "../../src/models/canvas/snap.ts";

const box = (id: string, x: number, y: number, width = 160, height = 56): Box => ({ id, x, y, width, height });

describe("distributePlaces", () => {
  it("shares the free space between the outer nodes in equal gaps, whatever order they are given in", () => {
    const places = distributePlaces([box("c", 700, 0), box("a", 100, 0), box("b", 300, 0)], "horizontal")!;
    // 700 - (100 + 160) = 440 of space, the middle node takes 160, 280 left for two gaps: 140 each.
    expect([...places]).toEqual([["b", { x: 400, y: 0 }]]);
  });

  it("is exact with five nodes, vertically, and leaves x alone", () => {
    const places = distributePlaces([box("a", 10, 0), box("b", 10, 70), box("c", 10, 150), box("d", 10, 210), box("e", 10, 600)], "vertical")!;
    // Free: 600 - 56 - 3 * 56 = 376 over four gaps = 94: b at 56 + 94 = 150, c at 150 + 56 + 94 = 300, d at 450.
    expect([...places].map(([id, at]) => [id, at.x, at.y])).toEqual([["b", 10, 150], ["c", 10, 300], ["d", 10, 450]]);
    const tops = [0, 150, 300, 450, 600];
    expect(tops.slice(1).map((top, index) => top - (tops[index] + 56))).toEqual([94, 94, 94, 94]);
  });

  it("treats nodes that overlap on the axis one by one, not as a group", () => {
    const places = distributePlaces([box("a", 0, 0), box("b", 40, 0), box("c", 90, 0), box("d", 800, 0)], "horizontal")!;
    // 800 - 160 = 640 of space, two nodes take 320, 320 for three gaps = 106.67: b at 266.67 -> 267, c at 266.67 + 160 + 106.67 = 533.33 -> 533.
    expect([...places].map(([id, at]) => [id, at.x])).toEqual([["b", 267], ["c", 533]]);
    // The gaps are whole units and differ by one at most: 267 - 160 = 107, 533 - 427 = 106, 800 - 693 = 107.
  });

  it("does nothing for two nodes, or when there is no space to share", () => {
    expect(distributePlaces([box("a", 0, 0), box("b", 500, 0)], "horizontal")).toBeNull();
    expect(distributePlaces([box("a", 0, 0), box("b", 100, 0), box("c", 200, 0)], "horizontal")).toBeNull();
  });
});

describe("snapping arithmetic", () => {
  it("rounds to the nearest grid line", () => {
    expect([snapValue(104), snapValue(105), snapValue(106), snapValue(-4), snapValue(-6)]).toEqual([100, 110, 110, -0, -10]);
    expect(snapValue(37, 25)).toBe(25);
    expect(GRID_SPACING).toBe(10);
  });

  it("finds the move that ends the node's corner on the grid", () => {
    expect(snapDelta({ x: 103, y: 47 }, { x: 18, y: 22 })).toEqual({ x: 17, y: 23 });
    expect(snapDelta({ x: 100, y: 50 }, { x: 3, y: -4 })).toEqual({ x: 0, y: 0 });
  });
});

describe("the snap preference", () => {
  const store = (initial: string | null = null) => {
    let value = initial;
    return { getItem: () => value, setItem: (_key: string, next: string) => { value = next; }, peek: () => value };
  };

  it("is off by default and when the stored value is odd or storage is missing", () => {
    expect(readSnap(store())).toBe(false);
    expect(readSnap(store("yes"))).toBe(false);
    expect(readSnap(store("{"))).toBe(false);
    expect(readSnap(null)).toBe(false);
  });

  it("round-trips the choice", () => {
    const kept = store();
    writeSnap(true, kept);
    expect(kept.peek()).toBe("true");
    expect(readSnap(kept)).toBe(true);
    writeSnap(false, kept);
    expect(readSnap(kept)).toBe(false);
  });

  it("never throws when storage is blocked", () => {
    const blocked = { getItem: () => { throw new DOMException("blocked", "SecurityError"); }, setItem: () => { throw new DOMException("blocked", "SecurityError"); } };
    expect(readSnap(blocked)).toBe(false);
    expect(() => writeSnap(true, blocked)).not.toThrow();
  });
});
