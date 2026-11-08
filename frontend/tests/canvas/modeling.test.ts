import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EditRefused, MOVE_SAVE_DELAY_MS } from "../../src/models/canvas/diagram/index.ts";
import type { GraphEdit } from "../../src/models/canvas/graph-types.ts";
import { createDiagram, graph, node, nodeType } from "./helpers.ts";

let current: ReturnType<typeof createDiagram>;
const sent: GraphEdit[] = [];
let answer: (edit: GraphEdit) => Promise<void>;

beforeEach(() => {
  sent.length = 0;
  answer = async () => undefined;
  current = createDiagram();
  current.importer.update(graph({ nodes: [node("a", "t1", 40, 40), node("b", "t1", 300, 40), node("c", "t2", 40, 200)], nodeTypes: [nodeType("t1"), nodeType("t2")] }));
  current.modeling.setSender(async (edit) => { sent.push(edit); await answer(edit); });
});
afterEach(() => { vi.useRealTimers(); current.destroy(); });

const refuse = () => { answer = () => Promise.reject(new Error("refused by the server")); };

describe("applyEdit: accepted by the server", () => {
  it("deletes a node and its connection at once and sends one write", async () => {
    const done = current.modeling.applyEdit({ kind: "node.delete", id: "a" });
    expect(current.registry.get("a")).toBeUndefined();
    expect(current.registry.get("ab")).toBeUndefined();
    await done;
    expect(sent).toEqual([{ kind: "elements.delete", nodeIds: ["a"], connectionIds: [] }]);
    expect(current.commandStack.canUndo()).toBe(true);
  });

  it("renames a node on the command stack", async () => {
    const done = current.modeling.applyEdit({ kind: "node.update", id: "a", name: "Renamed", description: "text" });
    expect(current.registry.get("a").businessObject.node.name).toBe("Renamed");
    await done;
    expect(current.host.querySelector('[data-element-id="a"] .shadow-node-name')?.textContent).toBe("Renamed");
    expect(current.host.querySelector('[data-element-id="a"]')?.getAttribute("aria-label")).toBe("Renamed (Type t1)");
  });

  it("draws a new node and a new connection as pending elements until the next load replaces them", async () => {
    await current.modeling.applyEdit({ kind: "node.create", nodeTypeId: "t1", name: "New", x: 500, y: 300 });
    const pending = current.registry.filter((element: any) => element.businessObject?.pending);
    expect(pending).toHaveLength(1);
    expect([pending[0].x, pending[0].y]).toEqual([500, 300]);
    await current.modeling.applyEdit({ kind: "connection.create", connectionTypeId: "c1", sourceId: "b", targetId: "a" });
    expect(current.registry.filter((element: any) => element.businessObject?.pending)).toHaveLength(2);
    // The load after the write has neither: both pending elements go.
    current.importer.update(graph({ nodes: [node("a", "t1", 40, 40), node("b", "t1", 300, 40), node("c", "t2", 40, 200)], nodeTypes: [nodeType("t1"), nodeType("t2")] }));
    expect(current.registry.filter((element: any) => element.businessObject?.pending)).toHaveLength(0);
  });
});

describe("applyEdit: refused", () => {
  it("restores a deleted node with its connection and passes the error on", async () => {
    refuse();
    await expect(current.modeling.applyEdit({ kind: "node.delete", id: "a" })).rejects.toThrow("refused by the server");
    expect(current.registry.get("a")).toBeDefined();
    expect(current.registry.get("ab")).toBeDefined();
    expect(current.registry.get("a").outgoing).toHaveLength(1);
    expect(current.commandStack.canUndo()).toBe(false);
  });

  it("restores the old name", async () => {
    refuse();
    await expect(current.modeling.applyEdit({ kind: "node.update", id: "a", name: "Renamed", description: null })).rejects.toThrow();
    expect(current.registry.get("a").businessObject.node.name).toBe("Node a");
    expect(current.host.querySelector('[data-element-id="a"] .shadow-node-name')?.textContent).toBe("Node a");
  });

  it("removes a node and a connection that were drawn too early", async () => {
    refuse();
    await expect(current.modeling.applyEdit({ kind: "node.create", nodeTypeId: "t1", name: "New", x: 0, y: 300 })).rejects.toThrow();
    await expect(current.modeling.applyEdit({ kind: "connection.create", connectionTypeId: "c1", sourceId: "b", targetId: "a" })).rejects.toThrow();
    expect(current.registry.filter((element: any) => element.businessObject?.pending)).toHaveLength(0);
    expect(current.registry.get("b").outgoing).toHaveLength(0);
  });

  it("does not undo a later gesture: when something else was done since, the next load puts the server's state back", async () => {
    let fail!: (error: Error) => void;
    answer = () => new Promise((_, reject) => { fail = reject; });
    const first = current.modeling.applyEdit({ kind: "node.delete", id: "c" });
    current.modelingService.moveElements([current.registry.get("a")], { x: 10, y: 0 });
    fail(new Error("refused"));
    await expect(first).rejects.toThrow();
    expect(current.registry.get("a").x).toBe(50);
    expect(current.registry.get("c")).toBeUndefined();
  });
});

