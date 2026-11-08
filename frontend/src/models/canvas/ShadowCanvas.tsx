import Diagram from "diagram-js";
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";

import { CanvasToolbar, type CanvasToolbarTexts } from "./CanvasToolbar";
import { shadowGraphModule } from "./diagram";
import type { GraphImporter } from "./diagram/GraphImporter";
import type { GraphKeys } from "./diagram/GraphKeys";
import type { GraphModeling } from "./diagram/GraphModeling";
import type { GraphNavigation } from "./diagram/GraphNavigation";
import { isConnectionElement, isNodeElement, type GraphElement } from "./diagram/model";
import type { GraphData, GraphEdit, GraphEditSender } from "./graph-types";
import type { KeyBinding } from "./keymap";
import { zoomPercent, type Point, type View, type ViewMemory } from "./view";

export type CanvasTarget = { id: string; kind: "node" | "connection" | "root" };

/** What a parent can ask of the canvas. Later tickets add export and more here. */
export type ShadowCanvasHandle = {
  /** Runs an edit on the canvas at once and sends it; rejects when refused (the change is then undone). */
  applyEdit(edit: GraphEdit): Promise<void>;
  /** Shows the whole graph with padding. */
  fit(): void;
  /** Zooms to a scale (1 is 100 %, clamped to 10 %-400 %) around the centre of the drawing area. */
  zoomTo(scale: number): void;
  zoomIn(): void;
  zoomOut(): void;
  /** 100 % around the centre of the drawing area. */
  actualSize(): void;
  /** Centres the drawing area on a canvas point, keeping the zoom. */
  centreOn(point: Point): void;
  getView(): View | null;
  /** Adds a key to the canvas keymap (it only fires while focus is inside the drawing and not in a text field); returns the function that removes it. */
  registerKey(binding: KeyBinding): () => void;
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
  /** Esc was pressed in the drawing: cancel what the parent has under way (connect mode) and return true, or return false to let Esc clear the selection. */
  onEscape?(): boolean;
  /** What the line remembers of its view: restored after a remount, fitted once after the line's first load. */
  view: ViewMemory;
  toolbarTexts: CanvasToolbarTexts;
  label: string;
  ref?: Ref<ShadowCanvasHandle>;
};

type Services = { importer: GraphImporter; modeling: GraphModeling; navigation: GraphNavigation; keys: GraphKeys };

const kindOf = (element: GraphElement | undefined): CanvasTarget["kind"] => (isNodeElement(element) ? "node" : isConnectionElement(element) ? "connection" : "root");

/**
 * One diagram-js `Diagram` for the lifetime of the component. React draws nothing inside it: it hands the plain graph to the importer,
 * which updates shapes in place, and the diagram reports selection and edits back through the props. The container is observed so the
 * diagram follows the size the page gives it.
 */
