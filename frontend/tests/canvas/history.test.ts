import { beforeEach, describe, expect, it } from "vitest";

import type { EditResult, GraphData, GraphEdit } from "../../src/models/canvas/graph-types.ts";
import { GraphHistory, type HistoryPort } from "../../src/models/canvas/history.ts";
import { connection, createDiagram, graph, node, nodeType } from "./helpers.ts";

/** A tiny in-memory "server": the writes change `data`, and creates answer with a fresh id, as the real routes do. */
function server(initial: GraphData) {
  const state = { data: structuredClone(initial), writes: [] as GraphEdit[], counter: 0, fail: null as null | ((edit: GraphEdit) => Error | null), unread: false };
  const port: HistoryPort = {
    fresh: async () => (state.unread ? null : structuredClone(state.data)),
    isRefusal: (error) => error instanceof Refusal,
    write: async (edit): Promise<EditResult> => {
      const error = state.fail?.(edit);
      if (error) throw error;
      state.writes.push(edit);
      const data = state.data;
      switch (edit.kind) {
        case "node.create": { const id = `n${++state.counter}`; data.nodes.push({ id, node_type_id: edit.nodeTypeId, name: edit.name, description: edit.description ?? null, x: edit.x, y: edit.y }); return { id }; }
        case "node.delete": data.nodes = data.nodes.filter((item) => item.id !== edit.id); data.connections = data.connections.filter((item) => item.source_node_id !== edit.id && item.target_node_id !== edit.id); return;
        case "node.update": Object.assign(data.nodes.find((item) => item.id === edit.id)!, { name: edit.name, description: edit.description }); return;
        case "node.move": for (const move of edit.moves) Object.assign(data.nodes.find((item) => item.id === move.id)!, { x: move.x, y: move.y }); return;
        case "connection.create": { const id = `c${++state.counter}`; data.connections.push({ id, connection_type_id: edit.connectionTypeId, source_node_id: edit.sourceId, target_node_id: edit.targetId }); return { id }; }
        case "connection.delete": data.connections = data.connections.filter((item) => item.id !== edit.id); return;
        case "connection.reroute": Object.assign(data.connections.find((item) => item.id === edit.id)!, { source_node_id: edit.sourceId, target_node_id: edit.targetId }); return;
        case "elements.delete": return;
      }
    },
  };
  return { state, port };
}
class Refusal extends Error {}

const base = () => graph({ nodes: [node("a", "t1", 40, 40), node("b", "t1", 300, 40), node("c", "t1", 40, 200)], connections: [connection("ab", "a", "b")] });
let history: GraphHistory;
beforeEach(() => { history = new GraphHistory(); });

