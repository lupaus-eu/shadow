import { describe, expect, it } from "vitest";

import { modelMessages } from "../../src/models/messages.ts";
import { timelineMessages } from "../../src/models/timeline-messages.ts";
import { nextAnnouncement, nodeConnectionRows, selectionAnnouncement } from "../../src/models/canvas/a11y.ts";
import type { GraphData } from "../../src/models/canvas/graph-types.ts";

// Every label, message and shortcut hint of the model pages and the canvas exists in Finnish and English, is not empty, and is not the
// English text copied into the Finnish file. Functions are called with sample arguments.
const SAMPLE = ["Alpha", "Beta", "Gamma", "2026-01-01"];
// Words that are the same in both languages on purpose.
const SAME = new Set(["Node", "node", "Nodes", "PNG", "SVG", "Export as SVG", "Export as PNG", "Min", "Max", "Mallit"]);

function flatten(value: unknown, path: string, out: Map<string, string>) {
  if (typeof value === "string") out.set(path, value);
  else if (typeof value === "function") {
    const call = value as (...args: unknown[]) => unknown;
    let result: unknown;
    try { result = call(...SAMPLE); } catch { result = call(SAMPLE.slice(0, 2), SAMPLE.slice(2)); }
    if (typeof result === "string") out.set(path, result);
    else flatten(result, `${path}()`, out);
  } else if (Array.isArray(value)) value.forEach((item, index) => flatten(item, `${path}[${index}]`, out));
  else if (value && typeof value === "object") for (const [key, item] of Object.entries(value)) flatten(item, path ? `${path}.${key}` : key, out);
}
const read = (source: (locale: "fi" | "en") => unknown) => {
  const fi = new Map<string, string>(); const en = new Map<string, string>();
  flatten(source("fi"), "", fi); flatten(source("en"), "", en);
  return { fi, en };
};

describe.each([["model and canvas messages", modelMessages], ["timeline messages", timelineMessages]] as const)("%s", (_name, source) => {
  const { fi, en } = read(source as (locale: "fi" | "en") => unknown);
  it("has the same keys in Finnish and English", () => {
    expect([...fi.keys()].sort()).toEqual([...en.keys()].sort());
  });
  it("has no empty text", () => {
    const empty = [...fi, ...en].filter(([, text]) => text.trim() === "").map(([key]) => key);
    expect(empty).toEqual([]);
  });
  it("has no Finnish text that is just the English text", () => {
    const same = [...fi].filter(([key, text]) => en.get(key) === text && text.length > 3 && !SAME.has(text)).map(([key, text]) => `${key}: ${text}`);
    expect(same).toEqual([]);
  });
});

const graph: GraphData = {
  nodes: [{ id: "a", node_type_id: "t", name: "Sales", description: null, x: 0, y: 0 }, { id: "b", node_type_id: "t", name: "Support", description: null, x: 0, y: 0 }],
  connections: [{ id: "k", connection_type_id: "c", source_node_id: "a", target_node_id: "b" }],
  nodeTypes: [{ id: "t", key: "unit", name: "Unit", color: "#fff", shape: "rectangle", version: 1 }],
  connectionTypes: [{ id: "c", key: "reports", name: "Reports to", style: "solid", source_end: "none", target_end: "arrow", version: 1 }],
  allowedConnections: [],
  markers: { added: [], updated: [], removed: [] },
} as unknown as GraphData;

describe("live region and text alternative helpers", () => {
  it("alternates the text so a repeated sentence is announced again, and says nothing for nothing", () => {
    expect(nextAnnouncement("", "Done")).toBe("Done");
    expect(nextAnnouncement("Done", "Done")).toBe("Done ");
    expect(nextAnnouncement("Done ", "Done")).toBe("Done");
    expect(nextAnnouncement("Done", "")).toBe("");
  });
  const en = modelMessages("en");
  it("says name and type of a node, the ends of a connection, a count, and nothing for an empty selection", () => {
    expect(selectionAnnouncement(graph, ["a"], en)).toBe("Selected Sales, Unit.");
    expect(selectionAnnouncement(graph, ["k"], en)).toBe("Selected the connection Reports to from Sales to Support.");
    expect(selectionAnnouncement(graph, ["a", "b"], en)).toBe("2 elements selected.");
    expect(selectionAnnouncement(graph, [], en)).toBe("");
  });
  it("lists the connections of a node with direction, type and the other node, in both languages", () => {
    expect(nodeConnectionRows(graph, "a", en)).toEqual([{ id: "k", label: "outgoing Reports to: Support" }]);
    expect(nodeConnectionRows(graph, "b", modelMessages("fi"))).toEqual([{ id: "k", label: "tuleva Reports to: Sales" }]);
    expect(nodeConnectionRows(graph, "none", en)).toEqual([]);
  });
});
