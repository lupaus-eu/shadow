import Diagram from "diagram-js";
import { useEffect, useId, useImperativeHandle, useRef, useState, type Ref } from "react";

import { CanvasToolbar, type CanvasToolbarTexts } from "./CanvasToolbar";
import { buildExportSvg, downloadBlob, exportFileName, resolveTokens, svgBlob, svgToPng } from "./export";
import type { GraphMinimap } from "./minimap";
import type { DrawingHandlers, DrawingState, GraphDrawing } from "./diagram/GraphDrawing";
import type { HistoryOutcome, HistoryState } from "./history";
import { shadowGraphModule } from "./diagram";
import type { GraphFilter } from "./diagram/GraphFilter";
import type { GraphImporter } from "./diagram/GraphImporter";
import type { GraphKeys } from "./diagram/GraphKeys";
import type { GraphModeling } from "./diagram/GraphModeling";
import type { GraphNavigation } from "./diagram/GraphNavigation";
import { MIN_ALIGN, MIN_DISTRIBUTE, type AlignMode, type DistributeAxis, type GraphTools } from "./diagram/GraphTools";
import { isConnectionElement, isNodeElement, type GraphElement } from "./diagram/model";
import type { GraphData, GraphEdit, GraphEditSender } from "./graph-types";
import type { KeyBinding } from "./keymap";
import { noFilter, type CanvasFilter } from "./type-list";
import { zoomPercent, type Point, type View, type ViewMemory } from "./view";

/** What a tidying or export tool came to, for the parent to say aloud (a failure is a notice). Nothing is reported when there was nothing to do. */
export type ToolResult = { tool: "align" | "distribute" | "layout" | "export" | "minimap"; ok: boolean };

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
  /** Aligns the selected nodes (two or more); one history entry. False when fewer are selected. */
  align(mode: AlignMode): Promise<boolean>;
  /** Spreads the selected nodes (three or more) with equal gaps; one history entry. */
  distribute(axis: DistributeAxis): Promise<boolean>;
  /** Lays the graph out in layers (loads `elkjs` now); one history entry. */
  autoLayout(): Promise<boolean>;
  /** Downloads the canvas as an SVG or a PNG file named after the model and the line; false when nothing is drawn. */
  exportImage(kind: "svg" | "png"): Promise<boolean>;
  /** Puts keyboard focus back on the drawing (the selected node, else the first drawn node, else the drawing itself); used after a dialog closed. */
  focus(): void;
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
  /** Snap to the grid: the person's choice (kept by the parent), applied to every diagram this component creates. */
  snap: boolean;
  onSnapChange(on: boolean): void;
  /** Names the exported files: `model-line.svg`, sanitised. */
  exportName: { model: string; line: string };
  /** A tool finished (or failed). */
  onToolResult?(result: ToolResult): void;
  /** The toolbar's Connect button. */
  onToggleConnect(): void;
  toolbarTexts: CanvasToolbarTexts;
  label: string;
  /** Said by screen readers after the label: the keys of the drawing. */
  description?: string;
  ref?: Ref<ShadowCanvasHandle>;
};

type Services = { tools: GraphTools; drawing: GraphDrawing; importer: GraphImporter; filter: GraphFilter; registry: { get(id: string): GraphElement | undefined }; modeling: GraphModeling; navigation: GraphNavigation; keys: GraphKeys };

const kindOf = (element: GraphElement | undefined): CanvasTarget["kind"] => (isNodeElement(element) ? "node" : isConnectionElement(element) ? "connection" : "root");

/**
 * One diagram-js `Diagram` for the lifetime of the component. React draws nothing inside it: it hands the plain graph to the importer,
 * which updates shapes in place, and the diagram reports selection and edits back through the props. The container is observed so the
 * diagram follows the size the page gives it.
 */