describe("applyEdit: refused before sending", () => {
  it("refuses a self-connection, a type the Metamodel does not allow, and a duplicate, without calling the server", async () => {
    const cause = async (edit: GraphEdit) => (await current.modeling.applyEdit(edit).catch((error: unknown) => error)) as EditRefused;
    expect((await cause({ kind: "connection.create", connectionTypeId: "c1", sourceId: "a", targetId: "a" })).cause).toBe("self");
    expect((await cause({ kind: "connection.create", connectionTypeId: "c1", sourceId: "a", targetId: "c" })).cause).toBe("not_allowed");
    expect((await cause({ kind: "connection.create", connectionTypeId: "c1", sourceId: "a", targetId: "b" })).cause).toBe("duplicate");
    expect(sent).toEqual([]);
  });

  it("refuses an element that is not on the canvas", async () => {
    const error = (await current.modeling.applyEdit({ kind: "node.delete", id: "nope" }).catch((cause: unknown) => cause)) as EditRefused;
    expect(error).toBeInstanceOf(EditRefused);
    expect(error.cause).toBe("missing");
  });

  it("refuses every edit on a read-only canvas", async () => {
    current.importer.update(graph(), true);
    const error = (await current.modeling.applyEdit({ kind: "node.delete", id: "a" }).catch((cause: unknown) => cause)) as EditRefused;
    expect(error.cause).toBe("read_only");
    expect(sent).toEqual([]);
  });
});

describe("moving nodes", () => {
  it("collects moves and sends them once, rounded, after 400 ms of quiet", async () => {
    vi.useFakeTimers();
    current.modelingService.moveElements([current.registry.get("a")], { x: 10.4, y: 0 });
    await vi.advanceTimersByTimeAsync(MOVE_SAVE_DELAY_MS - 50);
    current.modelingService.moveElements([current.registry.get("a"), current.registry.get("b")], { x: 0, y: 20 });
    await vi.advanceTimersByTimeAsync(MOVE_SAVE_DELAY_MS - 50);
    expect(sent).toEqual([]);
    await vi.advanceTimersByTimeAsync(60);
    expect(sent).toEqual([{ kind: "node.move", moves: [{ id: "a", x: 50, y: 60 }, { id: "b", x: 300, y: 60 }] }]);
    expect(current.modeling.hasUnsavedMove("a")).toBe(false);
  });

  it("puts the nodes back when the server refuses the positions", async () => {
    vi.useFakeTimers();
    refuse();
    current.modelingService.moveElements([current.registry.get("a")], { x: 100, y: 0 });
    current.modelingService.moveElements([current.registry.get("a")], { x: 0, y: 100 });
    await vi.advanceTimersByTimeAsync(MOVE_SAVE_DELAY_MS + 10);
    expect(sent).toHaveLength(1);
    expect([current.registry.get("a").x, current.registry.get("a").y]).toEqual([40, 40]);
  });

  it("flushes pending moves at once on request", async () => {
    vi.useFakeTimers();
    current.modelingService.moveElements([current.registry.get("c")], { x: 5, y: 5 });
    await current.modeling.flush();
    expect(sent).toEqual([{ kind: "node.move", moves: [{ id: "c", x: 45, y: 205 }] }]);
  });
});
