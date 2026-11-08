import { describe, expect, it } from "vitest";

import { arrowHead, parallelShift, contrastingInk, shapeKind, shapePath, shortenName, wrapLabel } from "../../src/models/canvas/diagram/shapes.ts";

describe("shapeKind", () => {
  it("knows the five shapes, whatever the spelling", () => {
    expect(shapeKind("rectangle")).toBe("rectangle");
    expect(shapeKind("Ellipse")).toBe("ellipse");
    expect(shapeKind("diamond")).toBe("diamond");
    expect(shapeKind("hexagon")).toBe("hexagon");
    expect(shapeKind("round-rectangle")).toBe("roundrectangle");
    expect(shapeKind("roundrectangle")).toBe("roundrectangle");
  });
  it("falls back to a rounded rectangle", () => {
    for (const unknown of ["", "triangle", "star", null, undefined]) expect(shapeKind(unknown)).toBe("roundrectangle");
  });
});

describe("shortenName", () => {
  it("leaves 60 code points alone and shortens 61 to 59 plus an ellipsis", () => {
    expect(shortenName("a".repeat(60))).toBe("a".repeat(60));
    expect(shortenName("a".repeat(61))).toBe(`${"a".repeat(59)}…`);
    expect(shortenName("a".repeat(61))).toHaveLength(60);
  });
  it("shortens an 80 character name to 59 characters and an ellipsis", () => {
    const eighty = "abcdefghij".repeat(8);
    expect(shortenName(eighty)).toBe(`${eighty.slice(0, 59)}…`);
    expect(Array.from(shortenName(eighty))).toHaveLength(60);
  });
  it("counts code points, not UTF-16 units", () => {
    const sixty = "😀".repeat(60);
    expect(sixty).toHaveLength(120); // UTF-16 units
    expect(shortenName(sixty)).toBe(sixty);
    expect(shortenName(`${sixty}x`)).toBe(`${"😀".repeat(59)}…`);
  });
  it("never splits a surrogate pair or a joined emoji it keeps whole", () => {
    const shortened = shortenName(`${"a".repeat(58)}😀😀😀`);
    expect(shortened).toBe(`${"a".repeat(58)}😀…`);
    expect(Array.from(shortened)).toHaveLength(60);
  });
  it("leaves the empty and short names alone", () => {
    expect(shortenName("")).toBe("");
    expect(shortenName("Sales")).toBe("Sales");
  });
});

describe("wrapLabel", () => {
  it("keeps words whole and breaks at the line length", () => {
    expect(wrapLabel("Sales and marketing department", 16, 3)).toEqual(["Sales and", "marketing", "department"]);
  });
  it("ends the last line with an ellipsis when it does not fit", () => {
    const lines = wrapLabel("one two three four five six seven eight", 10, 2);
    expect(lines).toHaveLength(2);
    expect(lines[1].endsWith("…")).toBe(true);
  });
  it("splits a word longer than a line", () => {
    expect(wrapLabel("abcdefghij", 4, 5)).toEqual(["abcd", "efgh", "ij"]);
  });
});

describe("contrastingInk", () => {
  it("uses dark text on light fills and white on dark fills", () => {
    expect(contrastingInk("#cfe3ff")).toBe("#111827");
    expect(contrastingInk("#fff")).toBe("#111827");
    expect(contrastingInk("#0b1f3a")).toBe("#ffffff");
    expect(contrastingInk("#000000")).toBe("#ffffff");
  });
  it("uses dark text for a colour it cannot read", () => {
    expect(contrastingInk("rebeccapurple")).toBe("#111827");
  });
});

describe("shapePath and arrowHead", () => {
  it("places the outline at the shape's position", () => {
    expect(shapePath("rectangle", 10, 4, 5, 6)).toBe("M5,6 L15,6 L15,10 L5,10 Z");
    expect(shapePath("diamond", 10, 4)).toBe("M5,0 L10,2 L5,4 L0,2 Z");
    expect(shapePath("hexagon", 100, 40)).toContain("L100,20");
    expect(shapePath("ellipse", 10, 4)).toContain("a5,2");
  });
  it("points the arrowhead at the tip", () => {
    const [tip, left, right] = arrowHead({ x: 0, y: 0 }, { x: 100, y: 0 }, 10);
    expect(tip).toEqual({ x: 100, y: 0 });
    expect(left.x).toBeLessThan(100);
    expect(right.x).toBeLessThan(100);
    expect(left.y).toBeCloseTo(-right.y);
  });
});

describe("parallelShift", () => {
  const from = { x: 0, y: 0 };
  const to = { x: 100, y: 0 };
  it("keeps a single connection on the line", () => {
    expect(parallelShift(0, 1, from, to)).toEqual({ x: 0, y: 0 });
  });
  it("spreads two connections evenly on both sides, perpendicular to the line", () => {
    const a = parallelShift(0, 2, from, to);
    const b = parallelShift(1, 2, from, to);
    expect(a.x).toBeCloseTo(0);
    expect(b.x).toBeCloseTo(0);
    expect(a.y).toBeCloseTo(-b.y);
    expect(Math.abs(b.y - a.y)).toBeCloseTo(18);
  });
  it("keeps the middle one of three on the line", () => {
    expect(parallelShift(1, 3, from, to)).toEqual({ x: 0, y: 0 });
  });
  it("is perpendicular on a diagonal and safe for two nodes on the same spot", () => {
    const shift = parallelShift(0, 2, { x: 0, y: 0 }, { x: 10, y: 10 });
    expect(shift.x * 10 + shift.y * 10).toBeCloseTo(0);
    expect(parallelShift(0, 2, from, from)).toEqual({ x: 0, y: 0 });
  });
});
