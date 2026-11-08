import { afterEach, describe, expect, it } from "vitest";

import type { GraphKeys } from "../../src/models/canvas/diagram/GraphKeys.ts";
import type { GraphNavigation } from "../../src/models/canvas/diagram/GraphNavigation.ts";
import { createDiagram, graph } from "./helpers.ts";

// jsdom has no layout, so the drawing area is given a size; the view arithmetic itself is covered in view.test.ts, here the diagram-js wiring is.
let current: ReturnType<typeof createDiagram> | null = null;
afterEach(() => { current?.destroy(); current = null; });

function open() {
  current = createDiagram();
  const { diagram, importer } = current;
  const canvas = diagram.get("canvas") as { getSize(): { width: number; height: number } };
  canvas.getSize = () => ({ width: 1000, height: 600 });
  importer.update(graph());
  const navigation = diagram.get("graphNavigation") as GraphNavigation;
  navigation.reducedMotion = () => true;
  return { ...current, navigation, keys: diagram.get("graphKeys") as GraphKeys, svg: current.host.querySelector("svg")! };
}

const press = (svg: Element, key: string, init: KeyboardEventInit = {}, target: Element = svg) =>
  target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init }));

describe("GraphNavigation on a diagram", () => {
  it("zoom steps are clamped to 10 %-400 % and Fit and 100 % place the view", () => {
    const { navigation } = open();
    for (let i = 0; i < 40; i++) navigation.zoomStep(1, false);
    expect(navigation.getView().scale).toBeCloseTo(4, 2);
    for (let i = 0; i < 80; i++) navigation.zoomStep(-1, false);
    expect(navigation.getView().scale).toBeCloseTo(0.1, 2);
    navigation.fit(false);
    const fitted = navigation.getView();
    // The two nodes sit at x 40..300+, so everything fits at 100 % with padding.
    expect(fitted.scale).toBe(1);
    navigation.zoomBy(0.5);
    navigation.actualSize(false);
    expect(navigation.getView().scale).toBe(1);
  });

  it("100 % keeps the centre of the drawing area where it is", () => {
    const { navigation } = open();
    navigation.setView({ x: 100, y: 40, scale: 0.5 });
    const before = navigation.getView();
    const centre = { x: before.x + 500 / before.scale, y: before.y + 300 / before.scale };
    navigation.actualSize(false);
    const after = navigation.getView();
    expect(after.scale).toBe(1);
    expect(after.x + 500).toBeCloseTo(centre.x, 1);
    expect(after.y + 300).toBeCloseTo(centre.y, 1);
  });

  it("the wheel zooms around the pointer and stops at the limits", () => {
    const { navigation, host } = open();
    navigation.setView({ x: 0, y: 0, scale: 1 });
    (host.querySelector("svg") as SVGElement).dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    const wheel = (deltaY: number) => host.querySelector(".djs-container")!.dispatchEvent(new WheelEvent("wheel", { deltaY, clientX: 0, clientY: 0, bubbles: true, cancelable: true }));
    wheel(-100);
    expect(navigation.getView().scale).toBeGreaterThan(1);
    for (let i = 0; i < 200; i++) wheel(-240);
    expect(navigation.getView().scale).toBeCloseTo(4, 2);
    for (let i = 0; i < 400; i++) wheel(240);
    expect(navigation.getView().scale).toBeCloseTo(0.1, 2);
  });
});

describe("GraphKeys on a diagram", () => {
  it("+ - 0 and F act when the drawing has focus", () => {
    const { navigation, svg } = open();
    press(svg, "+");
    const zoomed = navigation.getView().scale;
    expect(zoomed).toBeGreaterThan(1);
    press(svg, "-");
    press(svg, "-");
    expect(navigation.getView().scale).toBeLessThan(1);
    press(svg, "0");
    expect(navigation.getView().scale).toBe(1);
    navigation.setView({ x: 5000, y: 5000, scale: 1 });
    press(svg, "f");
    expect(navigation.getView().x).toBeLessThan(1000);
  });

  it("does nothing for keys typed in a text field that sits in the drawing's container", () => {
    const { navigation, svg } = open();
    const input = document.createElement("input");
    svg.append(input);
    press(svg, "+", {}, input);
    expect(navigation.getView().scale).toBe(1);
  });

  it("arrows pan with nothing selected and move the selected node otherwise", () => {
    const { navigation, svg, registry, diagram } = open();
    const before = navigation.getView();
    press(svg, "ArrowRight");
    expect(navigation.getView().x).toBeCloseTo(before.x + 50, 1);
    const node = registry.get("a");
    (diagram.get("selection") as { select(element: unknown): void }).select(node);
    const x = node.x;
    press(svg, "ArrowRight");
    expect(node.x).toBe(x + 10);
    expect(navigation.getView().x).toBeCloseTo(before.x + 50, 1);
    press(svg, "ArrowDown", { shiftKey: true });
    expect(node.y).toBe(40 + 50);
  });

  it("arrows do not move nodes of a read-only canvas, they pan", () => {
    const { navigation, svg, registry, diagram, importer } = open();
    importer.update(graph(), true);
    (diagram.get("selection") as { select(element: unknown): void }).select(registry.get("a"));
    const x = registry.get("a").x;
    press(svg, "ArrowRight");
    expect(registry.get("a").x).toBe(x);
    expect(navigation.getView().x).not.toBe(0);
  });

  it("space + drag pans while Space is held, and not otherwise; a press on a node then does not select it", () => {
    const { navigation, svg, host, registry } = open();
    navigation.setView({ x: 0, y: 0, scale: 1 });
    const container = host.querySelector(".djs-container")!;
    const drag = (to: { x: number; y: number }) => {
      container.dispatchEvent(new MouseEvent("mousedown", { button: 0, clientX: 100, clientY: 100, bubbles: true, cancelable: true }));
      document.dispatchEvent(new MouseEvent("mousemove", { clientX: to.x, clientY: to.y, bubbles: true, cancelable: true }));
      document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    };
    drag({ x: 160, y: 130 });
    expect(navigation.getView().x).toBe(0);
    press(svg, " ");
    expect(container instanceof HTMLElement && container.style.cursor).toBe("grab");
    drag({ x: 160, y: 130 });
    expect(navigation.getView()).toMatchObject({ x: -60, y: -30, scale: 1 });
    svg.dispatchEvent(new KeyboardEvent("keyup", { key: " ", bubbles: true }));
    expect((container as HTMLElement).style.cursor).toBe("");
    drag({ x: 200, y: 200 });
    expect(navigation.getView().x).toBe(-60);
    expect(registry.get("a")).toBeTruthy();
  });

  it("a later ticket can register a key through the keymap", () => {
    const { keys, svg } = open();
    let pressed = 0;
    keys.keymap.register({ id: "test.c", keys: ["c"], run: () => { pressed++; } });
    press(svg, "c");
    expect(pressed).toBe(1);
  });
});
