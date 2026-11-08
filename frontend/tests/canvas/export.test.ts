import { afterEach, describe, expect, it } from "vitest";

import { buildExportSvg, exportFileBase, exportFileName, exportStyles, pngScale, resolveTokens, sanitizeNamePart, DEFAULT_TOKENS, EXPORT_PADDING } from "../../src/models/canvas/export.ts";
import type { GraphNavigation } from "../../src/models/canvas/diagram/GraphNavigation.ts";
import { createDiagram, graph, node, nodeType } from "./helpers.ts";

describe("file names", () => {
  it("joins the model and the line, sanitised, with the extension", () => {
    expect(exportFileName("Supply chain", "Base line", "svg")).toBe("Supply-chain-Base-line.svg");
    expect(exportFileName("Toimitusketju", "Skenaario: Kesä 2027", "png")).toBe("Toimitusketju-Skenaario-Kesä-2027.png");
    expect(exportFileBase("Ö/Ä\\Å", "a:b*c?d\"e<f>g|h")).toBe("Ö-Ä-Å-a-b-c-d-e-f-g-h");
  });

  it("drops control characters, leading dots and dashes, and path tricks", () => {
    expect(sanitizeNamePart("..\\..\\etc/passwd")).toBe("etc-passwd");
    expect(sanitizeNamePart("  .hidden  ")).toBe("hidden");
    expect(sanitizeNamePart("a\u0000b\u001fc😀d")).toBe("a-b-c-d");
    expect(sanitizeNamePart("???")).toBe("");
  });

  it("falls back to 'model' when nothing is left, avoids reserved names and caps the length", () => {
    expect(exportFileBase("", "***")).toBe("model");
    expect(exportFileBase("con", "")).toBe("model-con");
    expect(exportFileBase("only the model", "")).toBe("only-the-model");
    expect(Array.from(sanitizeNamePart("x".repeat(300)))).toHaveLength(80);
    expect(exportFileName("x".repeat(300), "y".repeat(300), "png").length).toBeLessThan(170);
  });
});

describe("PNG scale", () => {
  it("is 2 unless the image would be too large for a canvas", () => {
    expect(pngScale(800, 600)).toBe(2);
    expect(pngScale(20000, 600)).toBeCloseTo(0.8, 5);
  });
});

describe("tokens and styles", () => {
  it("resolves the theme colours, keeping the default for anything that is not a colour", () => {
    const tokens = resolveTokens((name) => ({ "--color-ink": "#101010", "--color-accent": "rgb(1, 2, 3)", "--color-surface": "url(javascript:1)" })[name] ?? "");
    expect(tokens).toMatchObject({ ink: "#101010", accent: "rgb(1, 2, 3)", surface: DEFAULT_TOKENS.surface, inkMuted: DEFAULT_TOKENS.inkMuted });
    expect(exportStyles(tokens)).toContain("stroke:rgb(1, 2, 3)");
  });
});

let current: ReturnType<typeof createDiagram> | null = null;
afterEach(() => { current?.destroy(); current = null; });

function open() {
  current = createDiagram();
  current.importer.update(graph({
    nodes: [node("a", "t1", 40, 40, "Alpha"), node("b", "t1", 300, 40, "Beta"), node("h", "t2", 300, 200, "Hidden one")],
    nodeTypes: [nodeType("t1"), nodeType("t2", "ellipse", "#ffd6a5")],
    connections: [{ id: "ab", connection_type_id: "c1", source_node_id: "a", target_node_id: "b" }, { id: "ah", connection_type_id: "c1", source_node_id: "a", target_node_id: "h" }],
    allowedConnections: [{ connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t1" }, { connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t2" }],
  }), false);
  const navigation = current.diagram.get("graphNavigation") as GraphNavigation;
  return { ...current, svg: current.host.querySelector("svg")! as SVGSVGElement, navigation };
}

describe("buildExportSvg", () => {
  it("serialises the whole graph with padding, styles inlined and no viewport transform", () => {
    const { svg, navigation } = open();
    const bounds = navigation.graphBounds()!;
    const exported = buildExportSvg(svg, bounds, { title: "Model - Base line" })!;
    expect(exported.width).toBe(Math.ceil(bounds.width + 2 * EXPORT_PADDING));
    expect(exported.height).toBe(Math.ceil(bounds.height + 2 * EXPORT_PADDING));
    const doc = new DOMParser().parseFromString(exported.svg, "image/svg+xml");
    expect(doc.querySelector("parsererror")).toBeNull();
    const root = doc.documentElement;
    expect(root.getAttribute("viewBox")).toBe(`${Math.floor(bounds.x - EXPORT_PADDING)} ${Math.floor(bounds.y - EXPORT_PADDING)} ${exported.width} ${exported.height}`);
    expect(root.querySelector("title")?.textContent).toBe("Model - Base line");
    expect(root.querySelector("style")?.textContent).toContain(".shadow-connection-line");
    expect(root.querySelector(".viewport")?.hasAttribute("transform")).toBe(false);
    const names = [...root.querySelectorAll(".shadow-node-name, .shadow-node-label")].map((element) => element.textContent);
    expect(names.join(" ")).toContain("Alpha");
    expect(names.join(" ")).toContain("Beta");
  });

  it("leaves a hidden type and its connections out, keeps the rest, and does not change the canvas", () => {
    const { svg, navigation, canvas, registry } = open();
    for (const id of ["h", "ah"]) (canvas as any).addMarker(registry.get(id), "shadow-hidden");
    const before = svg.outerHTML;
    const exported = buildExportSvg(svg, navigation.graphBounds(), { title: "t" })!;
    expect(exported.svg).toContain("Alpha");
    expect(exported.svg).toContain("Beta");
    expect(exported.svg).not.toContain("Hidden one");
    expect(exported.svg).not.toContain('data-element-id="ah"');
    expect(exported.svg).toContain('data-element-id="ab"');
    expect(svg.outerHTML).toBe(before);
    // The bounds follow what is shown: with the hidden node excluded the image is not as tall.
    const withHidden = buildExportSvg(svg, { x: 40, y: 40, width: 420, height: 216 }, { title: "t" })!;
    expect(exported.height).toBeLessThan(withHidden.height);
  });

  it("drops selection, outlines and keyboard attributes", () => {
    const { svg, navigation, selection, registry } = open();
    selection.select([registry.get("a")]);
    expect(svg.querySelector(".selected")).not.toBeNull();
    const exported = buildExportSvg(svg, navigation.graphBounds(), { title: "t" })!;
    expect(exported.svg).not.toMatch(/class="[^"]*\bselected\b/);
    expect(exported.svg).not.toContain("djs-outline");
    expect(exported.svg).not.toContain("tabindex");
  });

  it("returns null when nothing is drawn", () => {
    const { svg } = open();
    expect(buildExportSvg(svg, null, { title: "t" })).toBeNull();
  });
});
