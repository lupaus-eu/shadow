import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { GraphEdit } from "../../src/models/canvas/graph-types.ts";
import { hasNoOverlap } from "../../src/models/canvas/layout.ts";
import { createDiagram, graph, node } from "./helpers.ts";

// Align, distribute and snapping on a headless diagram. Nodes are 160 x 56. Every tool ends in exactly one write of positions and one
// history entry, which is what the position-batch assertions below check.
let current: ReturnType<typeof createDiagram>;
const sent: GraphEdit[] = [];

const load = (...nodes: ReturnType<typeof node>[]) => current.importer.update(graph({ nodes, connections: [] }), false);
const pick = (...ids: string[]) => current.selection.select(ids.map((id) => current.registry.get(id)));
const at = (id: string) => { const { x, y } = current.registry.get(id); return { x, y }; };

beforeEach(() => {
  sent.length = 0;
  current = createDiagram();
  current.modeling.setSender(async (edit) => { sent.push(edit); });
});
afterEach(() => current.destroy());

describe("align", () => {
  beforeEach(() => load(node("a", "t1", 100, 40), node("b", "t1", 300, 150), node("c", "t1", 520, 300), node("d", "t1", 900, 900)));

  it("left puts the selected nodes on the leftmost left edge and leaves the others", async () => {
    pick("a", "b", "c");
    expect(await current.tools.align("left")).toBe(true);
    expect([at("a"), at("b"), at("c"), at("d")]).toEqual([{ x: 100, y: 40 }, { x: 100, y: 150 }, { x: 100, y: 300 }, { x: 900, y: 900 }]);
  });

  it("top puts them on the highest top edge", async () => {
    pick("a", "b", "c");
    await current.tools.align("top");
    expect([at("a"), at("b"), at("c")]).toEqual([{ x: 100, y: 40 }, { x: 300, y: 40 }, { x: 520, y: 40 }]);
  });

  it("centre puts the centres of three nodes on one vertical line, the middle of the span", async () => {
    pick("a", "b", "c");
    await current.tools.align("centre");
    // Span 100..680, centre 390; every 160 wide node starts at 390 - 80.
    expect([at("a").x, at("b").x, at("c").x]).toEqual([310, 310, 310]);
    expect([at("a").y, at("b").y, at("c").y]).toEqual([40, 150, 300]);
  });

  it("middle puts the centres on one horizontal line", async () => {
    pick("a", "b", "c");
    await current.tools.align("middle");
    // Span 40..356, middle 198; every 56 high node starts at 198 - 28.
    expect([at("a").y, at("b").y, at("c").y]).toEqual([170, 170, 170]);
    expect([at("a").x, at("b").x, at("c").x]).toEqual([100, 300, 520]);
  });

  it("is one write of positions and one history entry, sent without waiting for the quiet time", async () => {
    pick("a", "b", "c");
    await current.tools.align("left");
    expect(sent).toEqual([{ kind: "node.move", moves: [{ id: "a", x: 100, y: 40 }, { id: "b", x: 100, y: 150 }, { id: "c", x: 100, y: 300 }] }]);
    expect(current.modeling.history.labels()).toEqual({ undo: ["move"], redo: [] });
  });

  it("needs two nodes, and does nothing for one or for connections", async () => {
    pick("a");
    expect(current.tools.canAlign()).toBe(false);
    expect(await current.tools.align("left")).toBe(false);
    expect(sent).toEqual([]);
    pick("a", "b");
    expect(current.tools.canAlign()).toBe(true);
  });
});

describe("distribute", () => {
  it("spreads three nodes horizontally with equal gaps and keeps the outer two", async () => {
    load(node("a", "t1", 100, 0), node("b", "t1", 300, 0), node("c", "t1", 700, 0));
    pick("a", "b", "c");
    expect(await current.tools.distribute("horizontal")).toBe(true);
    // Free space: 700 - (100 + 160) - 160 = 280 between the outer nodes, 140 per gap.
    expect([at("a").x, at("b").x, at("c").x]).toEqual([100, 400, 700]);
    expect(sent).toHaveLength(1);
    expect(current.modeling.history.labels().undo).toEqual(["move"]);
  });

  it("spreads four nodes vertically with equal gaps", async () => {
    load(node("a", "t1", 0, 0), node("b", "t1", 0, 80), node("c", "t1", 0, 160), node("d", "t1", 0, 468));
    pick("a", "b", "c", "d");
    await current.tools.distribute("vertical");
    // Heights 56: from the bottom of the first (56) to the top of the last (468) is 412, less the two nodes between (112) is 300 free, 100 per gap.
    expect([at("a").y, at("b").y, at("c").y, at("d").y]).toEqual([0, 156, 312, 468]);
  });

  it("needs three nodes", async () => {
    load(node("a", "t1", 0, 0), node("b", "t1", 300, 0), node("c", "t1", 900, 0));
    pick("a", "b");
    expect(current.tools.canDistribute()).toBe(false);
    expect(await current.tools.distribute("horizontal")).toBe(false);
    pick("a", "b", "c");
    expect(current.tools.canDistribute()).toBe(true);
  });
});

describe("read-only", () => {
  it("refuses every tool", async () => {
    load(node("a", "t1", 100, 40), node("b", "t1", 300, 150), node("c", "t1", 520, 300));
    current.importer.update(graph({ nodes: [node("a", "t1", 100, 40), node("b", "t1", 300, 150), node("c", "t1", 520, 300)], connections: [] }), true);
    pick("a", "b", "c");
    expect(current.tools.canAlign()).toBe(false);
    expect(await current.tools.align("left")).toBe(false);
    expect(await current.tools.distribute("horizontal")).toBe(false);
    expect(await current.tools.autoLayout()).toBe(false);
  });
});

