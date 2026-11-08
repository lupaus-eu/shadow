import Diagram from "diagram-js";
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";

import { CanvasToolbar, type CanvasToolbarTexts } from "./CanvasToolbar";
import type { DrawingHandlers, DrawingState, GraphDrawing } from "./diagram/GraphDrawing";
import type { HistoryOutcome, HistoryState } from "./history";
import { shadowGraphModule } from "./diagram";
import type { GraphFilter } from "./diagram/GraphFilter";
import type { GraphImporter } from "./diagram/GraphImporter";
import type { GraphKeys } from "./diagram/GraphKeys";
import type { GraphModeling } from "./diagram/GraphModeling";
import type { GraphNavigation } from "./diagram/GraphNavigation";
import { isConnectionElement, isNodeElement, type GraphElement } from "./diagram/model";
import type { GraphData, GraphEdit, GraphEditSender } from "./graph-types";
import type { KeyBinding } from "./keymap";
import { noFilter, type CanvasFilter } from "./type-list";
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
  /** Centres on a node (the drawing's own position of it, so an unsaved move counts); with `zoom` also zooms in to at least 100 %. False when the node is not drawn. */
  centreOnNode(id: string, options?: { zoom?: boolean }): boolean;
  getView(): View | null;
  /** Draws an empty node of a type at the centre of the view and opens its name for editing; false when it cannot (read-only, unknown type). */
  addNode(nodeTypeId: string): boolean;
  /** Opens a node's name for editing in place. */
  renameNode(id: string): boolean;
  /** Undoes or redoes the person's last step (see `history.ts`); the outcome is also reported through `onHistory`. */
  undo(): Promise<HistoryOutcome>;
  redo(): Promise<HistoryOutcome>;
  /** Forgets the undo and redo stacks (the line or event changed). */
  clearHistory(): void;
  /** Switches the lasso mode. */
  setLasso(on: boolean): void;
  /** Adds a key to the canvas keymap (it only fires while focus is inside the drawing and not in a text field); returns the function that removes it. */
  registerKey(binding: KeyBinding): () => void;
};

type Props = {
  graph: GraphData | null;
  readOnly: boolean;
  /** The selected nodes and connections. The canvas follows them and reports changes through `onSelect`. */
  selectedIds: readonly string[];
  onSelect(ids: string[]): void;
  /** What the pointer gestures of the canvas ask of the parent (connect, delete from the pad, naming in place). */
  drawing: DrawingHandlers;
  drawingTexts: { connect: string; remove: string; nodeName: string; namePlaceholder: string };
  /** A fresh read of the graph, for the history (it checks the state before every undo and redo). Resolves null when it failed. */
  readGraph(): Promise<GraphData | null>;
  /** True for a refusal of the server (stale, rule, broken chain). */
  isRefusal(error: unknown): boolean;
  /** An undo or redo finished, was refused or was rejected. */
  onHistory(outcome: HistoryOutcome): void;
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
  /** Which types are hidden and which nodes match a search; applied as markers on the drawn elements. */
  filter?: CanvasFilter;
  /** Keys of the parent's panels, registered on every diagram this component creates (read when the diagram is created; their `run` should read refs). Registering through the handle instead would be lost when the diagram is recreated. */
  keyBindings?: KeyBinding[];
  /** The toolbar's Connect button. */
  onToggleConnect(): void;
  toolbarTexts: CanvasToolbarTexts;
  label: string;
  ref?: Ref<ShadowCanvasHandle>;
};

type Services = { drawing: GraphDrawing; importer: GraphImporter; filter: GraphFilter; registry: { get(id: string): GraphElement | undefined }; modeling: GraphModeling; navigation: GraphNavigation; keys: GraphKeys };

const kindOf = (element: GraphElement | undefined): CanvasTarget["kind"] => (isNodeElement(element) ? "node" : isConnectionElement(element) ? "connection" : "root");

/**
 * One diagram-js `Diagram` for the lifetime of the component. React draws nothing inside it: it hands the plain graph to the importer,
 * which updates shapes in place, and the diagram reports selection and edits back through the props. The container is observed so the
 * diagram follows the size the page gives it.
 */
