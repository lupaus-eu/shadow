import { afterEach, describe, expect, it } from "vitest";

import { readTypeCollapse, writeTypeCollapse } from "../../src/models/canvas/type-collapse.ts";
import type { GraphFilter } from "../../src/models/canvas/diagram/GraphFilter.ts";
import type { GraphNavigation } from "../../src/models/canvas/diagram/GraphNavigation.ts";
import { groupNodes, hideAllTypes, isGroupOpen, isNodeVisible, nextPlacement, searchMatches, showAllTypes, toggleType } from "../../src/models/canvas/type-list.ts";
import { connection, connectionType, createDiagram, graph, node, nodeType } from "./helpers.ts";

const named = (id: string, name: string) => ({ ...nodeType(id), name });
const sample = () => graph({
  nodeTypes: [named("t2", "Unit"), named("t1", "Team"), named("t3", "Role")],
  nodes: [node("a", "t1", 0, 0, "Sales"), node("b", "t1", 0, 0, "Alpha"), node("c", "t2", 0, 0, "Support"), node("d", "t9", 0, 0, "Orphan")],
});

describe("groupNodes", () => {
  it("sorts types by name, nodes by name, keeps empty types and counts nodes", () => {
    const groups = groupNodes(sample());
    expect(groups.map((group) => group.type.name)).toEqual(["Role", "Team", "Unit"]);
    expect(groups.map((group) => group.nodes.map((item) => item.name))).toEqual([[], ["Alpha", "Sales"], ["Support"]]);
    // A node of an unknown type is not listed; the counts match the nodes that are.
    expect(groups.reduce((sum, group) => sum + group.nodes.length, 0)).toBe(3);
  });

  it("sorts numbers naturally and ties by id", () => {
    const groups = groupNodes(graph({ nodeTypes: [named("t1", "T")], nodes: [node("z", "t1", 0, 0, "Node 10"), node("y", "t1", 0, 0, "Node 2"), node("x", "t1", 0, 0, "Node 2")] }));
    expect(groups[0].nodes.map((item) => item.id)).toEqual(["x", "y", "z"]);
  });
});

describe("visibility", () => {
  it("toggles one type, shows all and hides all", () => {
    const groups = groupNodes(sample());
    const hidden = toggleType(new Set(), "t1");
    expect([...hidden]).toEqual(["t1"]);
    expect(isNodeVisible(node("a", "t1"), hidden)).toBe(false);
    expect(isNodeVisible(node("c", "t2"), hidden)).toBe(true);
    expect(toggleType(hidden, "t1").size).toBe(0);
    expect(hideAllTypes(groups).size).toBe(3);
    expect(showAllTypes().size).toBe(0);
  });
});

describe("searchMatches", () => {
  const groups = groupNodes(sample());
  it("is null without a query and matches names case-insensitively in list order", () => {
    expect(searchMatches(groups, "  ", new Set())).toBeNull();
    expect(searchMatches(groups, "S", new Set())?.map((item) => item.name)).toEqual(["Alpha", "Sales", "Support"].filter((name) => /s/i.test(name)));
    expect(searchMatches(groups, "SALES", new Set())?.map((item) => item.id)).toEqual(["a"]);
    expect(searchMatches(groups, "zzz", new Set())).toEqual([]);
  });
  it("never matches nodes of hidden types", () => {
    expect(searchMatches(groups, "s", new Set(["t1"]))?.map((item) => item.id)).toEqual(["c"]);
  });
});

describe("isGroupOpen and placement", () => {
  const [role, team] = groupNodes(sample());
  it("empty types start collapsed, the person's choice wins, a search opens groups with a match", () => {
    expect(isGroupOpen(role, {}, null)).toBe(false);
    expect(isGroupOpen(team, {}, null)).toBe(true);
    expect(isGroupOpen(team, { t1: true }, null)).toBe(false);
    expect(isGroupOpen(role, { t3: false }, null)).toBe(true);
    expect(isGroupOpen(team, { t1: true }, new Set(["a"]))).toBe(true);
    expect(isGroupOpen(team, {}, new Set(["zzz"]))).toBe(false);
  });
  it("places new nodes on the grid used until drawing arrives", () => {
    expect(nextPlacement(0)).toEqual({ x: 30, y: 30 });
    expect(nextPlacement(9)).toEqual({ x: 200, y: 90 });
  });
});

describe("type collapse storage", () => {
  const memory = () => {
    const data = new Map<string, string>();
    return { data, getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => { data.set(key, value); } };
  };
  it("round-trips per model and keeps other models", () => {
    const store = memory();
    writeTypeCollapse("m1", { t1: true, t2: false }, store);
    writeTypeCollapse("m2", { t1: false }, store);
    expect(readTypeCollapse("m1", store)).toEqual({ t1: true, t2: false });
    expect(readTypeCollapse("m2", store)).toEqual({ t1: false });
    expect(readTypeCollapse("m3", store)).toEqual({});
    expect([...store.data.keys()]).toEqual(["shadow.canvas.typeCollapse"]);
  });
  it("blocked, missing and malformed storage give the defaults and never throw", () => {
    const blocked = { getItem: () => { throw new DOMException("blocked", "SecurityError"); }, setItem: () => { throw new DOMException("blocked", "SecurityError"); } };
    expect(readTypeCollapse("m", blocked)).toEqual({});
    expect(() => writeTypeCollapse("m", { t: true }, blocked)).not.toThrow();
    expect(readTypeCollapse("m", null)).toEqual({});
    expect(() => writeTypeCollapse("m", { t: true }, null)).not.toThrow();
    for (const bad of ["{oops", "null", "42", "[]", '{"m":"x"}', '{"m":{"t":"yes"}}']) {
      const store = memory();
      store.data.set("shadow.canvas.typeCollapse", bad);
      expect(readTypeCollapse("m", store), bad).toEqual({});
    }
  });
});

