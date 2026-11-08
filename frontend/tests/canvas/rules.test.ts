import { afterEach, describe, expect, it } from "vitest";

import { checkConnection, connectionKey } from "../../src/models/canvas/diagram/GraphRules.ts";
import { connection, createDiagram, graph, node, nodeType } from "./helpers.ts";

let current: ReturnType<typeof createDiagram>;
afterEach(() => current?.destroy());

const allowed = new Set([connectionKey("c1", "t1", "t2")]);
const a = { id: "a", nodeTypeId: "t1" };
const b = { id: "b", nodeTypeId: "t2" };

describe("checkConnection", () => {
  it("allows a connection the metamodel lists", () => {
    expect(checkConnection({ allowed, connectionTypeId: "c1", source: a, target: b, existing: [] })).toEqual({ allowed: true });
  });
  it("refuses a node connected to itself, before anything else", () => {
    expect(checkConnection({ allowed, connectionTypeId: "c1", source: a, target: a, existing: [] })).toEqual({ allowed: false, cause: "self" });
  });
  it("refuses a triple the metamodel does not list, in either direction", () => {
    expect(checkConnection({ allowed, connectionTypeId: "c1", source: b, target: a, existing: [] })).toEqual({ allowed: false, cause: "not_allowed" });
    expect(checkConnection({ allowed, connectionTypeId: "c2", source: a, target: b, existing: [] })).toEqual({ allowed: false, cause: "not_allowed" });
  });
  it("refuses a second connection of the same type between the same nodes", () => {
    const existing = [{ connectionTypeId: "c1", sourceId: "a", targetId: "b" }];
    expect(checkConnection({ allowed, connectionTypeId: "c1", source: a, target: b, existing })).toEqual({ allowed: false, cause: "duplicate" });
  });
  it("accepts a connection of another type, or the other way, over an existing one", () => {
    const both = new Set([connectionKey("c1", "t1", "t2"), connectionKey("c2", "t1", "t2"), connectionKey("c1", "t2", "t1")]);
    const existing = [{ connectionTypeId: "c1", sourceId: "a", targetId: "b" }];
    expect(checkConnection({ allowed: both, connectionTypeId: "c2", source: a, target: b, existing }).allowed).toBe(true);
    expect(checkConnection({ allowed: both, connectionTypeId: "c1", source: b, target: a, existing }).allowed).toBe(true);
  });
});

describe("GraphRules on a diagram", () => {
  const load = (readOnly = false) => {
    current = createDiagram();
    current.importer.update(graph({ nodes: [node("a"), node("b", "t1", 300, 0), node("c", "t2", 0, 200)], nodeTypes: [nodeType("t1"), nodeType("t2")], connections: [connection("ab", "a", "b")] }), readOnly);
    const rules = (action: string, context: object) => (current.diagram.get("rules") as { allowed(action: string, context: object): boolean }).allowed(action, context);
    return { rules, shape: (id: string) => current.registry.get(id) };
  };
  const link = (typeId: string) => ({ businessObject: { kind: "connection", connection: { id: "x", connection_type_id: typeId, source_node_id: "", target_node_id: "" }, connectionType: undefined, change: null } });

  it("allows connections the Metamodel allows and refuses duplicates and self-connections", () => {
    const { rules, shape } = load();
    expect(rules("connection.create", { source: shape("b"), target: shape("a"), connection: link("c1") })).toBe(true);
    expect(rules("connection.create", { source: shape("a"), target: shape("b"), connection: link("c1") })).toBe(false);
    expect(rules("connection.create", { source: shape("a"), target: shape("a"), connection: link("c1") })).toBe(false);
    expect(rules("connection.create", { source: shape("a"), target: shape("c"), connection: link("c1") })).toBe(false);
  });

  it("lets a writable canvas move and delete", () => {
    const { rules, shape } = load();
    expect(rules("elements.move", { shapes: [shape("a")] })).toBe(true);
    expect(rules("elements.delete", { elements: [shape("a")] })).toBe(true);
  });

  it("refuses every edit on a read-only canvas", () => {
    const { rules, shape } = load(true);
    for (const action of ["elements.move", "shape.move", "shape.create", "elements.delete", "connection.create", "connection.reconnect"]) {
      expect(rules(action, { shapes: [shape("a")], source: shape("b"), target: shape("a"), connection: link("c1") }), action).toBe(false);
    }
  });

  it("never lets a node be resized", () => {
    const { rules, shape } = load();
    expect(rules("shape.resize", { shape: shape("a") })).toBe(false);
  });
});
