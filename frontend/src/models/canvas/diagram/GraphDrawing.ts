import type Canvas from "diagram-js/lib/core/Canvas.js";
import type ElementFactory from "diagram-js/lib/core/ElementFactory.js";
import type EventBus from "diagram-js/lib/core/EventBus.js";
import type Overlays from "diagram-js/lib/features/overlays/Overlays.js";
import type Selection from "diagram-js/lib/features/selection/Selection.js";

import { freeSpot } from "../draw";
import type { GraphNavigation } from "./GraphNavigation";
import type { GraphContext, GraphRules } from "./GraphRules";
import { isConnectionElement, isNodeElement, normalizeName, type GraphElement, type NodeObject, type RegistryLike } from "./model";
import { NODE_HEIGHT, NODE_WIDTH } from "./shapes";

type LassoTool = { activateLasso(event: Event, autoActivate?: boolean): void };
type Connect = { start(event: Event, start: unknown, autoActivate?: boolean): void };

/** What the parent decides when a gesture on the canvas ends. All of them only ask: the parent applies the rules, confirms and writes. */
export type DrawingHandlers = {
  /** A connection was drawn from one node to another (drag from the context pad, or two clicks). */
  connect(sourceId: string, targetId: string): void;
  /** The context pad asks to delete these elements. */
  remove(ids: string[]): void;
  /** A new node was named in place. */
  create(input: { nodeTypeId: string; name: string; x: number; y: number }): void;
  /** An existing node was renamed in place. */
  rename(id: string, name: string): void;
};

export type DrawingTexts = { connect: string; remove: string; nodeName: string; namePlaceholder: string };

export type DrawingState = { lasso: boolean };

const MAX_NAME = 120;
const EDITOR = "shadow-editor";

let draftCounter = 0;

/**
 * Everything the person draws with the pointer apart from moving: the context pad (connect and delete), the connect gesture of the
 * library (drag from the pad, or click the pad and then the target), the lasso mode, and naming a node in place. It decides nothing:
 * the outcome of each gesture is handed to `handlers`, which are the parent's. The library's `connect` would draw the connection itself;
 * here its end is taken over, so a drag and the two-click mode end in the same place and the same messages.
 */
export class GraphDrawing {
  static $inject = ["eventBus", "canvas", "overlays", "elementRegistry", "elementFactory", "selection", "connect", "lassoTool", "graphNavigation", "graphContext", "graphRules"];

  handlers: DrawingHandlers | null = null;
  texts: DrawingTexts = { connect: "Connect", remove: "Delete", nodeName: "Node name", namePlaceholder: "Name" };
  private lassoOn = false;
  private readonly listeners = new Set<(state: DrawingState) => void>();
  private editor: { close(commit: boolean): void } | null = null;

  constructor(
    private readonly eventBus: EventBus,
    private readonly canvas: Canvas,
    private readonly overlays: Overlays,
    private readonly registry: RegistryLike,
    private readonly factory: ElementFactory,
    private readonly selection: Selection,
    private readonly connect: Connect,
    private readonly lasso: LassoTool,
    private readonly navigation: GraphNavigation,
    private readonly context: GraphContext,
    private readonly rules: GraphRules,
  ) {
    // The library's hover would also accept the reverse direction; Shadow connections run from where the drag starts.
    eventBus.on("connect.hover", 900, (event: { context: { start: GraphElement; hover: GraphElement | null; canExecute: unknown; source: unknown; target: unknown } }) => {
      const { context } = event;
      if (!isNodeElement(context.start) || !isNodeElement(context.hover)) return;
      context.source = context.start;
      context.target = context.hover;
      context.canExecute = this.rules.options(context.start, context.hover).types.length > 0;
    });
    // The end of a connect gesture is ours: nothing is drawn by the library, the parent checks the rules and writes.
    eventBus.on("connect.end", 3000, (event: { context: { start: GraphElement; hover: GraphElement | null } }) => {
      const { start, hover } = event.context;
      if (isNodeElement(start) && isNodeElement(hover) && !this.context.readOnly) this.handlers?.connect(start.id, hover.id);
      return false;
    });
    // In lasso mode a press on the background draws the selection rectangle instead of panning.
    eventBus.on("element.mousedown", 1600, (event: { element: GraphElement; originalEvent: MouseEvent }) => {
      if (!this.lassoOn || event.element !== (this.canvas.getRootElement() as unknown) || event.originalEvent.button !== 0) return undefined;
      this.lasso.activateLasso(event.originalEvent, true);
      return false;
    });
    // Double-clicking a node renames it in place.
    eventBus.on("element.dblclick", 1500, (event: { element: GraphElement }) => {
      if (!isNodeElement(event.element) || this.context.readOnly) return undefined;
      this.renameNode(event.element.id);
      return false;
    });
    // The selection rectangle must not pick up what the type panel hides.
    eventBus.on("selection.changed", 1100, (event: { newSelection: GraphElement[] }) => {
      const shown = event.newSelection.filter((element) => !this.canvas.hasMarker(element as never, "shadow-hidden"));
      if (shown.length !== event.newSelection.length) queueMicrotask(() => this.selection.select(shown as never));
    });
    eventBus.on("diagram.destroy", () => this.editor?.close(false));
  }

