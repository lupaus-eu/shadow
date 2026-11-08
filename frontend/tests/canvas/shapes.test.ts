import { describe, expect, it } from "vitest";

import { arrowHead, contrastingInk, shapeKind, shapePath, shortenName, wrapLabel } from "../../src/models/canvas/diagram/shapes.ts";

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
  it("leaves 60 code points alone and shortens 61 with an ellipsis", () => {
    expect(shortenName("a".repeat(60))).toBe("a".repeat(60));
    expect(shortenName("a".repeat(61))).toBe(`${"a".repeat(60)}…`);
  });
  it("counts code points, not UTF-16 units", () => {
    const sixty = "😀".repeat(60);
    expect(shortenName(sixty)).toBe(sixty);
    expect(shortenName(`${sixty}x`)).toBe(`${sixty}…`);
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
