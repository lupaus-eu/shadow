import type AlignElements from "diagram-js/lib/features/align-elements/AlignElements.js";
import type Canvas from "diagram-js/lib/core/Canvas.js";
import type EventBus from "diagram-js/lib/core/EventBus.js";
import type GridSnapping from "diagram-js/lib/features/grid-snapping/GridSnapping.js";
import type Selection from "diagram-js/lib/features/selection/Selection.js";

import { distributePlaces } from "../arrange";
import { computeLayout, placeLayout, type LayoutEdge, type LayoutNode } from "../layout";
import { GRID_SPACING, snapDelta } from "../snap";
import type { Point } from "../view";
import type { GraphContext } from "./GraphRules";
import type { GraphModeling } from "./GraphModeling";
import type { GraphNavigation } from "./GraphNavigation";
import type { GraphPopover } from "./GraphPopover";
import { isConnectionElement, isNodeElement, isPendingId, type GraphElement, type RegistryLike } from "./model";

export type AlignMode = "left" | "centre" | "top" | "middle";
export type DistributeAxis = "horizontal" | "vertical";

/** Align needs two nodes, distribute three (the first and last stay, the ones between get equal gaps). */
export const MIN_ALIGN = 2;
export const MIN_DISTRIBUTE = 3;

/** The part of a `shape.move.move` event that snapping reads and rewrites. */
export type MoveEvent = { context: { shape?: GraphElement }; dx: number; dy: number; originalEvent?: { ctrlKey?: boolean; metaKey?: boolean } };

const ALIGNMENT: Record<AlignMode, "left" | "center" | "top" | "middle"> = { left: "left", centre: "center", top: "top", middle: "middle" };

/**
 * The tidying tools of the canvas: snap to the grid, align, distribute and automatic layout. Align and distribute are the library's own
 * `align-elements` (one command); distribute is our own arithmetic (`arrange.ts`) applied as one command; automatic layout asks `elkjs` for places and applies them as one command
 * (`GraphModeling.arrange`). Every one of them ends in exactly one write of positions and one entry in the person's history, because the
 * moves are collected by `GraphModeling` and saved straight away. Nothing here runs unless asked: the graph never rearranges itself.
 *
 * Snapping is the library's `grid-snapping` for its on/off state and the grid size; the drag itself is finished here, because the library
 * snaps the pointer, which only lands a node on the grid when it started on the grid. With snapping on, the dragged node's own top left
 * corner is snapped and the other selected nodes move by the same amount. Holding Ctrl or Cmd while dragging turns snapping off for that drag.
 */
export class GraphTools {
  static $inject = ["eventBus", "canvas", "selection", "gridSnapping", "alignElements", "graphModeling", "graphNavigation", "graphContext", "elementRegistry", "graphPopover"];

  constructor(
    eventBus: EventBus,
    private readonly canvas: Canvas,
    private readonly selection: Selection,
    private readonly grid: GridSnapping,
    private readonly alignElements: AlignElements,
    private readonly modeling: GraphModeling,
    private readonly navigation: GraphNavigation,
    private readonly context: GraphContext,
    private readonly registry: RegistryLike,
    private readonly popover: GraphPopover,
  ) {
    const bus = eventBus as unknown as { on(event: string, priority: number, handler: (event: never) => unknown): void };
    // After the library's own pointer snapping (priority 1200) and before the move reads `dx` and `dy` (priority 500).
    bus.on("shape.move.move", 1100, ((event: MoveEvent) => this.snapMove(event)) as never);
  }

  /** Finishes a drag with snapping on (see the class comment): rewrites the event's `dx` and `dy` so the dragged node ends on the grid. */
  snapMove(event: MoveEvent): void {
    const shape = event.context.shape;
    if (!this.grid.isActive() || !shape || !isNodeElement(shape) || (event.originalEvent && (event.originalEvent.ctrlKey || event.originalEvent.metaKey))) return;
    const snapped = snapDelta({ x: shape.x, y: shape.y }, { x: event.dx, y: event.dy }, this.grid.getGridSpacing?.() ?? GRID_SPACING);
    event.dx = snapped.x;
    event.dy = snapped.y;
  }

  get snapping(): boolean { return this.grid.isActive(); }
  setSnapping(on: boolean) { if (this.grid.isActive() !== on) this.grid.setActive(on); }

  /** The selected nodes that are drawn (a node of a hidden type cannot be selected, but a stale selection is filtered all the same). */
  selectedNodes(): GraphElement[] {
    return (this.selection.get() as unknown as GraphElement[]).filter((element) => isNodeElement(element) && !isPendingId(element.id) && !this.canvas.hasMarker(element as never, "shadow-hidden"));
  }

  canAlign(): boolean { return !this.context.readOnly && this.selectedNodes().length >= MIN_ALIGN; }
  canDistribute(): boolean { return !this.context.readOnly && this.selectedNodes().length >= MIN_DISTRIBUTE; }

  /** Aligns the selected nodes to their left edges, centres, top edges or middles. Resolves when the positions are saved; false when there was nothing to do. */
  async align(mode: AlignMode): Promise<boolean> {
    if (!this.canAlign()) return false;
    this.popover.hide();
    this.alignElements.trigger(this.selectedNodes() as never[], ALIGNMENT[mode]);
    await this.modeling.flush();
    return true;
  }

  /** Spreads the selected nodes so the gaps between them are equal, keeping the first and the last where they are. False when there is no free space to share. */
  async distribute(axis: DistributeAxis): Promise<boolean> {
    if (!this.canDistribute()) return false;
    this.popover.hide();
    const places = distributePlaces(this.selectedNodes().map((node) => ({ id: node.id, x: node.x, y: node.y, width: node.width, height: node.height })), axis);
    if (!places) return false;
    await this.modeling.arrange([...places].map(([id, at]) => ({ id, ...at })));
    return true;
  }

  /** Lays every drawn node out in layers with `elkjs` and moves them as one step; the graph keeps its top left corner and is then fitted in view. False when there are fewer than two nodes. */
  async autoLayout(): Promise<boolean> {
    if (this.context.readOnly) return false;
    const nodes = this.registry.filter((element) => isNodeElement(element) && !isPendingId(element.id)) as GraphElement[];
    if (nodes.length < 2) return false;
    const ids = new Set(nodes.map((node) => node.id));
    const input: LayoutNode[] = nodes.map((node) => ({ id: node.id, width: node.width, height: node.height }));
    const edges: LayoutEdge[] = (this.registry.filter(isConnectionElement) as GraphElement[]).filter((edge) => edge.source && edge.target && ids.has(edge.source.id) && ids.has(edge.target.id)).map((edge) => ({ id: edge.id, source: edge.source!.id, target: edge.target!.id }));
    const anchor: Point = { x: Math.min(...nodes.map((node) => node.x)), y: Math.min(...nodes.map((node) => node.y)) };
    const placed = placeLayout(await computeLayout(input, edges), anchor);
    this.popover.hide();
    await this.modeling.arrange([...placed].map(([id, at]) => ({ id, ...at })));
    this.navigation.fit();
    return true;
  }
}