  setHandlers(handlers: DrawingHandlers | null) { this.handlers = handlers; }
  setTexts(texts: DrawingTexts) { this.texts = texts; }

  get state(): DrawingState { return { lasso: this.lassoOn }; }
  subscribe(listener: (state: DrawingState) => void): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  /** Switches the lasso mode (a press on the background draws a selection rectangle). */
  setLasso(on: boolean) {
    if (this.lassoOn === on) return;
    this.lassoOn = on;
    for (const listener of this.listeners) listener(this.state);
  }

  /** Starts the library's connect gesture from a node (the context pad's entry: dragged, or clicked and then the target clicked). */
  startConnect(event: Event, element: GraphElement) {
    if (this.context.readOnly || !isNodeElement(element)) return;
    this.connect.start(event, element);
  }

  /** Where a new node goes: the centre of what is in view at the current zoom and pan, moved aside a little while a node is already there. */
  newNodeSpot(): { x: number; y: number } {
    const centre = this.navigation.viewCentre();
    const taken = this.registry.filter(isNodeElement).map((node) => ({ x: node.x, y: node.y }));
    return freeSpot({ x: Math.round(centre.x - NODE_WIDTH / 2), y: Math.round(centre.y - NODE_HEIGHT / 2) }, taken);
  }

  /**
   * Draws an empty node of a type at the centre of the view and opens its name for editing. Enter or leaving the field keeps it
   * (a blank name cancels), Esc cancels. Nothing is sent before the name is committed, and nothing is left behind by a cancel.
   */
  addNode(nodeTypeId: string): boolean {
    if (this.context.readOnly) return false;
    const nodeType = this.context.nodeTypes.find((type) => type.id === nodeTypeId);
    if (!nodeType) return false;
    this.editor?.close(false);
    const spot = this.newNodeSpot();
    const id = `draft-${++draftCounter}`;
    const businessObject: NodeObject = { kind: "node", node: { id, node_type_id: nodeTypeId, name: "", description: null, x: spot.x, y: spot.y }, nodeType, change: null, draft: true };
    const shape = this.factory.createShape({ id, x: spot.x, y: spot.y, width: NODE_WIDTH, height: NODE_HEIGHT, businessObject } as never) as unknown as GraphElement;
    this.canvas.addShape(shape as never, this.canvas.getRootElement());
    this.selection.select(null as never);
    this.openEditor(shape, "", (name) => {
      this.canvas.removeShape(shape as never);
      if (name) this.handlers?.create({ nodeTypeId, name, x: spot.x, y: spot.y });
    });
    return true;
  }

  /** Opens a node's name for editing in place. */
  renameNode(id: string): boolean {
    const element = this.registry.get(id);
    if (this.context.readOnly || !element || !isNodeElement(element) || element.businessObject.draft) return false;
    this.editor?.close(false);
    const before = element.businessObject.node.name;
    this.openEditor(element, before, (name) => { if (name && name !== before) this.handlers?.rename(id, name); });
    return true;
  }

  /** True while a name is being edited in place. */
  get editing(): boolean { return this.editor !== null; }

  /**
   * The editor is an input over the node (an overlay, so it follows pan and zoom). `done(name)` runs once: with the name for Enter and
   * for leaving the field, with an empty string for Esc. A draft is removed by its own `done`.
   */
  private openEditor(element: GraphElement, initial: string, done: (name: string) => void) {
    const wrapper = document.createElement("div");
    wrapper.className = EDITOR;
    wrapper.style.width = `${NODE_WIDTH}px`;
    wrapper.style.height = `${NODE_HEIGHT}px`;
    const input = document.createElement("input");
    input.type = "text";
    input.value = initial;
    input.maxLength = MAX_NAME;
    input.setAttribute("aria-label", this.texts.nodeName);
    input.placeholder = this.texts.namePlaceholder;
    input.className = "shadow-editor-input";
    wrapper.append(input);
    const overlayId = this.overlays.add(element as never, EDITOR, { position: { top: 0, left: 0 }, html: wrapper, scale: true } as never);
    let finished = false;
    const finish = (commit: boolean) => {
      if (finished) return;
      finished = true;
      const name = commit ? normalizeName(input.value) : "";
      this.overlays.remove(overlayId);
      this.editor = null;
      done(name);
      this.canvas.getContainer().querySelector<SVGElement>(`[data-element-id="${CSS.escape(element.id)}"]`)?.focus();
    };
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); if (normalizeName(input.value)) finish(true); else input.setAttribute("aria-invalid", "true"); }
      else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finish(false); }
      else event.stopPropagation();
    });
    input.addEventListener("input", () => input.removeAttribute("aria-invalid"));
    input.addEventListener("blur", () => finish(normalizeName(input.value) !== ""));
    this.editor = { close: finish };
    queueMicrotask(() => { input.focus(); input.select(); });
  }

  /** Closes the editor without keeping its text. */
  cancelEditing() { this.editor?.close(false); }

  /** The elements the context pad may act on: a node or a connection of a writable diagram. */
  canEdit(element: unknown): element is GraphElement {
    return !this.context.readOnly && (isNodeElement(element) || isConnectionElement(element)) && !(isNodeElement(element) && element.businessObject.draft);
  }
}
