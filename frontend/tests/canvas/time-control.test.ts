import { afterEach, describe, expect, it } from "vitest";

import { canvasWritable, markCounts, shouldClearHistory, sourceEventId } from "../../src/models/canvas/edit-target";
import { ghostSummary } from "../../src/models/canvas/ghosts";
import { toGraphData } from "../../src/models/canvas/useGraphState";
import { ChainBrokenError, ForbiddenError, RuleError, StaleVersionError } from "../../src/models/client";
import { refusalMessage } from "../../src/models/timeline/refusals";
import { connection, createDiagram, graph, node } from "./helpers.ts";

let current: ReturnType<typeof createDiagram>;
afterEach(() => current?.destroy());

describe("edit target", () => {
  it("asks the loader for the shown event unless it is the last one", () => {
    expect(sourceEventId(true, { id: "e2" })).toBeNull();
    expect(sourceEventId(false, { id: "e1" })).toBe("e1");
    expect(sourceEventId(false, null)).toBeNull();
  });
  it("is writable for any shown event; only the subscription and the role decide", () => {
    expect(canvasWritable({ subscriptionWritable: true, canWriteLine: true })).toBe(true);
    expect(canvasWritable({ subscriptionWritable: false, canWriteLine: true })).toBe(false);
    expect(canvasWritable({ subscriptionWritable: true, canWriteLine: false })).toBe(false);
  });
  it("clears the undo history when the shown event changes, not on the first event or the same one", () => {
    expect(shouldClearHistory("e1", "e2")).toBe(true);
    expect(shouldClearHistory("e1", "e1")).toBe(false);
    expect(shouldClearHistory(null, "e1")).toBe(false);
    expect(shouldClearHistory("e1", null)).toBe(false);
  });
});

describe("change marks", () => {
  it("counts what the shown event added, changed and removed", () => {
    expect(markCounts({ added: ["a", "b"], updated: ["c"], removed: [] })).toEqual({ added: 2, updated: 1, removed: 0, any: true });
    expect(markCounts({ added: [], updated: [], removed: [] }).any).toBe(false);
  });
  it("maps the state answer's removed list to ghosts with their data", () => {
    const gone = { id: "x", node_type_id: "t1", name: "Gone", description: null, x: 5, y: 6 };
    const { graph: data } = toGraphData({ event: null, node_types: [], connection_types: [], allowed_connections: [], nodes: [], connections: [], changes: { added: [], updated: [], removed: ["x"] }, ghosts: { nodes: [gone], connections: [] } });
    expect(data.markers.removed).toEqual(["x"]);
    expect(data.ghosts?.nodes).toEqual([gone]);
    expect(ghostSummary(data).nodes).toEqual(["Gone"]);
  });
  it("draws added and changed elements with + and ~ badges and removed ones as outlines with a - badge, outside the editable elements", () => {
    current = createDiagram();
    const gone = node("z", "t1", 300, 300, "Gone");
    current.importer.update(graph({ markers: { added: ["a"], updated: ["b"], removed: ["z"] }, ghosts: { nodes: [gone], connections: [] } }));
    const badge = (id: string) => current.host.querySelector(`[data-element-id="${id}"] .shadow-change-badge`)?.textContent;
    expect(badge("a")).toBe("+");
    expect(badge("b")).toBe("~");
    expect(current.registry.get("z")).toBeUndefined();
    const ghost = current.host.querySelector("[data-ghost='node']");
    expect(ghost?.textContent).toContain("Gone");
    expect(ghost?.querySelector("[data-change='removed']")?.textContent).toBe("−");
    expect((ghost as SVGElement).style.pointerEvents).toBe("none");
    // The next load without ghosts clears the layer.
    current.importer.update(graph());
    expect(current.host.querySelector("[data-ghost]")).toBeNull();
  });
  it("draws a removed connection between known ends", () => {
    current = createDiagram();
    const gone = node("z", "t1", 300, 300, "Gone");
    const lost = { ...connection("az", "a", "z"), connection_type_id: "c1" };
    current.importer.update(graph({ ghosts: { nodes: [gone], connections: [lost] } }));
    expect(current.host.querySelector("[data-ghost='connection']")).not.toBeNull();
  });
});

describe("refusal messages of a canvas edit", () => {
  const hint = { code: "add_element_before", event_title: "Hire", event_date: "2026-03-01", element_name: "Sales", element_kind: "node" };
  it("names event and element and what to do first for a broken chain", () => {
    const message = refusalMessage(new ChainBrokenError("missing_element", hint), "en");
    expect(message).toContain("Hire");
    expect(message).toContain('"Sales"');
    expect(message).toContain("earlier event first");
  });
  it("explains a stale answer, a branch point and a forbidden write in both languages", () => {
    for (const locale of ["en", "fi"] as const) {
      expect(refusalMessage(new StaleVersionError(), locale).length).toBeGreaterThan(10);
      expect(refusalMessage(new ForbiddenError(), locale).length).toBeGreaterThan(10);
      expect(refusalMessage(new RuleError("branch_point", { reason: "branch_point", line: "Plan B" }), locale)).toContain("Plan B");
    }
  });
});
