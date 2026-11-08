import { afterEach, describe, expect, it } from "vitest";

import { connection, createDiagram, graph, node } from "./helpers.ts";

let current: ReturnType<typeof createDiagram>;
afterEach(() => current?.destroy());

const start = (id: string) => current.registry.get(id).waypoints[0] as { x: number; y: number };
const end = (id: string) => current.registry.get(id).waypoints.at(-1) as { x: number; y: number };

function draw(connections: ReturnType<typeof connection>[]) {
  current = createDiagram();
  current.importer.update(graph({ nodes: [node("a", "t1", 40, 40), node("b", "t1", 400, 40)], connections }));
}

describe("parallel connections between the same two nodes", () => {
  it("leaves a single connection on the line between the centres", () => {
    draw([connection("c1", "a", "b")]);
    expect(start("c1").y).toBeCloseTo(68);
    expect(end("c1").y).toBeCloseTo(68);
  });

  it("moves two connections apart, both sides of the line, in either direction", () => {
    draw([connection("c1", "a", "b"), connection("c2", "b", "a")]);
    const first = start("c1").y;
    const second = start("c2").y;
    expect(first).not.toBeCloseTo(second);
    expect(Math.abs(first - second)).toBeCloseTo(18);
    expect((first + second) / 2).toBeCloseTo(68);
    // Each stays straight: both ends are level.
    expect(end("c1").y).toBeCloseTo(first);
  });

  it("puts a third one on the line and keeps them 18 apart", () => {
    draw([connection("c1", "a", "b"), connection("c2", "a", "b"), connection("c3", "a", "b")]);
    const ys = ["c1", "c2", "c3"].map((id) => start(id).y).sort((a, b) => a - b);
    expect(ys[1]).toBeCloseTo(68);
    expect(ys[1] - ys[0]).toBeCloseTo(18);
    expect(ys[2] - ys[1]).toBeCloseTo(18);
  });

  it("lays the first connection out again when a second one arrives, and back when it goes", () => {
    draw([connection("c1", "a", "b")]);
    const data = graph({ nodes: [node("a", "t1", 40, 40), node("b", "t1", 400, 40)], connections: [connection("c1", "a", "b"), connection("c2", "a", "b")] });
    current.importer.update(data);
    expect(start("c1").y).not.toBeCloseTo(68);
    current.importer.update(graph({ nodes: data.nodes, connections: [connection("c1", "a", "b")] }));
    expect(start("c1").y).toBeCloseTo(68);
  });

  it("does not offset connections between other pairs", () => {
    current = createDiagram();
    current.importer.update(graph({ nodes: [node("a", "t1", 40, 40), node("b", "t1", 400, 40), node("c", "t1", 400, 300)], connections: [connection("c1", "a", "b"), connection("c2", "a", "c"), connection("c3", "a", "b")] }));
    const straight = current.registry.get("c2").waypoints;
    expect(straight[0].x).toBeGreaterThan(40);
    // c2 runs from the middle of a to the middle of c: its slope is that of the centres.
    const slope = (straight.at(-1).y - straight[0].y) / (straight.at(-1).x - straight[0].x);
    expect(slope).toBeCloseTo((328 - 68) / (480 - 120), 1);
  });
});
