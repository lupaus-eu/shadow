import Diagram from "diagram-js";

import { shadowGraphModule } from "../../src/models/canvas/diagram/index.ts";
import type { GraphData } from "../../src/models/canvas/graph-types.ts";
import type { GraphEdit } from "../../src/models/canvas/graph-types.ts";
import type { GraphImporter } from "../../src/models/canvas/diagram/GraphImporter.ts";
import type { GraphModeling } from "../../src/models/canvas/diagram/GraphModeling.ts";
import type { GraphRules } from "../../src/models/canvas/diagram/GraphRules.ts";

export const nodeType = (id: string, shape = "rectangle", color = "#cfe3ff") => ({ id, key: id, name: `Type ${id}`, color, shape, version: 1 });
export const connectionType = (id: string, style = "solid", source_end = "none", target_end = "arrow") => ({ id, key: id, name: `Link ${id}`, style, source_end, target_end, version: 1 });
export const node = (id: string, node_type_id = "t1", x = 0, y = 0, name = `Node ${id}`) => ({ id, node_type_id, name, description: null, x, y });
export const connection = (id: string, source_node_id: string, target_node_id: string, connection_type_id = "c1") => ({ id, connection_type_id, source_node_id, target_node_id });

export function graph(overrides: Partial<GraphData> = {}): GraphData {
  return {
    nodes: [node("a", "t1", 40, 40), node("b", "t1", 300, 40)],
    connections: [connection("ab", "a", "b")],
    nodeTypes: [nodeType("t1")],
    connectionTypes: [connectionType("c1")],
    allowedConnections: [{ connection_type_id: "c1", source_node_type_id: "t1", target_node_type_id: "t1" }],
    markers: { added: [], updated: [], removed: [] },
    ...overrides,
  };
}

export function createDiagram() {
  const host = document.createElement("div");
  document.body.append(host);
  const diagram = new Diagram({ canvas: { container: host }, modules: [shadowGraphModule] });
  const get = <T,>(name: string) => diagram.get(name) as T;
  return {
    diagram,
    host,
    importer: get<GraphImporter>("graphImporter"),
    modeling: get<GraphModeling>("graphModeling"),
    rules: get<GraphRules>("graphRules"),
    registry: get<{ get(id: string): any; filter(fn: (element: any) => boolean): any[] }>("elementRegistry"),
    commandStack: get<{ canUndo(): boolean; undo(): void; clear(): void }>("commandStack"),
    canvas: get<{ hasMarker(element: unknown, name: string): boolean }>("canvas"),
    modelingService: get<{ moveElements(shapes: unknown[], delta: { x: number; y: number }): void }>("modeling"),
    destroy: () => { diagram.destroy(); host.remove(); },
  };
}

export type { GraphEdit };