describe("snapping", () => {
  beforeEach(() => load(node("a", "t1", 103, 47), node("b", "t1", 300, 150)));

  it("is off until turned on, and the library's grid snapping holds the state", () => {
    expect(current.tools.snapping).toBe(false);
    current.tools.setSnapping(true);
    expect(current.tools.snapping).toBe(true);
    current.tools.setSnapping(false);
    expect(current.tools.snapping).toBe(false);
  });

  const drag = (id: string, dx: number, dy: number, original: Partial<MouseEvent> = {}) => {
    const event = { context: { shape: current.registry.get(id) }, dx, dy, originalEvent: original };
    current.tools.snapMove(event);
    return event;
  };

  it("lands the dragged node's top left corner on the grid, whatever the pointer did", () => {
    current.tools.setSnapping(true);
    const event = drag("a", 18, 22);
    // 103 + 18 = 121 -> 120; 47 + 22 = 69 -> 70.
    expect([103 + event.dx, 47 + event.dy]).toEqual([120, 70]);
  });

  it("leaves the drag alone when snapping is off or Ctrl or Cmd is held", () => {
    expect(drag("a", 18, 22)).toMatchObject({ dx: 18, dy: 22 });
    current.tools.setSnapping(true);
    expect(drag("a", 18, 22, { ctrlKey: true })).toMatchObject({ dx: 18, dy: 22 });
    expect(drag("a", 18, 22, { metaKey: true })).toMatchObject({ dx: 18, dy: 22 });
  });
});

describe("auto layout", () => {
  it("arranges 50 drawn nodes without overlaps as one command, one write and one history entry, and keeps the graph's corner", async () => {
    const nodes = Array.from({ length: 50 }, (_, index) => node(`n${index}`, "t1", (index % 10) * 50, Math.floor(index / 10) * 20 + 100));
    const connections = Array.from({ length: 49 }, (_, index) => ({ id: `c${index}`, connection_type_id: "c1", source_node_id: `n${Math.floor(index / 2)}`, target_node_id: `n${index + 1}` }));
    current.importer.update(graph({ nodes, connections }), false);
    const before = new Map(nodes.map((item) => [item.id, { x: item.x, y: item.y }]));
    expect(await current.tools.autoLayout()).toBe(true);
    const boxes = current.registry.filter((element: any) => element.businessObject?.kind === "node").map((element: any) => ({ x: element.x, y: element.y, width: element.width, height: element.height }));
    expect(boxes).toHaveLength(50);
    expect(hasNoOverlap(boxes)).toBe(true);
    expect(Math.min(...boxes.map((box) => box.x))).toBe(0);
    expect(Math.min(...boxes.map((box) => box.y))).toBe(100);
    // One command on the library's stack too: a single undo there puts every node back.
    (current.diagram.get("commandStack") as { undo(): void }).undo();
    expect([...before].every(([id, place]) => current.registry.get(id).x === place.x && current.registry.get(id).y === place.y)).toBe(true);
    expect(sent).toHaveLength(1);
    expect(sent[0].kind).toBe("node.move");
    expect(current.modeling.history.labels()).toEqual({ undo: ["move"], redo: [] });
  }, 30_000);

  it("does nothing for fewer than two nodes", async () => {
    load(node("a", "t1", 10, 10));
    expect(await current.tools.autoLayout()).toBe(false);
    expect(sent).toEqual([]);
  });

  it("is undone in one step: the history writes every node back to where it was", async () => {
    const nodes = [node("a", "t1", 0, 0), node("b", "t1", 0, 100), node("c", "t1", 0, 200)];
    current.importer.update(graph({ nodes, connections: [{ id: "ab", connection_type_id: "c1", source_node_id: "a", target_node_id: "b" }, { id: "bc", connection_type_id: "c1", source_node_id: "b", target_node_id: "c" }] }), false);
    await current.tools.autoLayout();
    sent.length = 0;
    current.modeling.setHistoryPort({ read: async () => graph({ nodes: nodes.map((item) => ({ ...item, x: current.registry.get(item.id).x, y: current.registry.get(item.id).y })), connections: [] }) });
    const outcome = await current.modeling.undo();
    expect(outcome.status).toBe("done");
    // `a` stays where it is (the layout keeps the graph's corner), so only `b` and `c` are written back.
    expect(sent).toEqual([{ kind: "node.move", moves: [{ id: "b", x: 0, y: 100 }, { id: "c", x: 0, y: 200 }] }]);
  });
});

describe("moving the target end of a connection", () => {
  it("re-lays the connection out (the library gives `false` for the end that did not move)", () => {
    current.importer.update(graph({ nodes: [node("a", "t1", 40, 40), node("b", "t1", 300, 40)], connections: [{ id: "ab", connection_type_id: "c1", source_node_id: "a", target_node_id: "b" }] }), false);
    expect(() => current.modelingService.moveElements([current.registry.get("b")], { x: 0, y: 200 })).not.toThrow();
    const waypoints = current.registry.get("ab").waypoints;
    expect(waypoints).toHaveLength(2);
    expect(waypoints.every((point: { x: number; y: number }) => Number.isFinite(point.x) && Number.isFinite(point.y))).toBe(true);
  });
});