describe("GraphHistory", () => {
  it("undoes and redoes a created node by deleting it and creating it again (a new id the later steps follow)", async () => {
    const { state, port } = server(base());
    state.data.nodes.push({ id: "x1", node_type_id: "t1", name: "New", description: null, x: 5, y: 6 });
    history.record({ label: "create", undo: [{ kind: "node.delete", ref: "x1", expect: { name: "New", description: null, nodeTypeId: "t1" }, touching: [] }], redo: [{ kind: "node.create", ref: "x1", nodeTypeId: "t1", name: "New", description: null, x: 5, y: 6 }] });
    expect(await history.undo(port)).toMatchObject({ status: "done", label: "create" });
    expect(state.data.nodes.map((item) => item.id)).toEqual(["a", "b", "c"]);
    expect(history.state).toMatchObject({ canUndo: false, canRedo: true });
    expect(await history.redo(port)).toMatchObject({ status: "done" });
    expect(state.data.nodes.at(-1)).toMatchObject({ name: "New", node_type_id: "t1", x: 5, y: 6 });
    expect(history.resolve("x1")).toBe(state.data.nodes.at(-1)!.id);
    // The next undo deletes the re-created node, not the old id.
    await history.undo(port);
    expect(state.data.nodes.map((item) => item.id)).toEqual(["a", "b", "c"]);
  });

  it("restores a deleted node with the same name, description, type, position and its connections", async () => {
    const { state, port } = server(base());
    state.data.nodes[0].description = "Sales team";
    const snap = { connectionTypeId: "c1", sourceRef: "a", targetRef: "b" };
    history.record({
      label: "delete",
      redo: [{ kind: "node.delete", ref: "a", expect: { name: "Node a", description: "Sales team", nodeTypeId: "t1" }, touching: [snap] }],
      undo: [{ kind: "node.create", ref: "a", nodeTypeId: "t1", name: "Node a", description: "Sales team", x: 40, y: 40 }, { kind: "connection.create", ref: "ab", ...snap }],
    });
    await port.write({ kind: "node.delete", id: "a" });
    expect(state.data.connections).toHaveLength(0);
    expect(await history.undo(port)).toMatchObject({ status: "done" });
    const back = state.data.nodes.at(-1)!;
    expect(back).toMatchObject({ name: "Node a", description: "Sales team", node_type_id: "t1", x: 40, y: 40 });
    expect(back.id).not.toBe("a");
    // The connection points at the new id, not the deleted one.
    expect(state.data.connections).toEqual([{ id: expect.any(String), connection_type_id: "c1", source_node_id: back.id, target_node_id: "b" }]);
    // Redo deletes the node under its new id.
    expect(await history.redo(port)).toMatchObject({ status: "done" });
    expect(state.data.nodes.map((item) => item.name)).toEqual(["Node b", "Node c"]);
  });

  it("undoes and redoes a rename, a re-route, a connect and a move", async () => {
    const { state, port } = server(base());
    history.record({ label: "rename", undo: [{ kind: "node.update", ref: "a", name: "Node a", description: null, expect: { name: "Sales", description: null } }], redo: [{ kind: "node.update", ref: "a", name: "Sales", description: null, expect: { name: "Node a", description: null } }] });
    state.data.nodes[0].name = "Sales";
    await history.undo(port);
    expect(state.data.nodes[0].name).toBe("Node a");
    await history.redo(port);
    expect(state.data.nodes[0].name).toBe("Sales");

    const reroute = (s: string, t: string, es: string, et: string) => ({ kind: "connection.reroute" as const, ref: "ab", sourceRef: s, targetRef: t, expect: { sourceRef: es, targetRef: et } });
    history.record({ label: "reroute", undo: [reroute("a", "b", "a", "c")], redo: [reroute("a", "c", "a", "b")] });
    state.data.connections[0].target_node_id = "c";
    await history.undo(port);
    expect(state.data.connections[0]).toMatchObject({ source_node_id: "a", target_node_id: "b" });

    history.record({ label: "connect", undo: [{ kind: "connection.delete", ref: "z", expect: { connectionTypeId: "c1", sourceRef: "b", targetRef: "c" } }], redo: [{ kind: "connection.create", ref: "z", connectionTypeId: "c1", sourceRef: "b", targetRef: "c" }] });
    state.data.connections.push({ id: "z", connection_type_id: "c1", source_node_id: "b", target_node_id: "c" });
    await history.undo(port);
    expect(state.data.connections.map((item) => item.id)).toEqual(["ab"]);
    await history.redo(port);
    expect(state.data.connections).toHaveLength(2);

    const move = (to: { x: number; y: number }, from: { x: number; y: number }) => ({ kind: "node.move" as const, moves: [{ ref: "a", to, from }, { ref: "b", to: { x: to.x + 100, y: to.y }, from: { x: from.x + 260, y: from.y } }] });
    history.record({ label: "move", undo: [move({ x: 40, y: 40 }, { x: 90, y: 90 })], redo: [move({ x: 90, y: 90 }, { x: 40, y: 40 })] });
    state.data.nodes[0].x = 90; state.data.nodes[0].y = 90; state.data.nodes[1].x = 350; state.data.nodes[1].y = 90;
    // The old position is written back (one write for every moved node, one undo step).
    const before = state.writes.length;
    await history.undo(port);
    expect(state.writes.slice(before)).toEqual([{ kind: "node.move", moves: [{ id: "a", x: 40, y: 40 }, { id: "b", x: 140, y: 40 }] }]);
    expect(history.labels().undo).not.toContain("move");
  });

  it("refuses an undo when someone changed the element since, drops the entry and leaves the other entries alone", async () => {
    const { state, port } = server(base());
    history.record({ label: "rename", undo: [{ kind: "node.update", ref: "b", name: "Node b", description: null, expect: { name: "Mine", description: null } }], redo: [] });
    history.record({ label: "rename", undo: [{ kind: "node.update", ref: "a", name: "Node a", description: null, expect: { name: "Mine", description: null } }], redo: [] });
    state.data.nodes[0].name = "Theirs"; // someone else renamed a
    state.data.nodes[1].name = "Mine";
    expect(await history.undo(port)).toMatchObject({ status: "refused", reason: "changed" });
    expect(state.writes).toHaveLength(0);
    expect(history.labels()).toEqual({ undo: ["rename"], redo: [] });
    // The older entry still works.
    expect(await history.undo(port)).toMatchObject({ status: "done" });
    expect(state.data.nodes[1].name).toBe("Node b");
  });

  it("refuses when the element is gone, or has connections nobody knew of", async () => {
    const { state, port } = server(base());
    history.record({ label: "create", undo: [{ kind: "node.delete", ref: "gone", expect: { name: "x", description: null, nodeTypeId: "t1" }, touching: [] }], redo: [] });
    expect(await history.undo(port)).toMatchObject({ status: "refused", reason: "missing" });
    history.record({ label: "create", undo: [{ kind: "node.delete", ref: "a", expect: { name: "Node a", description: null, nodeTypeId: "t1" }, touching: [] }], redo: [] });
    expect(await history.undo(port)).toMatchObject({ status: "refused", reason: "changed" }); // a is joined to b by someone
    expect(state.writes).toHaveLength(0);
    expect(history.state.canUndo).toBe(false);
  });

  it("refuses to move a node somebody else moved", async () => {
    const { state, port } = server(base());
    history.record({ label: "move", undo: [{ kind: "node.move", moves: [{ ref: "a", to: { x: 0, y: 0 }, from: { x: 90, y: 90 } }] }], redo: [] });
    expect(await history.undo(port)).toMatchObject({ status: "refused", reason: "changed" });
    expect(state.data.nodes[0]).toMatchObject({ x: 40, y: 40 });
  });

  it("drops the entry when the server answers 409 or 422, keeps it when only the network fails, and keeps both stacks consistent", async () => {
    const { state, port } = server(base());
    const entry = (ref: string) => ({ label: "rename" as const, undo: [{ kind: "node.update" as const, ref, name: `Node ${ref}`, description: null, expect: { name: `Node ${ref}`, description: null } }], redo: [] });
    history.record(entry("a"));
    history.record(entry("b"));
    state.fail = () => new Error("offline");
    expect(await history.undo(port)).toMatchObject({ status: "rejected", dropped: false });
    expect(history.labels().undo).toHaveLength(2);
    state.fail = () => new Refusal("stale");
    expect(await history.undo(port)).toMatchObject({ status: "rejected", dropped: true });
    expect(history.labels()).toEqual({ undo: ["rename"], redo: [] });
    state.fail = null;
    expect(await history.undo(port)).toMatchObject({ status: "done" });
    expect(history.labels()).toEqual({ undo: [], redo: ["rename"] });
  });

  it("drops an entry that failed half way and keeps a failed read", async () => {
    const { state, port } = server(base());
    history.record({ label: "delete", undo: [{ kind: "node.create", ref: "q", nodeTypeId: "t1", name: "Q", description: null, x: 0, y: 0 }, { kind: "node.create", ref: "r", nodeTypeId: "t1", name: "R", description: null, x: 0, y: 0 }], redo: [] });
    state.unread = true;
    expect(await history.undo(port)).toMatchObject({ status: "rejected", dropped: false });
    state.unread = false;
    let count = 0;
    state.fail = () => (++count === 2 ? new Error("offline") : null);
    expect(await history.undo(port)).toMatchObject({ status: "rejected", dropped: true });
    expect(history.state.canUndo).toBe(false);
  });

  it("a new edit ends the redo line, the stack clears, and a running undo blocks a second one", async () => {
    const { state, port } = server(base());
    const entry = { label: "rename" as const, undo: [{ kind: "node.update" as const, ref: "a", name: "Node a", description: null, expect: { name: "Node a", description: null } }], redo: [] };
    history.record(entry);
    await history.undo(port);
    expect(history.state.canRedo).toBe(true);
    history.record(entry);
    expect(history.state.canRedo).toBe(false);
    const first = history.undo(port);
    expect(await history.undo(port)).toEqual({ status: "idle" });
    await first;
    expect(state.writes).toHaveLength(2);
    history.record(entry);
    history.clear();
    expect(history.state).toEqual({ canUndo: false, canRedo: false, busy: false });
  });
});