// The filter on a headless diagram: hidden types and search become markers, nothing leaves the model.
let current: ReturnType<typeof createDiagram> | null = null;
afterEach(() => { current?.destroy(); current = null; });

function open() {
  current = createDiagram();
  const { diagram, importer } = current;
  (diagram.get("canvas") as { getSize(): { width: number; height: number } }).getSize = () => ({ width: 1000, height: 600 });
  importer.update(graph({
    nodeTypes: [nodeType("t1"), nodeType("t2")],
    nodes: [node("a", "t1", 40, 40), node("b", "t2", 300, 40), node("c", "t1", 600, 40)],
    connections: [connection("ab", "a", "b"), connection("ac", "a", "c")],
    connectionTypes: [connectionType("c1")],
    allowedConnections: [
      { connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t2" },
      { connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t1" },
    ],
  }));
  const navigation = diagram.get("graphNavigation") as GraphNavigation;
  navigation.reducedMotion = () => true;
  return { ...current, filter: diagram.get("graphFilter") as GraphFilter, navigation };
}

describe("GraphFilter", () => {
  it("hides a type's nodes and every connection touching them, and restores them", () => {
    const { filter, canvas, registry } = open();
    filter.apply({ hiddenTypeIds: new Set(["t2"]), matchIds: null });
    expect(canvas.hasMarker(registry.get("b"), "shadow-hidden")).toBe(true);
    expect(canvas.hasMarker(registry.get("ab"), "shadow-hidden")).toBe(true);
    expect(canvas.hasMarker(registry.get("a"), "shadow-hidden")).toBe(false);
    expect(canvas.hasMarker(registry.get("ac"), "shadow-hidden")).toBe(false);
    // Still in the model.
    expect(registry.get("b")).toBeDefined();
    expect(registry.get("ab")).toBeDefined();
    filter.apply({ hiddenTypeIds: new Set(), matchIds: null });
    expect(registry.filter((element: any) => canvas.hasMarker(element, "shadow-hidden"))).toHaveLength(0);
  });

  it("hiding every type hides all connections", () => {
    const { filter, canvas, registry } = open();
    filter.apply({ hiddenTypeIds: new Set(["t1", "t2"]), matchIds: null });
    expect(registry.filter((element: any) => element.parent && !canvas.hasMarker(element, "shadow-hidden"))).toHaveLength(0);
  });

  it("a search outlines matches and dims the rest; a connection with a matching end is not dimmed; clearing restores", () => {
    const { filter, canvas, registry } = open();
    filter.apply({ hiddenTypeIds: new Set(), matchIds: new Set(["a"]) });
    expect(canvas.hasMarker(registry.get("a"), "shadow-match")).toBe(true);
    expect(canvas.hasMarker(registry.get("a"), "shadow-dim")).toBe(false);
    expect(canvas.hasMarker(registry.get("b"), "shadow-dim")).toBe(true);
    expect(canvas.hasMarker(registry.get("ab"), "shadow-dim")).toBe(false);
    filter.apply({ hiddenTypeIds: new Set(), matchIds: new Set(["c"]) });
    expect(canvas.hasMarker(registry.get("ab"), "shadow-dim")).toBe(true);
    expect(canvas.hasMarker(registry.get("ac"), "shadow-dim")).toBe(false);
    filter.apply({ hiddenTypeIds: new Set(), matchIds: null });
    expect(registry.filter((element: any) => canvas.hasMarker(element, "shadow-dim") || canvas.hasMarker(element, "shadow-match"))).toHaveLength(0);
  });

  it("a hidden node is neither matched nor dimmed", () => {
    const { filter, canvas, registry } = open();
    filter.apply({ hiddenTypeIds: new Set(["t2"]), matchIds: new Set(["b"]) });
    expect(canvas.hasMarker(registry.get("b"), "shadow-match")).toBe(false);
    expect(canvas.hasMarker(registry.get("b"), "shadow-dim")).toBe(false);
  });

  it("Fit ignores hidden nodes, and focus centres and zooms in to at least 100 %", () => {
    const { filter, navigation } = open();
    const all = navigation.graphBounds()!;
    filter.apply({ hiddenTypeIds: new Set(["t1"]), matchIds: null });
    const rest = navigation.graphBounds()!;
    expect(rest.width).toBeLessThan(all.width);
    navigation.setView({ x: 0, y: 0, scale: 0.5 });
    navigation.focus({ x: 700, y: 300 }, 1, false);
    const view = navigation.getView();
    expect(view.scale).toBe(1);
    expect(view.x + 500).toBeCloseTo(700, 1);
    expect(view.y + 300).toBeCloseTo(300, 1);
    navigation.setView({ x: 0, y: 0, scale: 2 });
    navigation.focus({ x: 700, y: 300 }, 1, false);
    expect(navigation.getView().scale).toBe(2);
  });
});
