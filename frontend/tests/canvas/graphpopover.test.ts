import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POPOVER_DELAY_MS, type GraphPopover } from "../../src/models/canvas/diagram/GraphPopover.ts";
import { createDiagram, graph, node } from "./helpers.ts";

let current: ReturnType<typeof createDiagram>;
let popover: GraphPopover;
let bus: { fire(event: string, payload?: object): void };
beforeEach(() => {
  vi.useFakeTimers();
  current = createDiagram();
  popover = current.diagram.get("graphPopover") as GraphPopover;
  bus = current.diagram.get("eventBus") as typeof bus;
  current.importer.update(graph({
    nodes: [{ ...node("a", "t1", 40, 40, "Sales"), description: "Sells things" }, node("b", "t1", 300, 40, "Support")],
    connections: [],
  }));
});
afterEach(() => { current.destroy(); vi.useRealTimers(); });

const shown = () => [...current.host.querySelectorAll<HTMLElement>(".shadow-popover")];
const gfx = (id: string) => current.host.querySelector(`[data-element-id="${id}"]`) as SVGElement;
const hover = (id: string) => bus.fire("element.hover", { element: current.registry.get(id), gfx: gfx(id) });
const out = (id: string) => bus.fire("element.out", { element: current.registry.get(id), gfx: gfx(id) });
const focus = (id: string) => gfx(id).dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
const blur = (id: string, to: Element | null = null) => gfx(id).dispatchEvent(new FocusEvent("focusout", { bubbles: true, relatedTarget: to }));

describe("GraphPopover", () => {
  it("opens after a short hover with the full name, type and description, and closes on leave", () => {
    hover("a");
    expect(shown()).toHaveLength(0);
    vi.advanceTimersByTime(POPOVER_DELAY_MS);
    const [box] = shown();
    expect(box.getAttribute("role")).toBe("tooltip");
    expect(box.querySelector(".shadow-popover-name")?.textContent).toBe("Sales");
    expect(box.querySelector(".shadow-popover-type")?.textContent).toBe("Type t1");
    expect(box.querySelector(".shadow-popover-description")?.textContent).toBe("Sells things");
    expect(gfx("a").getAttribute("aria-describedby")).toBe(box.id);
    out("a");
    expect(shown()).toHaveLength(0);
    expect(gfx("a").hasAttribute("aria-describedby")).toBe(false);
  });

  it("does not open when the pointer only passes by", () => {
    hover("a");
    vi.advanceTimersByTime(POPOVER_DELAY_MS - 50);
    out("a");
    vi.advanceTimersByTime(1000);
    expect(shown()).toHaveLength(0);
  });

  it("shows the whole name, however long, and leaves out an empty description", () => {
    const long = "x".repeat(80);
    current.importer.update(graph({ nodes: [node("a", "t1", 40, 40, long)], connections: [] }));
    focus("a");
    expect(shown()[0].querySelector(".shadow-popover-name")?.textContent).toBe(long);
    expect(shown()[0].querySelector(".shadow-popover-description")).toBeNull();
  });

  it("opens at once on keyboard focus and closes when focus leaves", () => {
    focus("a");
    expect(shown()).toHaveLength(1);
    expect(popover.openFor).toBe("a");
    blur("a");
    expect(shown()).toHaveLength(0);
  });

  it("keeps one popover: moving to another node replaces it", () => {
    focus("a");
    focus("b");
    expect(shown()).toHaveLength(1);
    expect(popover.openFor).toBe("b");
  });

  it("closes on Esc without taking the key", () => {
    focus("a");
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    gfx("a").dispatchEvent(event);
    expect(shown()).toHaveLength(0);
    expect(event.defaultPrevented).toBe(false);
  });

  it("closes when the drawing is panned but stays when only the zoom changes", () => {
    focus("a");
    // jsdom cannot pan or zoom the SVG, so the view events are fired the way the library fires them.
    const canvas = current.diagram.get("canvas") as { viewbox(): { x: number; y: number; scale: number; outer: { width: number; height: number } } };
    const view = vi.spyOn(canvas, "viewbox");
    const at = (scale: number) => view.mockReturnValue({ x: 0, y: 0, scale, outer: { width: 800, height: 600 } });
    at(1);
    bus.fire("canvas.viewbox.changing");
    expect(shown()).toHaveLength(0);
    focus("b");
    at(2);
    bus.fire("canvas.viewbox.changing");
    expect(shown()).toHaveLength(1);
    bus.fire("canvas.viewbox.changed", { viewbox: { scale: 2 } });
    expect(shown()).toHaveLength(1);
    expect(popover.openFor).toBe("b");
  });

  it("ignores the node being named and the naming input", () => {
    const element = current.registry.get("a");
    element.businessObject = { ...element.businessObject, draft: true };
    focus("a");
    expect(shown()).toHaveLength(0);
    element.businessObject = { ...element.businessObject, draft: false };
    const editor = document.createElement("div");
    editor.className = "shadow-editor";
    current.host.querySelector(".djs-container")!.append(editor);
    focus("a");
    expect(shown()).toHaveLength(0);
    editor.remove();
    focus("a");
    expect(shown()).toHaveLength(1);
  });

  it("is not opened while a node is dragged", () => {
    bus.fire("drag.init");
    focus("a");
    expect(shown()).toHaveLength(0);
    bus.fire("drag.cleanup");
    focus("a");
    expect(shown()).toHaveLength(1);
  });

  it("shows nothing for a node of a hidden type", () => {
    (current.diagram.get("canvas") as { addMarker(element: unknown, marker: string): void }).addMarker(current.registry.get("a"), "shadow-hidden");
    focus("a");
    expect(shown()).toHaveLength(0);
  });

  it("follows a change of the node: the open popover shows the new name", () => {
    focus("a");
    current.importer.update(graph({ nodes: [node("a", "t1", 40, 40, "Renamed"), node("b", "t1", 300, 40)], connections: [] }));
    expect(shown()).toHaveLength(1);
    expect(shown()[0].querySelector(".shadow-popover-name")?.textContent).toBe("Renamed");
  });

  it("closes when the node goes", () => {
    focus("a");
    current.importer.update(graph({ nodes: [node("b", "t1", 300, 40)], connections: [] }));
    expect(shown()).toHaveLength(0);
  });
});
