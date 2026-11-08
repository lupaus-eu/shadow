import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { toGraphData, useGraphState, type GraphLoader, type GraphSource, type LoadedGraph } from "../../src/models/canvas/useGraphState.ts";
import type { LineState } from "../../src/models/client.ts";
import { graph } from "./helpers.ts";

type Hook = ReturnType<typeof useGraphState>;
let root: Root | null = null;
afterEach(() => { act(() => root?.unmount()); root = null; });

const source = (overrides: Partial<GraphSource> = {}): GraphSource => ({ organizationId: "o", modelId: "m", lineId: "l", ...overrides });
const loaded = (name = "first"): LoadedGraph => ({ graph: { ...graph(), nodes: [{ id: "n", node_type_id: "t1", name, description: null, x: 1, y: 2 }] }, change: null });

function mount(initial: GraphSource, load: GraphLoader) {
  const result: { current: Hook } = { current: undefined as unknown as Hook };
  const host = document.createElement("div");
  root = createRoot(host);
  const render = (value: GraphSource) => {
    function Probe() { result.current = useGraphState(value, load); return null; }
    act(() => root!.render(createElement(Probe)));
  };
  render(initial);
  return { result, render };
}

const settle = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });

describe("useGraphState", () => {
  it("starts loading, then returns plain graph data", async () => {
    const load = vi.fn<GraphLoader>(async () => loaded());
    const { result } = mount(source(), load);
    expect(result.current.status).toBe("loading");
    expect(result.current.graph).toBeNull();
    await settle();
    expect(result.current.status).toBe("ready");
    expect(result.current.graph?.nodes[0].name).toBe("first");
    expect(load.mock.calls[0][0]).toEqual(source());
  });

  it("reports a failed load and keeps the last graph on a failed reload", async () => {
    let fail = false;
    const load: GraphLoader = async () => { if (fail) throw new Error("down"); return loaded(); };
    const { result } = mount(source(), load);
    await settle();
    fail = true;
    await act(async () => { await result.current.reload(); });
    expect(result.current.status).toBe("failed");
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.graph?.nodes[0].name).toBe("first");
  });

  it("reload loads again, keeps the old graph until the answer arrives, and resolves with what it loaded", async () => {
    let name = "first";
    let release!: () => void;
    let gate = Promise.resolve();
    const load: GraphLoader = async () => { await gate; return loaded(name); };
    const { result } = mount(source(), load);
    await settle();
    name = "second";
    gate = new Promise<void>((resolve) => { release = resolve; });
    let promise!: Promise<LoadedGraph | null>;
    act(() => { promise = result.current.reload(); });
    expect(result.current.graph?.nodes[0].name).toBe("first");
    expect(result.current.status).toBe("ready");
    release();
    let value: LoadedGraph | null = null;
    await act(async () => { value = await promise; });
    expect(value).not.toBeNull();
    expect(result.current.graph?.nodes[0].name).toBe("second");
  });

  it("drops an older answer that arrives after a newer one", async () => {
    const releases: (() => void)[] = [];
    let call = 0;
    const load: GraphLoader = async () => {
      const mine = ++call;
      if (mine > 1) await new Promise<void>((resolve) => releases.push(resolve));
      return loaded(mine === 1 ? "initial" : mine === 2 ? "stale" : "fresh");
    };
    const { result } = mount(source(), load);
    await settle();
    act(() => { void result.current.reload(); });
    act(() => { void result.current.reload(); });
    await act(async () => { releases[1](); await Promise.resolve(); });
    await act(async () => { releases[0](); await Promise.resolve(); });
    expect(result.current.graph?.nodes[0].name).toBe("fresh");
  });

  it("starts over without the old graph when the line or the change changes", async () => {
    const load: GraphLoader = async (value) => loaded(`${value.lineId}/${value.changeId ?? "last"}`);
    const { result, render } = mount(source({ lineId: "l1" }), load);
    await settle();
    expect(result.current.graph?.nodes[0].name).toBe("l1/last");
    render(source({ lineId: "l1", changeId: "e2" }));
    expect(result.current.graph).toBeNull();
    expect(result.current.status).toBe("loading");
    await settle();
    expect(result.current.graph?.nodes[0].name).toBe("l1/e2");
    render(source({ lineId: "l2" }));
    expect(result.current.graph).toBeNull();
    await settle();
    expect(result.current.graph?.nodes[0].name).toBe("l2/last");
  });

  it("returns the change the graph is shown after", async () => {
    const change = { id: "e", line_id: "l", occurred_on: "2026-01-01", title: "Start", version: 3, planned: false, edit_count: 1 };
    const { result } = mount(source(), async () => ({ ...loaded(), change }));
    await settle();
    expect(result.current.change).toEqual(change);
  });
});

describe("toGraphData", () => {
  it("maps the state route's answer, with the change markers", () => {
    const state: LineState = {
      change: null,
      node_types: [{ id: "t", key: "t", name: "T", color: "#fff", shape: "ellipse", version: 1 }],
      connection_types: [{ id: "c", key: "c", name: "C", style: "dashed", source_end: "none", target_end: "arrow", version: 1 }],
      allowed_connections: [{ connection_type_id: "c", source_node_type_id: "t", target_node_type_id: "t" }],
      nodes: [{ id: "n", node_type_id: "t", name: "N", description: null, x: 0, y: 0 }],
      connections: [],
      marks: { added: ["n"], updated: [], removed: ["gone"] },
    };
    const { graph: data } = toGraphData(state);
    expect(data.nodeTypes[0].shape).toBe("ellipse");
    expect(data.connectionTypes[0].style).toBe("dashed");
    expect(data.allowedConnections).toHaveLength(1);
    expect(data.markers).toEqual({ added: ["n"], updated: [], removed: ["gone"] });
  });
});
