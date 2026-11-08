import { describe, expect, it } from "vitest";

import { connectionOptions, connectionKey } from "../../src/models/canvas/diagram/GraphRules.ts";
import { deleteSummary, freeSpot, planConnection, SPOT_STEP } from "../../src/models/canvas/draw.ts";
import { modelMessages } from "../../src/models/messages.ts";
import { connection, connectionType, graph, node, nodeType } from "./helpers.ts";

describe("freeSpot (a new node at the viewport centre)", () => {
  it("is exactly the centre when nothing is there, and steps aside for a node already there", () => {
    expect(freeSpot({ x: 500, y: 300 }, [])).toEqual({ x: 500, y: 300 });
    expect(freeSpot({ x: 500, y: 300 }, [{ x: 0, y: 0 }])).toEqual({ x: 500, y: 300 });
    expect(freeSpot({ x: 500, y: 300 }, [{ x: 505, y: 302 }])).toEqual({ x: 500 + 2 * SPOT_STEP, y: 300 + 2 * SPOT_STEP });
    expect(freeSpot({ x: 0, y: 0 }, [{ x: 0, y: 0 }, { x: SPOT_STEP, y: SPOT_STEP }])).toEqual({ x: 2 * SPOT_STEP, y: 2 * SPOT_STEP });
  });
});

describe("connectionOptions and planConnection", () => {
  const g = graph({
    nodes: [node("a", "t1"), node("b", "t1"), node("r", "t2")],
    nodeTypes: [nodeType("t1"), nodeType("t2")],
    connectionTypes: [connectionType("c1"), connectionType("c2")],
    allowedConnections: [
      { connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t1" },
      { connection_type_id: "c2", source_node_type_id: "t1", target_node_type_id: "t1" },
      { connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t2" },
    ],
    connections: [connection("x", "a", "b", "c1")],
  });

  it("offers only the types the metamodel allows and that do not exist yet", () => {
    expect(planConnection(g, "a", "b")).toMatchObject({ kind: "create", connectionTypeId: "c2" });
    expect(planConnection(g, "b", "a")).toMatchObject({ kind: "choose", types: [{ id: "c1" }, { id: "c2" }] });
    expect(planConnection(g, "a", "r")).toMatchObject({ kind: "create", connectionTypeId: "c1" });
  });

  it("gives three distinct causes: self, not allowed (with the type names) and duplicate", () => {
    expect(planConnection(g, "a", "a")).toMatchObject({ kind: "refused", cause: "self" });
    expect(planConnection(g, "r", "a")).toMatchObject({ kind: "refused", cause: "not_allowed", sourceType: "Type t2", targetType: "Type t1" });
    expect(planConnection(g, "a", "b", "c1")).toMatchObject({ kind: "refused", cause: "duplicate" });
    expect(planConnection(g, "a", "r", "c2")).toMatchObject({ kind: "refused", cause: "not_allowed" });
    expect(planConnection(g, "a", "b", "c2")).toMatchObject({ kind: "create", connectionTypeId: "c2" });
  });

  it("the three refusals read differently, in both languages, and never carry server text", () => {
    for (const locale of ["en", "fi"] as const) {
      const text = modelMessages(locale);
      const messages = [text.refusalSelf, text.refusalDuplicate, text.refusalNotAllowed("Unit", "Role")];
      expect(new Set(messages).size).toBe(3);
      expect(messages[2]).toContain("Unit");
      expect(messages[2]).toContain("Role");
    }
  });

  it("connectionOptions ignores a connection being re-routed when it is listed as existing", () => {
    const allowed = new Set([connectionKey("c1", "t1", "t1")]);
    const input = { allowed, connectionTypeIds: ["c1"], source: { id: "a", nodeTypeId: "t1" }, target: { id: "b", nodeTypeId: "t1" } };
    expect(connectionOptions({ ...input, existing: [{ id: "x", connectionTypeId: "c1", sourceId: "a", targetId: "b" }] }).refusal).toBe("duplicate");
    expect(connectionOptions({ ...input, existing: [] }).types).toEqual(["c1"]);
  });
});

describe("deleteSummary and the confirmation text", () => {
  const g = graph({
    nodes: [node("a", "t1", 0, 0, "Sales"), node("b", "t1", 0, 0, "Support"), node("c", "t1", 0, 0, "Ops")],
    connections: [connection("ab", "a", "b"), connection("cb", "c", "b"), connection("ac", "a", "c")],
  });

  it("takes every connection touching a deleted node, once, and lists selected loose connections separately", () => {
    const summary = deleteSummary(g, ["a"], ["cb", "ab"]);
    expect(summary.nodes.map((n) => n.name)).toEqual(["Sales"]);
    expect(summary.connections.map((item) => item.connection.id).sort()).toEqual(["ab", "ac", "cb"]);
    expect(summary.alone).toEqual(["cb"]);
  });

  it("names the node and its touching connections, in English and Finnish", () => {
    const en = modelMessages("en");
    const fi = modelMessages("fi");
    expect(en.deleteTitle(["Sales"], ["Sales → Support (Link c1)", "Sales → Ops (Link c1)"])).toBe("Delete the node “Sales”? Its 2 connections will also be deleted: Sales → Support (Link c1), Sales → Ops (Link c1). You can undo this.");
    expect(en.deleteTitle(["A", "B", "C"], [])).toBe("Delete 3 nodes (A, B, C)? You can undo this.");
    expect(en.deleteTitle([], ["x → y (L)"])).toContain("the connection");
    expect(en.deleteTitle(["A"], ["1", "2", "3", "4", "5"])).toContain("1, 2, 3 and 2 more");
    expect(fi.deleteTitle(["Sales"], ["a"])).toContain("Sales");
    expect(fi.deleteTitle(["Sales"], ["a"])).toContain("liitos");
  });
});
