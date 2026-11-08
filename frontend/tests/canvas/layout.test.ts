import { describe, expect, it } from "vitest";

import { COMPONENT_SPACING, LAYOUT_OPTIONS, computeLayout, fromElkGraph, hasNoOverlap, placeLayout, toElkGraph, type LayoutEdge, type LayoutNode } from "../../src/models/canvas/layout.ts";

const node = (id: string, width = 160, height = 56): LayoutNode => ({ id, width, height });

describe("toElkGraph", () => {
  it("maps nodes with their sizes and connections with one source and one target, asking for the layered algorithm", () => {
    const graph = toElkGraph([node("a"), node("b", 100, 40)], [{ id: "ab", source: "a", target: "b" }]);
    expect(graph.layoutOptions).toMatchObject({ "elk.algorithm": "layered", "elk.direction": "RIGHT" });
    expect(graph.children).toEqual([{ id: "a", width: 160, height: 56 }, { id: "b", width: 100, height: 40 }]);
    expect(graph.edges).toEqual([{ id: "ab", sources: ["a"], targets: ["b"] }]);
    expect(LAYOUT_OPTIONS["elk.separateConnectedComponents"]).toBe("true");
    expect(COMPONENT_SPACING).toBeGreaterThan(0);
  });

  it("leaves out connections to unknown nodes and from a node to itself", () => {
    const graph = toElkGraph([node("a"), node("b")], [{ id: "x", source: "a", target: "gone" }, { id: "self", source: "a", target: "a" }, { id: "ok", source: "b", target: "a" }]);
    expect(graph.edges?.map((edge) => edge.id)).toEqual(["ok"]);
  });
});

describe("fromElkGraph and placeLayout", () => {
  it("reads whole-unit positions, and moves the layout's corner to the anchor", () => {
    const positions = fromElkGraph({ id: "root", children: [{ id: "a", x: 0.4, y: 0 }, { id: "b", x: 250.6, y: 76 }] });
    expect([...positions]).toEqual([["a", { x: 0, y: 0 }], ["b", { x: 251, y: 76 }]]);
    expect([...placeLayout(positions, { x: 40, y: -20 })]).toEqual([["a", { x: 40, y: -20 }], ["b", { x: 291, y: 56 }]]);
  });

  it("keeps the layout's own shape when its corner is not at zero, and handles an empty layout", () => {
    const placed = placeLayout(new Map([["a", { x: 10, y: 10 }], ["b", { x: 30, y: 50 }]]), { x: 0, y: 0 });
    expect([...placed]).toEqual([["a", { x: 0, y: 0 }], ["b", { x: 20, y: 40 }]]);
    expect(placeLayout(new Map(), { x: 5, y: 5 }).size).toBe(0);
  });
});

describe("hasNoOverlap", () => {
  it("is false for overlapping boxes and true for touching ones", () => {
    expect(hasNoOverlap([{ x: 0, y: 0, width: 10, height: 10 }, { x: 10, y: 0, width: 10, height: 10 }])).toBe(true);
    expect(hasNoOverlap([{ x: 0, y: 0, width: 10, height: 10 }, { x: 9, y: 9, width: 10, height: 10 }])).toBe(false);
  });
});

/** A reproducible pseudo-random number generator (mulberry32), so the graph below is the same every run. */
function random(seed: number) {
  return () => { seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

describe("computeLayout (elkjs runs here, in the test)", () => {
  it("arranges a generated 50-node graph without overlapping boxes, giving every node a place", async () => {
    const next = random(51);
    const nodes: LayoutNode[] = Array.from({ length: 50 }, (_, index) => node(`n${index}`, 120 + Math.floor(next() * 80), 40 + Math.floor(next() * 40)));
    const edges: LayoutEdge[] = [];
    // A spanning forest plus extra cross links and a few parallel and reversed connections; the last five nodes stay unconnected.
    for (let index = 1; index < 45; index++) edges.push({ id: `t${index}`, source: `n${Math.floor(next() * index)}`, target: `n${index}` });
    for (let index = 0; index < 20; index++) edges.push({ id: `x${index}`, source: `n${Math.floor(next() * 45)}`, target: `n${Math.floor(next() * 45)}` });
    edges.push({ id: "p1", source: "n1", target: "n2" }, { id: "p2", source: "n1", target: "n2" }, { id: "p3", source: "n2", target: "n1" });
    const positions = await computeLayout(nodes, edges);
    expect(positions.size).toBe(50);
    const boxes = nodes.map((item) => ({ ...positions.get(item.id)!, width: item.width, height: item.height }));
    expect(boxes.every((box) => Number.isInteger(box.x) && Number.isInteger(box.y))).toBe(true);
    expect(hasNoOverlap(boxes)).toBe(true);
    // And still none after the layout is moved to where the graph was.
    const placed = placeLayout(positions, { x: -300, y: 120 });
    expect(hasNoOverlap(nodes.map((item) => ({ ...placed.get(item.id)!, width: item.width, height: item.height })))).toBe(true);
  }, 30_000);

  it("puts connected nodes in layers from left to right", async () => {
    const positions = await computeLayout([node("a"), node("b"), node("c")], [{ id: "1", source: "a", target: "b" }, { id: "2", source: "b", target: "c" }]);
    expect(positions.get("a")!.x).toBeLessThan(positions.get("b")!.x);
    expect(positions.get("b")!.x).toBeLessThan(positions.get("c")!.x);
  });

  it("is quick and trivial for nothing, and keeps a lone node", async () => {
    expect((await computeLayout([], [])).size).toBe(0);
    expect((await computeLayout([node("a")], [])).get("a")).toEqual({ x: 0, y: 0 });
  });
});
