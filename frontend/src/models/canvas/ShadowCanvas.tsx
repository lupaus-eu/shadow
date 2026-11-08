import Diagram from "diagram-js";
import { useEffect, useImperativeHandle, useRef, type Ref } from "react";

import { shadowGraphModule } from "./diagram";
import type { GraphImporter } from "./diagram/GraphImporter";
import type { GraphModeling } from "./diagram/GraphModeling";
import { isConnectionElement, isNodeElement, type GraphElement } from "./diagram/model";
import type { GraphData, GraphEdit, GraphEditSender } from "./graph-types";

export type CanvasTarget = { id: string; kind: "node" | "connection" | "root" };

/** What a parent can ask of the canvas. Later tickets add zoom, fit, centring and export here. */
export type ShadowCanvasHandle = {
  /** Runs an edit on the canvas at once and sends it; rejects when refused (the change is then undone). */
  applyEdit(edit: GraphEdit): Promise<void>;
};

type Props = {
  graph: GraphData | null;
  readOnly: boolean;
  /** The selected node or connection, or null. The canvas follows it and reports changes through `onSelect`. */
  selectedId: string | null;
  onSelect(id: string | null): void;
  /** A click (or Enter or Space) on an element or the background. Return true to handle it yourself; the canvas then does not select. */
  onElementClick?(target: CanvasTarget): boolean;
  /** Writes an edit to the server; reject to have the optimistic change reverted. */
  send: GraphEditSender;
  /** True while a connection is being started: the pointer becomes a crosshair. */
  connecting?: boolean;
  label: string;
  ref?: Ref<ShadowCanvasHandle>;
};

type Services = { importer: GraphImporter; modeling: GraphModeling };

const kindOf = (element: GraphElement | undefined): CanvasTarget["kind"] => (isNodeElement(element) ? "node" : isConnectionElement(element) ? "connection" : "root");

/**
 * One diagram-js `Diagram` for the lifetime of the component. React draws nothing inside it: it hands the plain graph to the importer,
 * which updates shapes in place, and the diagram reports selection and edits back through the props. The container is observed so the
 * diagram follows the size the page gives it.
 */
export function ShadowCanvas({ graph, readOnly, selectedId, onSelect, onElementClick, send, connecting = false, label, ref }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const diagram = useRef<Diagram | null>(null);
  const services = useRef<Services | null>(null);
  const props = useRef({ onSelect, onElementClick, send, selectedId });
  props.current = { onSelect, onElementClick, send, selectedId };

  useImperativeHandle(ref, () => ({ applyEdit: (edit) => (services.current ? services.current.modeling.applyEdit(edit) : Promise.reject(new Error("canvas not ready"))) }), []);

  // Create the diagram once and destroy it with the component.
  useEffect(() => {
    const host = container.current;
    if (!host) return;
    const created = new Diagram({ canvas: { container: host }, modules: [shadowGraphModule] });
    diagram.current = created;
    const get = <T,>(name: string) => created.get(name) as T;
    const modeling = get<GraphModeling>("graphModeling");
    services.current = { importer: get<GraphImporter>("graphImporter"), modeling };
    modeling.setSender((edit) => props.current.send(edit));
    const eventBus = get<{ on(event: string, priority: number, handler: (event: never) => unknown): void; off(event: string, handler: unknown): void }>("eventBus");
    const selection = get<{ get(): GraphElement[]; select(element: GraphElement | null): void }>("selection");
    const registry = get<{ get(id: string): GraphElement | undefined }>("elementRegistry");
    const canvas = get<{ resized(): void }>("canvas");

    // Clicks reach the parent first; when it handles one (connect mode) the diagram's own selection does not run.
    const activate = (element: GraphElement | undefined) => props.current.onElementClick?.({ id: element?.id ?? "", kind: kindOf(element) }) === true;
    // Clicking the one selected element again keeps it selected (the library would toggle it off); the background still clears.
    const onClick = ((event: { element: GraphElement; originalEvent?: MouseEvent }) => {
      if (activate(event.element)) return false;
      const modified = !!event.originalEvent && (event.originalEvent.shiftKey || event.originalEvent.ctrlKey || event.originalEvent.metaKey);
      const selected = selection.get();
      if (!modified && event.element?.parent && selected.length === 1 && selected[0] === event.element) return false;
      return undefined;
    }) as (event: never) => unknown;
    eventBus.on("element.click", 1500, onClick as never);
    const onSelection = ((event: { newSelection: GraphElement[] }) => props.current.onSelect(event.newSelection[0]?.id ?? null)) as (event: never) => unknown;
    eventBus.on("selection.changed", 1000, onSelection as never);

    // Nodes are buttons for the keyboard: Enter and Space act like a click.
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const id = (event.target as Element | null)?.closest?.("[data-element-id]")?.getAttribute("data-element-id");
      const element = id ? registry.get(id) : undefined;
      if (!element || !isNodeElement(element)) return;
      event.preventDefault();
      if (!activate(element)) selection.select(element);
    };
    host.addEventListener("keydown", onKey);

    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => canvas.resized());
    observer?.observe(host);
    return () => {
      observer?.disconnect();
      host.removeEventListener("keydown", onKey);
      // Moves still waiting for their quiet time are saved when the canvas closes.
      void modeling.flush();
      modeling.setSender(null);
      created.destroy();
      diagram.current = null;
      services.current = null;
    };
  }, []);

  // Hand every new graph to the importer; it diffs against what is drawn.
  useEffect(() => {
    if (!graph || !services.current || !diagram.current) return;
    services.current.importer.update(graph, readOnly);
    // The session's undo history belongs to one loaded graph; after a load its entries may point at replaced elements.
    (diagram.current.get("commandStack") as { clear(): void }).clear();
  }, [graph, readOnly]);

  // Follow the parent's selection.
  useEffect(() => {
    const created = diagram.current;
    if (!created) return;
    const selection = created.get("selection") as { get(): GraphElement[]; select(element: GraphElement | null): void };
    const registry = created.get("elementRegistry") as { get(id: string): GraphElement | undefined };
    const wanted = selectedId ? registry.get(selectedId) : undefined;
    const current = selection.get()[0];
    if ((current?.id ?? null) === (wanted?.id ?? null)) return;
    selection.select(wanted ?? null);
  }, [selectedId, graph]);

  return <div ref={container} role="group" aria-label={label} data-connecting={connecting || undefined} className="shadow-canvas h-full w-full" />;
}