describe("history recorded by applyEdit", () => {
  let current: ReturnType<typeof createDiagram>;
  const written: GraphEdit[] = [];
  beforeEach(() => {
    written.length = 0;
    current?.destroy();
    current = createDiagram();
    current.importer.update(graph({ nodes: [node("a", "t1", 40, 40), node("b", "t1", 300, 40), node("c", "t2", 40, 200)], nodeTypes: [nodeType("t1"), nodeType("t2")] }));
    current.modeling.setSender(async (edit) => { written.push(edit); return edit.kind === "node.create" ? { id: "new1" } : edit.kind === "connection.create" ? { id: "cx1" } : undefined; });
  });

  it("records create, rename, connect and delete as steps with their inverse; a multi-node delete is one entry", async () => {
    await current.modeling.applyEdit({ kind: "node.create", nodeTypeId: "t1", name: "  Two   words ", x: 1, y: 2 });
    expect(written[0]).toMatchObject({ name: "Two words" });
    await current.modeling.applyEdit({ kind: "node.update", id: "a", name: "Renamed", description: null });
    await current.modeling.applyEdit({ kind: "connection.create", connectionTypeId: "c1", sourceId: "b", targetId: "a" });
    await current.modeling.applyEdit({ kind: "elements.delete", nodeIds: ["c"], connectionIds: [] });
    expect(current.modeling.history.labels().undo).toEqual(["create", "rename", "connect", "delete"]);
  });

  it("deletes a set as one write and one entry; the connection touching the nodes leaves with them and is restored by the undo", async () => {
    await current.modeling.applyEdit({ kind: "elements.delete", nodeIds: ["a", "b"], connectionIds: [] });
    expect(written).toEqual([{ kind: "elements.delete", nodeIds: ["a", "b"], connectionIds: [] }]);
    expect(current.modeling.history.labels().undo).toEqual(["delete"]);
    const outcomes: string[] = [];
    const fresh = graph({ nodes: [node("c", "t2", 40, 200)], connections: [], nodeTypes: [nodeType("t1"), nodeType("t2")] });
    current.modeling.setHistoryPort({ read: async () => fresh, report: (outcome) => outcomes.push(outcome.status) });
    await current.modeling.undo();
    expect(outcomes).toEqual(["done"]);
    expect(written.slice(1).map((edit) => edit.kind)).toEqual(["node.create", "node.create", "connection.create"]);
    expect(written[1]).toMatchObject({ name: "Node a", nodeTypeId: "t1", x: 40, y: 40 });
  });

  it("records nothing when the server refuses, and nothing for a rename that changes nothing", async () => {
    await current.modeling.applyEdit({ kind: "node.update", id: "a", name: "Node a", description: null });
    expect(current.modeling.history.state.canUndo).toBe(false);
    current.modeling.setSender(async () => { throw new Error("refused"); });
    await expect(current.modeling.applyEdit({ kind: "node.delete", id: "a" })).rejects.toThrow();
    expect(current.modeling.history.state.canUndo).toBe(false);
  });

  it("a move of several nodes is one undo step that writes every old position", async () => {
    current.modelingService.moveElements([current.registry.get("a"), current.registry.get("b")], { x: 10, y: 20 });
    await current.modeling.flush();
    expect(written).toEqual([{ kind: "node.move", moves: [{ id: "a", x: 50, y: 60 }, { id: "b", x: 310, y: 60 }] }]);
    expect(current.modeling.history.labels().undo).toEqual(["move"]);
    current.modeling.setHistoryPort({ read: async () => graph({ nodes: [node("a", "t1", 50, 60), node("b", "t1", 310, 60), node("c", "t2", 40, 200)], nodeTypes: [nodeType("t1"), nodeType("t2")] }) });
    const outcome = await current.modeling.undo();
    expect(outcome).toMatchObject({ status: "done", label: "move" });
    expect(written.at(-1)).toEqual({ kind: "node.move", moves: [{ id: "a", x: 40, y: 40 }, { id: "b", x: 300, y: 40 }] });
  });

  it("does not undo on a read-only canvas", async () => {
    current.importer.update(graph(), true);
    expect(await current.modeling.undo()).toEqual({ status: "idle" });
  });
});