export function ShadowCanvas({ graph, readOnly, selectedIds, onSelect, drawing, drawingTexts, readGraph, isRefusal, onHistory, onToggleConnect, onElementClick, send, connecting = false, onEscape, view, filter = noFilter, keyBindings, toolbarTexts, label, ref }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const diagram = useRef<Diagram | null>(null);
  const services = useRef<Services | null>(null);
  const props = useRef({ onSelect, onElementClick, onEscape, send, selectedIds, view, keyBindings, drawing, drawingTexts, readGraph, isRefusal, onHistory });
  props.current = { onSelect, onElementClick, onEscape, send, selectedIds, view, keyBindings, drawing, drawingTexts, readGraph, isRefusal, onHistory };
  const [history, setHistory] = useState<HistoryState>({ canUndo: false, canRedo: false, busy: false });
  const [tools, setTools] = useState<DrawingState>({ lasso: false });
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
      centreOnNode: (id, options) => {
        const element = services.current?.registry.get(id);
        if (!element || !isNodeElement(element)) return false;
        const point = { x: element.x + element.width / 2, y: element.y + element.height / 2 };
        if (options?.zoom) navigation()?.focus(point); else navigation()?.centreOn(point);
        return true;
      },
      getView: () => navigation()?.getView() ?? null,
      addNode: (typeId) => services.current?.drawing.addNode(typeId) ?? false,
      renameNode: (id) => services.current?.drawing.renameNode(id) ?? false,
      undo: () => services.current?.modeling.undo() ?? Promise.resolve({ status: "idle" as const }),
      redo: () => services.current?.modeling.redo() ?? Promise.resolve({ status: "idle" as const }),
      clearHistory: () => services.current?.modeling.history.clear(),
      setLasso: (on) => services.current?.drawing.setLasso(on),
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
    const registry = get<{ get(id: string): GraphElement | undefined }>("elementRegistry");
    const drawingService = get<GraphDrawing>("graphDrawing");
    drawingService.setHandlers({
      connect: (a, b) => props.current.drawing.connect(a, b),
      remove: (ids) => props.current.drawing.remove(ids),
      create: (input) => props.current.drawing.create(input),
      rename: (id, name) => props.current.drawing.rename(id, name),
    });
    drawingService.setTexts(props.current.drawingTexts);
    modeling.setHistoryPort({ read: () => props.current.readGraph(), isRefusal: (error) => props.current.isRefusal(error), report: (outcome) => props.current.onHistory(outcome) });
    const unsubscribeHistory = modeling.history.subscribe(setHistory);
    const unsubscribeTools = drawingService.subscribe(setTools);
    services.current = { drawing: drawingService, importer: get<GraphImporter>("graphImporter"), filter: get<GraphFilter>("graphFilter"), registry, modeling, navigation, keys };
    modeling.setSender((edit) => props.current.send(edit));
    const eventBus = get<{ on(event: string, priority: number, handler: (event: never) => unknown): void; off(event: string, handler: unknown): void }>("eventBus");
    const selection = get<{ get(): GraphElement[]; select(element: GraphElement | null): void }>("selection");
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
        if (drawingService.state.lasso) { drawingService.setLasso(false); return true; }
        if (props.current.onEscape?.()) return true;
        if (selection.get().length === 0) return false;
        selection.select(null);
        return true;
      },
    });

    const unregisterParentKeys = (props.current.keyBindings ?? []).map((binding) => keys.keymap.register(binding));

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
    const onSelection = ((event: { newSelection: GraphElement[] }) => props.current.onSelect(event.newSelection.map((element) => element.id))) as (event: never) => unknown;
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
      unsubscribeHistory();
      unsubscribeTools();
      unregisterEscape();
      for (const unregister of unregisterParentKeys) unregister();
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

  // Hide and dim after every load or choice of the panel (a load may add elements; the markers are idempotent).
  useEffect(() => { services.current?.filter.apply(filter); }, [graph, filter]);

  // Follow the parent's selection.
  useEffect(() => {
    const created = diagram.current;
    if (!created) return;
    const selection = created.get("selection") as { get(): GraphElement[]; select(elements: GraphElement[] | null): void };
    const registry = created.get("elementRegistry") as { get(id: string): GraphElement | undefined };
    const wanted = selectedIds.map((id) => registry.get(id)).filter((element): element is GraphElement => !!element);
    const current = selection.get();
    if (current.length === wanted.length && current.every((element) => wanted.includes(element))) return;
    selection.select(wanted);
  }, [selectedIds, graph]);

  const navigation = () => services.current?.navigation;
  return (
    <div className="relative h-full w-full">
      <div ref={container} role="group" aria-label={label} data-connecting={connecting || undefined} data-zoom={zoomPercent(scale)} className="shadow-canvas h-full w-full" />
      <CanvasToolbar
        scale={scale}
        texts={toolbarTexts}
        actions={{ zoomIn: () => navigation()?.zoomStep(1), zoomOut: () => navigation()?.zoomStep(-1), fit: () => navigation()?.fit(), actualSize: () => navigation()?.actualSize() }}
        edit={{ writable: !readOnly, canUndo: history.canUndo, canRedo: history.canRedo, busy: history.busy, connecting, lasso: tools.lasso }}
        editActions={{ undo: () => void services.current?.modeling.undo(), redo: () => void services.current?.modeling.redo(), toggleConnect: onToggleConnect, toggleLasso: () => services.current?.drawing.setLasso(!services.current.drawing.state.lasso) }}
      />
    </div>
  );
}
