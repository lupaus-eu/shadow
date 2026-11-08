import { useCallback, useEffect, useRef, useState } from "react";

import { loadLineState, type LineChange, type LineState } from "../client";
import { noMarkers, type GraphData } from "./graph-types";

/**
 * Where the graph comes from. Today a line and, optionally, one of its changes (without one, the line's last change, the one edits go
 * into). This is the only place that knows about lines and changes; the canvas gets plain `GraphData`.
 */
export type GraphSource = { organizationId: string; modelId: string; lineId: string; changeId?: string | null };
export type GraphStatus = "loading" | "ready" | "failed";
export type LoadedGraph = { graph: GraphData; change: LineChange | null };
export type GraphLoader = (source: GraphSource, signal: AbortSignal) => Promise<LoadedGraph>;

/** Maps the state route's answer to plain graph data. */
export function toGraphData(state: LineState): LoadedGraph {
  return {
    change: state.change,
    graph: {
      nodes: state.nodes,
      connections: state.connections,
      nodeTypes: state.node_types,
      connectionTypes: state.connection_types,
      allowedConnections: state.allowed_connections,
      markers: state.marks ?? noMarkers,
      ghosts: state.ghosts,
    },
  };
}

export const loadGraphData: GraphLoader = async (source, signal) => toGraphData(await loadLineState(source.organizationId, source.modelId, source.lineId, source.changeId ?? null, signal));

type State = { key: string; graph: GraphData | null; change: LineChange | null; status: GraphStatus; error: unknown };

/**
 * The graph the selected line shows, as plain data, with the change markers of the shown change, the change itself (what an edit changes),
 * a status and `reload` (which resolves with the loaded graph, or null when it failed or was superseded). A new source resets to "loading" with no graph; a reload keeps the old graph on screen until the new one arrives,
 * and a late answer for an older request is dropped. A failed reload keeps the last graph and reports `failed`.
 */
export function useGraphState(source: GraphSource, load: GraphLoader = loadGraphData) {
  const key = `${source.organizationId}|${source.modelId}|${source.lineId}|${source.changeId ?? ""}`;
  const [state, setState] = useState<State>({ key, graph: null, change: null, status: "loading", error: null });
  const latest = useRef(0);
  const sourceRef = useRef(source);
  sourceRef.current = source;
  const controller = useRef<AbortController | null>(null);

  const reload = useCallback(async (): Promise<LoadedGraph | null> => {
    const request = ++latest.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    try {
      const loaded = await load(sourceRef.current, abort.signal);
      if (request !== latest.current) return null;
      setState({ key, graph: loaded.graph, change: loaded.change, status: "ready", error: null });
      return loaded;
    } catch (error) {
      if (request !== latest.current) return null;
      setState((old) => ({ ...old, key, status: "failed", error }));
      return null;
    }
  }, [key, load]);

  useEffect(() => {
    setState((old) => (old.key === key ? old : { key, graph: null, change: null, status: "loading", error: null }));
    void reload();
    return () => { latest.current++; controller.current?.abort(); };
  }, [key, reload]);

  // Until the effect has run for a new source, never show the old source's graph.
  const current = state.key === key;
  return { graph: current ? state.graph : null, change: current ? state.change : null, status: current ? state.status : ("loading" as GraphStatus), error: current ? state.error : null, reload };
}
