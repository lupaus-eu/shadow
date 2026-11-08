import { afterEach, describe, expect, it } from "vitest";

import { connection, createDiagram, graph, node, nodeType } from "./helpers.ts";

let current: ReturnType<typeof createDiagram>;
const open = () => (current = createDiagram());
afterEach(() => current?.destroy());

describe("GraphImporter", () => {
  it("draws every node and connection once", () => {
    const { importer, registry } = open();
    expect(importer.update(graph())).toEqual({ added: 3, updated: 0, removed: 0 });
    expect(registry.get("a").x).toBe(40);
    expect(registry.get("ab").waypoints).toHaveLength(2);
    expect(registry.get("ab").source.id).toBe("a");
    expect(registry.get("ab").target.id).toBe("b");
  });

  it("changes nothing when the same data comes again, and keeps the same elements", () => {
    const { importer, registry } = open();
    importer.update(graph());
    const before = registry.get("a");
    expect(importer.update(graph())).toEqual({ added: 0, updated: 0, removed: 0 });
    expect(registry.get("a")).toBe(before);
  });

  it("updates a changed node in place: same shape object, new data, moved connections", () => {
    const { importer, registry } = open();
    importer.update(graph());
    const shape = registry.get("b");
    const line = registry.get("ab");
    const waypoints = line.waypoints;
    const summary = importer.update(graph({ nodes: [node("a", "t1", 40, 40), node("b", "t1", 500, 200, "Renamed")] }));
    expect(summary).toEqual({ added: 0, updated: 1, removed: 0 });
    expect(registry.get("b")).toBe(shape);
    expect(shape.businessObject.node.name).toBe("Renamed");
    expect([shape.x, shape.y]).toEqual([500, 200]);
    expect(line.waypoints).not.toEqual(waypoints);
    expect(registry.get("ab")).toBe(line);
  });

  it("adds new elements and removes those that are gone, connections of a removed node included", () => {
    const { importer, registry } = open();
    importer.update(graph());
    const summary = importer.update(graph({ nodes: [node("a", "t1", 40, 40), node("c", "t1", 10, 200)], connections: [] }));
    expect(summary).toEqual({ added: 1, updated: 0, removed: 2 });
    expect(registry.get("b")).toBeUndefined();
    expect(registry.get("ab")).toBeUndefined();
    expect(registry.get("c")).toBeDefined();
    expect(registry.get("a").outgoing).toHaveLength(0);
  });

  it("redraws a node when its type changes colour or shape", () => {
    const { importer, registry } = open();
    importer.update(graph());
    const summary = importer.update(graph({ nodeTypes: [nodeType("t1", "diamond", "#112233")] }));
    expect(summary.updated).toBe(2);
    const body = current.host.querySelector('[data-element-id="a"] .shadow-node-body');
    expect(body?.getAttribute("data-shape")).toBe("diamond");
    expect((body as SVGElement).style.fill).toBe("rgb(17, 34, 51)");
    expect(registry.get("a")).toBeDefined();
  });

  it("marks added and updated elements with a class and a badge, and clears them on the next load", () => {
    const { importer, canvas, registry } = open();
    importer.update(graph({ markers: { added: ["a"], updated: ["ab"], removed: ["gone"] } }));
    expect(canvas.hasMarker(registry.get("a"), "shadow-added")).toBe(true);
    expect(canvas.hasMarker(registry.get("ab"), "shadow-updated")).toBe(true);
    expect(current.host.querySelector('[data-element-id="a"] .shadow-change-badge')?.getAttribute("data-change")).toBe("added");
    expect(current.host.querySelector('[data-element-id="b"] .shadow-change-badge')).toBeNull();
    importer.update(graph());
    expect(canvas.hasMarker(registry.get("a"), "shadow-added")).toBe(false);
    expect(current.host.querySelector(".shadow-change-badge")).toBeNull();
  });

  it("keeps a node with an unsaved move where the person put it", () => {
    const { importer, registry, modeling, modelingService } = open();
    importer.update(graph());
    modelingService.moveElements([registry.get("a")], { x: 100, y: 0 });
    expect(modeling.hasUnsavedMove("a")).toBe(true);
    importer.update(graph());
    expect(registry.get("a").x).toBe(140);
  });

  it("ignores a connection whose node is missing", () => {
    const { importer, registry } = open();
    expect(importer.update(graph({ connections: [connection("x", "a", "missing")] })).added).toBe(2);
    expect(registry.get("x")).toBeUndefined();
  });
});
