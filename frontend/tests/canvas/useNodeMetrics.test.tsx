import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Metric, SeriesPoint } from "../../src/models/client.ts";
import { useNodeMetrics, type LineKey, type MetricsLoaders } from "../../src/models/useNodeMetrics.ts";

type Hook = ReturnType<typeof useNodeMetrics>;
let root: Root | null = null;
afterEach(() => { act(() => root?.unmount()); root = null; });

const metric = (id: string, name: string, node_id: string | null): Metric => ({ id, key: id, name, unit: "EUR", node_id, formula: null, derived: false, version: 1, values: 2 });
const line = (lineId = "l1"): LineKey => ({ organizationId: "o", modelId: "m", lineId });
const points: SeriesPoint[] = [{ period: "2026-01-01", value: 1 }, { period: "2026-02-01", value: 20 }, { period: "2026-03-01", value: null }];

function mount(loaders: MetricsLoaders) {
  const result: { current: Hook } = { current: undefined as unknown as Hook };
  const host = document.createElement("div");
  root = createRoot(host);
  // One component for the whole test, so its cache survives a change of the selection like it does on the page.
  let args: [LineKey, string | null] = [line(), null];
  function Probe() { result.current = useNodeMetrics(args[0], args[1], loaders); return null; }
  const render = (key: LineKey, nodeId: string | null) => {
    args = [key, nodeId];
    act(() => root!.render(createElement(Probe)));
  };
  return { result, render };
}
const settle = () => act(async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); });

describe("useNodeMetrics", () => {
  it("reads nothing until a node is selected", async () => {
    const loaders = { list: vi.fn(async () => []), series: vi.fn(async () => points) };
    const { result, render } = mount(loaders);
    render(line(), null);
    await settle();
    expect(result.current.status).toBe("idle");
    expect(loaders.list).not.toHaveBeenCalled();
  });

  it("returns the node's metrics with their latest value", async () => {
    const loaders = { list: vi.fn(async () => [metric("m1", "Revenue", "n1"), metric("m2", "Cost", "n2")]), series: vi.fn(async () => points) };
    const { result, render } = mount(loaders);
    render(line(), "n1");
    expect(result.current.status).toBe("loading");
    await settle();
    expect(result.current.status).toBe("ready");
    expect(result.current.items.map((item) => [item.metric.name, item.latest])).toEqual([["Revenue", { period: "2026-02-01", value: 20 }]]);
    // Only the selected node's series was read.
    expect(loaders.series).toHaveBeenCalledTimes(1);
  });

  it("is ready with no items for a node without metrics", async () => {
    const { result, render } = mount({ list: async () => [metric("m1", "Revenue", "n1")], series: async () => points });
    render(line(), "n9");
    await settle();
    expect(result.current).toMatchObject({ status: "ready", items: [] });
  });

  it("reads the list once per line and each series once", async () => {
    const loaders = { list: vi.fn(async () => [metric("m1", "Revenue", "n1"), metric("m2", "Cost", "n2")]), series: vi.fn(async () => points) };
    const { result, render } = mount(loaders);
    render(line(), "n1");
    await settle();
    render(line(), "n2");
    await settle();
    render(line(), "n1");
    await settle();
    expect(result.current.status).toBe("ready");
    expect(loaders.list).toHaveBeenCalledTimes(1);
    expect(loaders.series).toHaveBeenCalledTimes(2);
    render(line("l2"), "n1");
    await settle();
    expect(loaders.list).toHaveBeenCalledTimes(2);
  });

  it("reports a failed read, does not cache it, and reads again on retry", async () => {
    let fail = true;
    const loaders = { list: vi.fn(async () => { if (fail) throw new Error("down"); return [metric("m1", "Revenue", "n1")]; }), series: vi.fn(async () => points) };
    const { result, render } = mount(loaders);
    render(line(), "n1");
    await settle();
    expect(result.current.status).toBe("failed");
    fail = false;
    act(() => result.current.retry());
    await settle();
    expect(result.current.status).toBe("ready");
    expect(result.current.items).toHaveLength(1);
    expect(loaders.list).toHaveBeenCalledTimes(2);
  });

  it("fails when a series cannot be read", async () => {
    const { result, render } = mount({ list: async () => [metric("m1", "Revenue", "n1")], series: async () => { throw new Error("down"); } });
    render(line(), "n1");
    await settle();
    expect(result.current.status).toBe("failed");
  });

  it("drops a late answer for a node that is no longer selected", async () => {
    let release: (value: Metric[]) => void = () => undefined;
    const list = vi.fn(() => new Promise<Metric[]>((resolve) => { release = resolve; }));
    const { result, render } = mount({ list, series: async () => points });
    render(line(), "n1");
    render(line(), "n2");
    await act(async () => { release([metric("m1", "Revenue", "n1"), metric("m2", "Cost", "n2")]); });
    await settle();
    expect(result.current.items.map((item) => item.metric.name)).toEqual(["Cost"]);
  });
});
