import { afterEach, describe, expect, it, vi } from "vitest";

import { attachMinimap } from "../../src/models/canvas/minimap.ts";
import type { GraphNavigation } from "../../src/models/canvas/diagram/GraphNavigation.ts";
import { createDiagram, graph, node, nodeType } from "./helpers.ts";

// The minimap is the library's, attached after load by `attachMinimap`. jsdom has no layout, so the sizes are given.
let current: ReturnType<typeof createDiagram> | null = null;
afterEach(() => { current?.destroy(); current = null; });

function open(opened = true) {
  current = createDiagram();
  const canvas = current.diagram.get("canvas") as { getSize(): { width: number; height: number } };
  canvas.getSize = () => ({ width: 1000, height: 600 });
  current.importer.update(graph({
    nodes: [node("a", "t1", 40, 40), node("b", "t1", 300, 40), node("h", "t2", 300, 300)],
    nodeTypes: [nodeType("t1"), nodeType("t2")],
    connections: [{ id: "ab", connection_type_id: "c1", source_node_id: "a", target_node_id: "b" }],
  }), false);
  const navigation = current.diagram.get("graphNavigation") as GraphNavigation;
  navigation.setView({ x: 0, y: 0, scale: 1 });
  const minimap = attachMinimap(current.diagram as never, opened);
  const parent = current.host.querySelector<HTMLElement>(".djs-minimap")!;
  return { ...current, minimap, parent, navigation };
}

const drawn = (parent: HTMLElement) => parent.querySelectorAll(".map svg > g:first-child > g").length;

describe("attachMinimap", () => {
  it("is a decorative aria-hidden view inside the canvas that shows every node and the connections", () => {
    const { parent, minimap } = open();
    expect(parent.getAttribute("aria-hidden")).toBe("true");
    expect(minimap.isOpen()).toBe(true);
    expect(parent.classList.contains("open")).toBe(true);
    // Three nodes and one connection.
    expect(drawn(parent)).toBe(4);
  });

  it("opens and closes, and can start closed", () => {
    const { parent, minimap } = open(false);
    expect(minimap.isOpen()).toBe(false);
    expect(parent.classList.contains("open")).toBe(false);
    minimap.open();
    expect(parent.classList.contains("open")).toBe(true);
    expect(drawn(parent)).toBe(4);
    minimap.close();
    expect(parent.classList.contains("open")).toBe(false);
  });

  it("leaves a hidden type's nodes and connections out after a refresh, and brings them back", () => {
    const { parent, minimap, canvas, registry } = open();
    for (const id of ["h"]) (canvas as any).addMarker(registry.get(id), "shadow-hidden");
    for (const id of ["ab"]) (canvas as any).addMarker(registry.get(id), "shadow-hidden");
    minimap.refresh();
    expect(drawn(parent)).toBe(2);
    for (const id of ["h", "ab"]) (canvas as any).removeMarker(registry.get(id), "shadow-hidden");
    minimap.refresh();
    expect(drawn(parent)).toBe(4);
  });

  it("moves the view through GraphNavigation.setView when the minimap is clicked", () => {
    const { parent, navigation } = open();
    const svg = parent.querySelector<SVGSVGElement>(".map svg")!;
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, right: 240, bottom: 150, width: 240, height: 150, x: 0, y: 0, toJSON: () => ({}) });
    parent.querySelector<HTMLElement>(".viewport-dom")!.getBoundingClientRect = () => ({ left: 0, top: 0, right: 100, bottom: 60, width: 100, height: 60, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    parent.getBoundingClientRect = () => ({ left: 0, top: 0, right: 240, bottom: 150, width: 240, height: 150, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    const setView = vi.spyOn(navigation, "setView");
    const before = navigation.getView();
    svg.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, clientX: 200, clientY: 120 }));
    document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, clientX: 200, clientY: 120 }));
    expect(setView).toHaveBeenCalled();
    const after = navigation.getView();
    expect(after.scale).toBeCloseTo(before.scale, 5);
    expect(after.x).toBeGreaterThan(before.x);
    expect(after.y).toBeGreaterThan(before.y);
  });
});
