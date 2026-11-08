import { useCallback, useEffect, useRef, useState } from "react";

import { loadMetrics, loadSeries, type Metric, type SeriesPoint } from "./client";
import { latestPoint, metricsOfNode, type NodeMetric } from "./canvas/node-metrics";

export type NodeMetricsState = { status: "idle" | "loading" | "ready" | "failed"; items: NodeMetric[]; retry(): void };
export type MetricsLoaders = {
  list(line: LineKey): Promise<Metric[]>;
  series(line: LineKey, metricId: string): Promise<SeriesPoint[]>;
};
export type LineKey = { organizationId: string; modelId: string; lineId: string };

const serverLoaders: MetricsLoaders = {
  list: (line) => loadMetrics(line.organizationId, line.modelId, line.lineId),
  series: async (line, metricId) => (await loadSeries(line.organizationId, line.modelId, line.lineId, metricId)).points,
};

/** What was read for one line: the metric list, and the latest value of each metric once it has been asked for. Lives as long as the canvas page. */
export type MetricsCache = Map<string, { list: Promise<Metric[]>; latest: Map<string, Promise<SeriesPoint | null>> }>;

/**
 * The metrics attached to the selected node, with each one's latest value. Nothing is read until a node is selected; the metric list is read
 * once per line and the series of a metric once, both kept while the canvas page is open (a trip to the Metrics tab, which edits them,
 * starts a fresh cache). A failed read is not cached, so `retry` asks again. A late answer for an older selection is dropped.
 */
export function useNodeMetrics(line: LineKey, nodeId: string | null, loaders: MetricsLoaders = serverLoaders): NodeMetricsState {
  const cache = useRef<MetricsCache>(new Map());
  const key = `${line.organizationId}|${line.modelId}|${line.lineId}`;
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ key: string; status: NodeMetricsState["status"]; items: NodeMetric[] }>({ key: "", status: "idle", items: [] });
  const loadersRef = useRef(loaders);
  loadersRef.current = loaders;

  useEffect(() => {
    if (!nodeId) { setState({ key: "", status: "idle", items: [] }); return; }
    let current = true;
    const wanted = `${key}|${nodeId}`;
    setState((old) => (old.key === wanted && old.status === "ready" ? old : { key: wanted, status: "loading", items: [] }));
    const read = loadersRef.current;
    let entry = cache.current.get(key);
    if (!entry) { entry = { list: read.list(line), latest: new Map() }; cache.current.set(key, entry); }
    const forget = () => { if (cache.current.get(key) === entry) cache.current.delete(key); };
    const own = entry;
    void (async () => {
      try {
        const metrics = metricsOfNode(await own.list, nodeId);
        const items = await Promise.all(metrics.map(async (metric): Promise<NodeMetric> => {
          let latest = own.latest.get(metric.id);
          if (!latest) { latest = read.series(line, metric.id).then(latestPoint); own.latest.set(metric.id, latest); }
          try { return { metric, latest: await latest }; } catch (cause) { own.latest.delete(metric.id); throw cause; }
        }));
        if (current) setState({ key: wanted, status: "ready", items });
      } catch {
        forget();
        if (current) setState({ key: wanted, status: "failed", items: [] });
      }
    })();
    return () => { current = false; };
    // `line` is rebuilt every render; its parts are in `key`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nodeId, attempt]);

  const retry = useCallback(() => setAttempt((count) => count + 1), []);
  const valid = !!nodeId && state.key === `${key}|${nodeId}`;
  return { status: nodeId ? (valid ? state.status : "loading") : "idle", items: valid ? state.items : [], retry };
}