export function ShadowCanvas({ graph, readOnly, selectedIds, onSelect, drawing, drawingTexts, readGraph, isRefusal, onHistory, onToggleConnect, onElementClick, send, connecting = false, onEscape, view, filter = noFilter, keyBindings, snap, onSnapChange, exportName, onToolResult, toolbarTexts, label, description, ref }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const descriptionId = useId();
  const diagram = useRef<Diagram | null>(null);
  const services = useRef<Services | null>(null);
  const props = useRef({ onSelect, onElementClick, onEscape, send, selectedIds, view, keyBindings, drawing, drawingTexts, readGraph, isRefusal, onHistory, snap, onSnapChange, exportName, onToolResult });
  props.current = { onSelect, onElementClick, onEscape, send, selectedIds, view, keyBindings, drawing, drawingTexts, readGraph, isRefusal, onHistory, snap, onSnapChange, exportName, onToolResult };
  const [history, setHistory] = useState<HistoryState>({ canUndo: false, canRedo: false, busy: false });
  const [tools, setTools] = useState<DrawingState>({ lasso: false });
  const [scale, setScale] = useState(1);
  // The minimap starts closed (it covers a corner of the drawing); the toolbar button opens it, and its code is loaded then, as a chunk of its own.
  const [minimapOpen, setMinimapOpen] = useState(false);
  const minimap = useRef<GraphMinimap | null>(null);
  const [busy, setBusy] = useState(false);
  // False until the first graph of this canvas has been placed (fitted or restored); before that the view is not remembered.
  const placed = useRef(false);
  const place = useRef<(() => void) | null>(null);

  /** Runs a tool and tells the parent how it went; `true` from the tool means it did something. A refusal or failure is a failed result, never an exception. */
  const runTool = async (tool: ToolResult["tool"], run: () => Promise<boolean>, blocking = false): Promise<boolean> => {
    if (blocking) setBusy(true);
    try {
      const done = await run();
      if (done) props.current.onToolResult?.({ tool, ok: true });
      return done;
    } catch {
      props.current.onToolResult?.({ tool, ok: false });
      return false;
    } finally {
      if (blocking) setBusy(false);
    }
  };

  /** Serialises the canvas as SVG (or draws that onto a PNG) and downloads it. False when nothing is drawn. */
  const exportImage = async (kind: "svg" | "png"): Promise<boolean> => {
    const source = container.current?.querySelector<SVGSVGElement>(".djs-container > svg");
    const navigation = services.current?.navigation;
    if (!source || !navigation) return false;
    const { model, line } = props.current.exportName;
    const exported = buildExportSvg(source, navigation.graphBounds(), { title: `${model} - ${line}`, tokens: resolveTokens((name) => getComputedStyle(document.documentElement).getPropertyValue(name)) });
    if (!exported) return false;
    downloadBlob(kind === "svg" ? svgBlob(exported) : await svgToPng(exported), exportFileName(model, line, kind));
    return true;
  };

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
      align: (mode) => runTool("align", () => services.current?.tools.align(mode) ?? Promise.resolve(false)),
      distribute: (axis) => runTool("distribute", () => services.current?.tools.distribute(axis) ?? Promise.resolve(false)),
      autoLayout: () => runTool("layout", () => services.current?.tools.autoLayout() ?? Promise.resolve(false), true),
      exportImage: (kind) => runTool("export", () => exportImage(kind), true),
      focus: () => {
        const host = container.current;
        if (!host) return;
        const visible = ".djs-element.djs-shape[role='button']:not(.shadow-hidden)";
        const target = host.querySelector<SVGElement>(`.selected${visible}`) ?? host.querySelector<SVGElement>(visible) ?? host.querySelector<SVGElement>(".djs-container > svg");
        target?.focus();
      },
      setLasso: (on) => services.current?.drawing.setLasso(on),
      registerKey: (binding) => services.current?.keys.keymap.register(binding) ?? (() => undefined),
    };
  }, []);

  // Create the diagram once and destroy it with the component.
  useEffect(() => {
    const host = container.current;
    if (!host) return;
    const created = new Diagram({ canvas: { container: host }, gridSnapping: { active: false }, modules: [shadowGraphModule] });
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
    const tools = get<GraphTools>("graphTools");
    tools.setSnapping(props.current.snap);
    services.current = { tools, drawing: drawingService, importer: get<GraphImporter>("graphImporter"), filter: get<GraphFilter>("graphFilter"), registry, modeling, navigation, keys };
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
      minimap.current = null;
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
  useEffect(() => { services.current?.filter.apply(filter); minimap.current?.refresh(); }, [graph, filter]);

  // The person's snap choice (kept by the parent) is the diagram's snapping.
  useEffect(() => { services.current?.tools.setSnapping(snap); }, [snap]);
  // Open or close the minimap when the toolbar says so. The first opening loads its code (and attaches it to this diagram); if that fails the button pops back out.
  useEffect(() => {
    if (!minimapOpen) { minimap.current?.close(); return; }
    if (minimap.current) { minimap.current.open(); return; }
    const created = diagram.current;
    let cancelled = false;
    void import("./minimap").then(({ attachMinimap }) => {
      if (cancelled || !created || diagram.current !== created) return;
      minimap.current = attachMinimap(created as never, true);
    }).catch(() => {
      if (cancelled) return;
      setMinimapOpen(false);
      props.current.onToolResult?.({ tool: "minimap", ok: false });
    });
    return () => { cancelled = true; };
  }, [minimapOpen]);

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
  const registry = services.current?.registry;
  const selectedNodes = selectedIds.filter((id) => { const element = registry?.get(id); return !!element && isNodeElement(element); }).length;
  const nodeCount = graph?.nodes.length ?? 0;
  return (
    <div className="relative h-full w-full">
      {description ? <p id={descriptionId} className="sr-only">{description}</p> : null}
      <div ref={container} role="group" aria-label={label} aria-describedby={description ? descriptionId : undefined} data-connecting={connecting || undefined} data-zoom={zoomPercent(scale)} className="shadow-canvas h-full w-full" />
      <CanvasToolbar
        scale={scale}
        texts={toolbarTexts}
        actions={{ zoomIn: () => navigation()?.zoomStep(1), zoomOut: () => navigation()?.zoomStep(-1), fit: () => navigation()?.fit(), actualSize: () => navigation()?.actualSize() }}
        edit={{ writable: !readOnly, canUndo: history.canUndo, canRedo: history.canRedo, busy: history.busy, connecting, lasso: tools.lasso }}
        editActions={{ undo: () => void services.current?.modeling.undo(), redo: () => void services.current?.modeling.redo(), toggleConnect: onToggleConnect, toggleLasso: () => services.current?.drawing.setLasso(!services.current.drawing.state.lasso) }}
        tools={{ writable: !readOnly, snap, canAlign: selectedNodes >= MIN_ALIGN, canDistribute: selectedNodes >= MIN_DISTRIBUTE, canLayout: nodeCount >= 2, busy, minimap: minimapOpen, canExport: nodeCount > 0 }}
        toolActions={{
          toggleSnap: () => onSnapChange(!snap),
          align: (mode) => void runTool("align", () => services.current?.tools.align(mode) ?? Promise.resolve(false)),
          distribute: (axis) => void runTool("distribute", () => services.current?.tools.distribute(axis) ?? Promise.resolve(false)),
          autoLayout: () => void runTool("layout", () => services.current?.tools.autoLayout() ?? Promise.resolve(false), true),
          toggleMinimap: () => setMinimapOpen((open) => !open),
          exportSvg: () => void runTool("export", () => exportImage("svg"), true),
          exportPng: () => void runTool("export", () => exportImage("png"), true),
        }}
      />
    </div>
  );
}
