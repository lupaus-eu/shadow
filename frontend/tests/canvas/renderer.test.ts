import { afterEach, describe, expect, it } from "vitest";

import { connection, connectionType, createDiagram, graph, node, nodeType } from "./helpers.ts";

let current: ReturnType<typeof createDiagram>;
afterEach(() => current?.destroy());

const visual = (id: string) => current.host.querySelector(`[data-element-id="${id}"]`) as SVGElement;

function draw(overrides: Parameters<typeof graph>[0]) {
  current = createDiagram();
  current.importer.update(graph(overrides));
}

describe("GraphRenderer nodes", () => {
  it.each([
    ["rectangle", "rect", "0"],
    ["roundrectangle", "rect", "8"],
    ["ellipse", "ellipse", null],
    ["diamond", "path", null],
    ["hexagon", "path", null],
    ["triangle", "rect", "8"],
    ["", "rect", "8"],
  ])("draws the node type shape %j as %s", (shape, tag, radius) => {
    draw({ nodeTypes: [nodeType("t1", shape)], connections: [] });
    const body = visual("a").querySelector(".shadow-node-body") as SVGElement;
    expect(body.tagName.toLowerCase()).toBe(tag);
    if (radius !== null) expect(body.getAttribute("rx")).toBe(radius);
    expect(body.getAttribute("data-shape")).toBe(shape === "triangle" || shape === "" ? "roundrectangle" : shape);
  });

  it("fills with the type colour and picks a readable text colour", () => {
    draw({ nodeTypes: [nodeType("t1", "rectangle", "#0b1f3a")], connections: [] });
    expect((visual("a").querySelector(".shadow-node-body") as SVGElement).style.fill).toBe("rgb(11, 31, 58)");
    expect(visual("a").querySelector(".shadow-node-name")?.getAttribute("fill") ?? (visual("a").querySelector(".shadow-node-name") as SVGElement).style.fill).toMatch(/#ffffff|rgb\(255, 255, 255\)|white/);
  });

  it("writes the name, the type name, and a full-name title", () => {
    draw({ nodeTypes: [nodeType("t1")], nodes: [node("a", "t1", 0, 0, "Sales")], connections: [] });
    expect(visual("a").querySelector(".shadow-node-name")?.textContent).toBe("Sales");
    expect(visual("a").querySelector(".shadow-node-type")?.textContent).toBe("Type t1");
    expect(visual("a").querySelector("title")?.textContent).toBe("Sales (Type t1)");
  });

  it("shortens a name over 60 characters in the label and keeps it whole in the title", () => {
    const long = `${"word ".repeat(15)}tail`; // 79 characters
    draw({ nodes: [node("a", "t1", 0, 0, long)], connections: [] });
    const lines = [...visual("a").querySelectorAll(".shadow-node-name")].map((line) => line.textContent ?? "");
    expect(lines.join("").includes("tail")).toBe(false);
    expect(lines.at(-1)?.endsWith("…")).toBe(true);
    expect(visual("a").querySelector("title")?.textContent).toContain("tail");
  });

  it("makes the node a named button for keyboards", () => {
    draw({ connections: [] });
    expect(visual("a").getAttribute("role")).toBe("button");
    expect(visual("a").getAttribute("tabindex")).toBe("0");
    expect(visual("a").getAttribute("aria-label")).toBe("Node a (Type t1)");
  });

  it("falls back to a neutral fill when the node's type is unknown", () => {
    draw({ nodes: [node("a", "gone", 0, 0)], connections: [] });
    expect((visual("a").querySelector(".shadow-node-body") as SVGElement).style.fill).toBe("rgb(221, 221, 221)");
    expect(visual("a").getAttribute("aria-label")).toBe("Node a ()");
  });
});

describe("GraphRenderer connections", () => {
  const line = () => visual("ab").querySelector(".shadow-connection-line") as SVGElement;
  const dash = () => line().style.getPropertyValue("stroke-dasharray") || line().getAttribute("stroke-dasharray") || "";
  const arrows = () => visual("ab").querySelectorAll(".shadow-connection-arrow").length;

  it("draws a solid line with one arrowhead at the target", () => {
    draw({ connectionTypes: [connectionType("c1", "solid", "none", "arrow")] });
    expect(dash()).toBe("");
    expect(arrows()).toBe(1);
  });

  it("draws a dashed line", () => {
    draw({ connectionTypes: [connectionType("c1", "dashed", "none", "none")] });
    expect(dash()).toBe("6 4");
    expect(arrows()).toBe(0);
  });

  it("draws arrowheads at both ends when the type has them", () => {
    draw({ connectionTypes: [connectionType("c1", "solid", "arrow", "arrow")] });
    expect(arrows()).toBe(2);
  });

  it("labels the connection with its type name", () => {
    draw({ connectionTypes: [connectionType("c1")] });
    expect(visual("ab").querySelector(".shadow-connection-label")?.textContent).toBe("Link c1");
  });

  it("runs the line between the shapes' borders, not through their middles", () => {
    draw({ nodes: [node("a", "t1", 0, 0), node("b", "t1", 400, 0)] });
    const [start, end] = current.registry.get("ab").waypoints;
    expect(start.x).toBeCloseTo(160, 0); // right edge of a 160 wide rectangle
    expect(end.x).toBeCloseTo(400, 0);
  });

  it("ends the line on the outline of an ellipse, inside its bounding box", () => {
    draw({ nodeTypes: [nodeType("t1", "ellipse")], nodes: [node("a", "t1", 0, 0), node("b", "t1", 400, 100)], connections: [connection("ab", "a", "b")] });
    const [start] = current.registry.get("ab").waypoints;
    expect(start.x).toBeLessThan(160);
    expect(start.x).toBeGreaterThan(80);
  });
});