export function ShadowCanvas({ graph, readOnly, selectedId, onSelect, onElementClick, send, connecting = false, onEscape, view, toolbarTexts, label, ref }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const diagram = useRef<Diagram | null>(null);
  const services = useRef<Services | null>(null);
  const props = useRef({ onSelect, onElementClick, onEscape, send, selectedId, view });
  props.current = { onSelect, onElementClick, onEscape, send, selectedId, view };
  const [scale, setScale] = useState(1);
  // False until the first graph of this canvas has been placed (fitted or restored); before that the view is not remembered.
  const placed = useRef(false);
  const place = useRef<(() => void) | null>(null);

  useImperativeHandle(ref, () => {
    const navigation = () => services.current?.navigation;
    return {
      applyEdit: (edit) => (services.current ? services.current.modeling.applyEdit(edit) : Promise.reject(new Error("canvas not ready"))),
      fit: () => navigation()?.fit(),
      zoomTo: (value) => navigation()?.zoomTo(value),
      zoomIn: () => navigation()?.zoomStep(1),
      zoomOut: () => navigation()?.zoomStep(-1),
      actualSize: () => navigation()?.actualSize(),
      centreOn: (point) => navigation()?.centreOn(point),
      getView: () => navigation()?.getView() ?? null,
      registerKey: (binding) => services.current?.keys.keymap.register(binding) ?? (() => undefined),
    };
  }, []);

  // Create the diagram once and destroy it with the component.
  useEffect(() => {
    const host = container.current;
    if (!host) return;
    const created = new Diagram({ canvas: { container: host }, modules: [shadowGraphModule] });
    diagram.current = created;
    const get = <T,>(name: string) => created.get(name) as T;
    const modeling = get<GraphModeling>("graphModeling");
    const navigation = get<GraphNavigation>("graphNavigation");
    const keys = get<GraphKeys>("graphKeys");
    services.current = { importer: get<GraphImporter>("graphImporter"), modeling, navigation, keys };
    modeling.setSender((edit) => props.current.send(edit));
    const eventBus = get<{ on(event: string, priority: number, handler: (event: never) => unknown): void; off(event: string, handler: unknown): void }>("eventBus");
    const selection = get<{ get(): GraphElement[]; select(element: GraphElement | null): void }>("selection");
    const registry = get<{ get(id: string): GraphElement | undefined }>("elementRegistry");
    const canvas = get<{ resized(): void }>("canvas");

    // The readout follows the view; the line remembers it once the first graph has been placed.
    const onViewbox = ((event: { viewbox: { x: number; y: number; scale: number } }) => {
      setScale(event.viewbox.scale);
      if (placed.current) props.current.view.remember({ x: event.viewbox.x, y: event.viewbox.y, scale: event.viewbox.scale });
    }) as (event: never) => unknown;
    eventBus.on("canvas.viewbox.changed", 1000, onViewbox as never);
    // Esc: cancel connect mode first, otherwise clear the selection.
    const unregisterEscape = keys.keymap.register({
      id: "canvas.escape",
      keys: ["Escape"],
      run: () => {
        if (props.current.onEscape?.()) return true;
        if (selection.get().length === 0) return false;
        selection.select(null);
        return true;
      },
    });

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

    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => { canvas.resized(); place.current?.(); });
    observer?.observe(host);
    return () => {
      observer?.disconnect();
      unregisterEscape();
      host.removeEventListener("keydown", onKey);
      // Moves still waiting for their quiet time are saved when the canvas closes.
      void modeling.flush();
      modeling.setSender(null);
      created.destroy();
      diagram.current = null;
      services.current = null;
      place.current = null;
      placed.current = false;
    };
  }, []);

  // Hand every new graph to the importer; it diffs against what is drawn.
  useEffect(() => {
    if (!graph || !services.current || !diagram.current) return;
    services.current.importer.update(graph, readOnly);
    // The session's undo history belongs to one loaded graph; after a load its entries may point at replaced elements.
    (diagram.current.get("commandStack") as { clear(): void }).clear();
    // The first graph of a line is fitted, or, when this canvas replaces one of the same line, the view it had comes back. Later loads
    // (after a save) only update shapes in place and never touch the view. Waits for a measured drawing area (the observer retries).
    if (!placed.current) {
      const navigation = services.current.navigation;
      const settle = () => {
        if (placed.current) return;
        const size = navigation.size();
        if (size.width <= 0 || size.height <= 0) return;
        const remembered = props.current.view.view;
        if (remembered) navigation.setView(remembered);
        else if (!props.current.view.fitted) navigation.fit(false);
        props.current.view.markFitted();
        placed.current = true;
        place.current = null;
        props.current.view.remember(navigation.getView());
      };
      place.current = settle;
      settle();
    }
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

  const navigation = () => services.current?.navigation;
  return (
    <div className="relative h-full w-full">
      <div ref={container} role="group" aria-label={label} data-connecting={connecting || undefined} data-zoom={zoomPercent(scale)} className="shadow-canvas h-full w-full" />
      <CanvasToolbar
        scale={scale}
        texts={toolbarTexts}
        actions={{ zoomIn: () => navigation()?.zoomStep(1), zoomOut: () => navigation()?.zoomStep(-1), fit: () => navigation()?.fit(), actualSize: () => navigation()?.actualSize() }}
      />
    </div>
  );
}
