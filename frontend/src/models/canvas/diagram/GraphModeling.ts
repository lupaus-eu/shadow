import type Canvas from "diagram-js/lib/core/Canvas.js";
import type CommandStack from "diagram-js/lib/command/CommandStack.js";
import type EventBus from "diagram-js/lib/core/EventBus.js";
import type Modeling from "diagram-js/lib/features/modeling/Modeling.js";

import type { EditResult, GraphData, GraphEdit, GraphEditSender } from "../graph-types";
import { GraphHistory, type ConnectionSnapshot, type HistoryOutcome, type HistoryStep, type Place } from "../history";
import type { ConnectionRefusal, GraphContext, GraphRules } from "./GraphRules";
import { isConnectionElement, isNodeElement, isPendingId, normalizeName, pendingId, type ConnectionObject, type GraphElement, type NodeObject, type RegistryLike } from "./model";
import { NODE_HEIGHT, NODE_WIDTH } from "./shapes";

/** Moves are saved together, this long after the last one. */
export const MOVE_SAVE_DELAY_MS = 400;

/** The edit was not sent: the canvas is read-only, the connection breaks a rule, or an element is gone. `cause` tells which. */
export class EditRefused extends Error {
  constructor(readonly cause: ConnectionRefusal | "read_only" | "missing") {
    super(`edit refused: ${cause}`);
  }
}

type Stack = CommandStack & { _stackIdx: number };
type Handler = { execute(context: UpdateContext): GraphElement[]; revert(context: UpdateContext): GraphElement[] };
type UpdateContext = { element: GraphElement; name: string; description: string | null; before?: NodeObject };

/** The one command Shadow adds to the command stack: renaming or re-describing a node. The built-in commands cover create, move, delete and connect. */
export class UpdateNodeHandler implements Handler {
  static $inject = [];

  execute(context: UpdateContext) {
    const current = context.element.businessObject as NodeObject;
    context.before = current;
    context.element.businessObject = { ...current, node: { ...current.node, name: context.name, description: context.description } };
    return [context.element];
  }

  revert(context: UpdateContext) {
    if (context.before) context.element.businessObject = context.before;
    return [context.element];
  }
}

/**
 * The single seam between the diagram and the server. `applyEdit` runs the change on the command stack at once (so the person sees it),
 * sends the same change through the sender, and when the sender rejects undoes the change and passes the error on. The sender is where
 * the server write lives: the model's event routes today, whichever target a later ticket chooses. A move made with the mouse is already
 * on the stack when it happens, so it is only collected here and sent in one batch after a short quiet time.
 *
 * A successful edit also goes into the session `history` (see `history.ts`) with the write that undoes it; `undo` and `redo` run those
 * writes through the same sender. They draw nothing themselves: the load that follows every write brings the diagram up to date.
 */
export class GraphModeling {
  static $inject = ["modeling", "commandStack", "eventBus", "canvas", "elementRegistry", "graphContext", "graphRules"];

  /** The person's undo and redo stacks for this diagram (cleared when it is destroyed or the owner calls `clear`). */
  readonly history = new GraphHistory();

  private send: GraphEditSender | null = null;
  private read: (() => Promise<GraphData | null>) | null = null;
  private isRefusal: (error: unknown) => boolean = () => false;
  private report: ((outcome: HistoryOutcome) => void) | null = null;
  private readonly moves = new Map<string, Place>();
  /** Where the moved nodes were before the batch started (kept exactly, not rounded): what an undo puts back. */
  private readonly origins = new Map<string, Place>();
  private batch: { before: number; after: number } | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly modeling: Modeling,
    private readonly commandStack: CommandStack,
    eventBus: EventBus,
    private readonly canvas: Canvas,
    private readonly registry: RegistryLike,
    private readonly context: GraphContext,
    private readonly rules: GraphRules,
  ) {
    eventBus.on("diagram.init", () => commandStack.registerHandler("shadow.node.update", UpdateNodeHandler as never));
    eventBus.on("commandStack.elements.move.postExecuted", (event: { context: { shapes: GraphElement[]; delta: Place } }) => {
      for (const shape of event.context.shapes) {
        if (!isNodeElement(shape)) continue;
        if (!this.origins.has(shape.id)) this.origins.set(shape.id, { x: shape.x - event.context.delta.x, y: shape.y - event.context.delta.y });
        this.moves.set(shape.id, { x: Math.round(shape.x), y: Math.round(shape.y) });
      }
      this.batch ??= { before: -1, after: -1 };
      this.schedule();
    });
    eventBus.on("diagram.destroy", () => { if (this.timer) clearTimeout(this.timer); this.timer = null; this.history.clear(); });
    eventBus.on("commandStack.changed", (event: { trigger: string | null }) => {
      if (event.trigger !== "execute" || !this.batch) return;
      this.batch.after = this.index();
      if (this.batch.before < 0) this.batch.before = this.batch.after - 1;
    });
  }

  setSender(send: GraphEditSender | null) {
    this.send = send;
  }

  /** What the history needs from its owner: a fresh read of the state, and which errors are refusals of the server. */
  setHistoryPort(port: { read: (() => Promise<GraphData | null>) | null; isRefusal?: (error: unknown) => boolean; report?: ((outcome: HistoryOutcome) => void) | null }) {
    this.read = port.read;
    this.isRefusal = port.isRefusal ?? (() => false);
    this.report = port.report ?? null;
  }

  hasUnsavedMove(id: string) {
    return this.moves.has(id);
  }

  /** Undoes the person's last step: the inverse write after a fresh read; the outcome is reported to the port's `report` too. */
  undo(): Promise<HistoryOutcome> { return this.runHistory("undo"); }
  redo(): Promise<HistoryOutcome> { return this.runHistory("redo"); }

  private async runHistory(direction: "undo" | "redo"): Promise<HistoryOutcome> {
    if (this.context.readOnly || !this.read) return { status: "idle" };
    if (this.moves.size > 0) await this.flush();
    const read = this.read;
    const outcome = await this.history[direction]({ fresh: () => read(), write: (edit) => this.dispatch(edit), isRefusal: (error) => this.isRefusal(error) });
    if (outcome.status !== "idle") this.report?.(outcome);
    return outcome;
  }

  /** Sends the collected moves now (the canvas is being closed, or the quiet time is over). */
  async flush(): Promise<void> {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    if (this.moves.size === 0) return;
    const moves = [...this.moves].map(([id, at]) => ({ id, ...at }));
    const origins = new Map(this.origins);
    const batch = this.batch ?? { before: this.index(), after: this.index() };
    this.moves.clear();
    this.origins.clear();
    this.batch = null;
    try {
      await this.dispatch({ kind: "node.move", moves });
      const changed = moves.filter((move) => { const from = origins.get(move.id); return !from || Math.abs(from.x - move.x) > 0.5 || Math.abs(from.y - move.y) > 0.5; });
      const known = changed.filter((move) => origins.has(move.id) && !isPendingId(move.id));
      if (known.length > 0) {
        const step = (direction: "to" | "from"): HistoryStep => ({ kind: "node.move", moves: known.map((move) => ({ ref: move.id, to: direction === "to" ? { x: move.x, y: move.y } : origins.get(move.id)!, from: direction === "to" ? origins.get(move.id)! : { x: move.x, y: move.y } })) });
        this.history.record({ label: "move", undo: [step("from")], redo: [step("to")] });
      }
    } catch {
      this.rollback(batch.before, batch.after);
    }
  }

  /** Runs an edit optimistically and sends it; rejects when it is refused (before sending, or by the server, in which case the change was undone). */
  async applyEdit(edit: GraphEdit): Promise<void> {
    if (this.context.readOnly) throw new EditRefused("read_only");
    if (edit.kind === "node.move") {
      for (const move of edit.moves) {
        const shape = this.registry.get(move.id);
        if (shape) this.modeling.moveElements([shape as never], { x: move.x - shape.x, y: move.y - shape.y });
      }
      return this.flush();
    }
    // Moves still waiting for their quiet time are written first: the writes keep their order and the history holds the move before this edit.
    if (this.moves.size > 0) void this.flush();
    switch (edit.kind) {
      case "node.delete": return this.deleteElements({ nodeIds: [edit.id], connectionIds: [] });
      case "connection.delete": return this.deleteElements({ nodeIds: [], connectionIds: [edit.id] });
      case "elements.delete": return this.deleteElements(edit);
      case "connection.reroute": return this.reroute(edit);
    }
    const before = this.index();
    const sent = edit.kind === "node.create" || edit.kind === "node.update" ? { ...edit, name: normalizeName(edit.name) } : edit;
    const undoable = this.entryFor(sent);
    this.optimistic(sent);
    const after = this.index();
    let result: EditResult;
    try {
      result = await this.dispatch(sent);
    } catch (error) {
      this.rollback(before, after);
      throw error;
    }
    const entry = undoable?.(result);
    if (entry) this.history.record(entry);
  }

  /** A function that builds the history entry once the write has answered (a created element's id is only known then), or null when nothing can be undone. Reads the diagram now, before the edit changes it. */
  private entryFor(edit: GraphEdit): ((result: EditResult) => { label: "create" | "rename" | "connect"; undo: HistoryStep[]; redo: HistoryStep[] } | null) | null {
    switch (edit.kind) {
      case "node.create": {
        const description = edit.description ?? null;
        return (result) => {
          const ref = result && result.id;
          if (!ref) return null;
          return {
            label: "create",
            undo: [{ kind: "node.delete", ref, expect: { name: edit.name, description, nodeTypeId: edit.nodeTypeId }, touching: [] }],
            redo: [{ kind: "node.create", ref, nodeTypeId: edit.nodeTypeId, name: edit.name, description, x: edit.x, y: edit.y }],
          };
        };
      }
      case "node.update": {
        const element = this.registry.get(edit.id);
        const old = element && isNodeElement(element) && !isPendingId(element.id) ? element.businessObject.node : null;
        if (!old || (old.name === edit.name && (old.description ?? null) === edit.description)) return null;
        const was = { name: old.name, description: old.description ?? null };
        const now = { name: edit.name, description: edit.description };
        return () => ({
          label: "rename",
          undo: [{ kind: "node.update", ref: edit.id, ...was, expect: now }],
          redo: [{ kind: "node.update", ref: edit.id, ...now, expect: was }],
        });
      }
      case "connection.create": {
        return (result) => {
          const ref = result && result.id;
          if (!ref) return null;
          const snapshot: ConnectionSnapshot = { connectionTypeId: edit.connectionTypeId, sourceRef: edit.sourceId, targetRef: edit.targetId };
          return {
            label: "connect",
            undo: [{ kind: "connection.delete", ref, expect: snapshot }],
            redo: [{ kind: "connection.create", ref, ...snapshot }],
          };
        };
      }
      default:
        return null;
    }
  }

  /** Deleting nodes and connections together: one command on the stack, one write, one history entry. The connections touching a deleted node leave with it (the server does the same). */
  private async deleteElements(edit: { nodeIds: string[]; connectionIds: string[] }): Promise<void> {
    const nodes = [...new Set(edit.nodeIds)].map((id) => this.element(id)).filter(isNodeElement);
    const nodeIds = new Set(nodes.map((node) => node.id));
    const touching = new Map<string, GraphElement & { businessObject: ConnectionObject }>();
    for (const node of nodes) for (const item of [...node.incoming, ...node.outgoing]) if (isConnectionElement(item)) touching.set(item.id, item);
    const alone = [...new Set(edit.connectionIds)].map((id) => this.element(id)).filter(isConnectionElement).filter((item) => !touching.has(item.id));
    if (nodes.length + alone.length === 0) return;

    const snapshot = (item: GraphElement & { businessObject: ConnectionObject }): ConnectionSnapshot => ({ connectionTypeId: item.businessObject.connection.connection_type_id, sourceRef: item.source?.id ?? item.businessObject.connection.source_node_id, targetRef: item.target?.id ?? item.businessObject.connection.target_node_id });
    const refs = [...nodes.map((node) => node.id), ...alone.map((item) => item.id), ...touching.keys()];
    const record = refs.every((id) => !isPendingId(id));
    const everyConnection = [...touching.values(), ...alone];
    const entry = record ? {
      label: "delete" as const,
      redo: [
        ...alone.map((item): HistoryStep => ({ kind: "connection.delete", ref: item.id, expect: snapshot(item) })),
        ...nodes.map((node): HistoryStep => ({
          kind: "node.delete", ref: node.id,
          expect: { name: node.businessObject.node.name, description: node.businessObject.node.description ?? null, nodeTypeId: node.businessObject.node.node_type_id },
          touching: [...touching.values()].filter((item) => item.source === node || item.target === node).map(snapshot),
        })),
      ],
      undo: [
        ...nodes.map((node): HistoryStep => ({ kind: "node.create", ref: node.id, nodeTypeId: node.businessObject.node.node_type_id, name: node.businessObject.node.name, description: node.businessObject.node.description ?? null, x: Math.round(node.x), y: Math.round(node.y) })),
        ...everyConnection.map((item): HistoryStep => ({ kind: "connection.create", ref: item.id, ...snapshot(item) })),
      ],
    } : null;

    const before = this.index();
    this.modeling.removeElements([...nodes, ...alone] as never[]);
    const after = this.index();
    try {
      await this.dispatch({ kind: "elements.delete", nodeIds: [...nodeIds], connectionIds: alone.map((item) => item.id) });
    } catch (error) {
      this.rollback(before, after);
      throw error;
    }
    if (entry) this.history.record(entry);
  }

  /** Points a connection at other nodes. It is not drawn ahead: the load after the write moves it. */
  private async reroute(edit: Extract<GraphEdit, { kind: "connection.reroute" }>): Promise<void> {
    const connection = this.element(edit.id);
    if (!isConnectionElement(connection)) throw new EditRefused("missing");
    const source = this.element(edit.sourceId);
    const target = this.element(edit.targetId);
    const old = { sourceRef: connection.source?.id ?? connection.businessObject.connection.source_node_id, targetRef: connection.target?.id ?? connection.businessObject.connection.target_node_id };
    if (old.sourceRef === edit.sourceId && old.targetRef === edit.targetId) return;
    const check = this.rules.checkConnection(connection.businessObject.connection.connection_type_id, source, target, connection.id);
    if (!check.allowed) throw new EditRefused(check.cause);
    await this.dispatch(edit);
    if (isPendingId(edit.id) || isPendingId(edit.sourceId) || isPendingId(edit.targetId)) return;
    const now = { sourceRef: edit.sourceId, targetRef: edit.targetId };
    this.history.record({
      label: "reroute",
      undo: [{ kind: "connection.reroute", ref: edit.id, ...old, expect: now }],
      redo: [{ kind: "connection.reroute", ref: edit.id, ...now, expect: old }],
    });
  }

  private dispatch(edit: GraphEdit): Promise<EditResult> {
    return this.send ? this.send(edit) : Promise.reject(new Error("no sender"));
  }

  private schedule() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.flush(), MOVE_SAVE_DELAY_MS);
  }

  private index() {
    return (this.commandStack as Stack)._stackIdx;
  }

  /** Undoes what an edit did, unless something else has been done since (then the next load puts the server's state back). */
  private rollback(before: number, after: number) {
    if (this.index() !== after) return;
    while (this.index() > before && this.commandStack.canUndo()) this.commandStack.undo();
  }

  private element(id: string): GraphElement {
    const element = this.registry.get(id);
    if (!element) throw new EditRefused("missing");
    return element;
  }

  private optimistic(edit: GraphEdit) {
    const root = this.canvas.getRootElement();
    switch (edit.kind) {
      case "node.create": {
        const businessObject: NodeObject = {
          kind: "node",
          node: { id: pendingId(), node_type_id: edit.nodeTypeId, name: edit.name, description: edit.description ?? null, x: edit.x, y: edit.y },
          nodeType: this.context.nodeTypes.find((type) => type.id === edit.nodeTypeId),
          change: null,
          pending: true,
        };
        // A load replaces this element with the real one.
        this.modeling.createShape({ id: businessObject.node.id, width: NODE_WIDTH, height: NODE_HEIGHT, businessObject } as never, { x: edit.x + NODE_WIDTH / 2, y: edit.y + NODE_HEIGHT / 2 }, root as never);
        return;
      }
      case "node.update":
        this.commandStack.execute("shadow.node.update", { element: this.element(edit.id), name: edit.name, description: edit.description });
        return;
      case "connection.create": {
        const source = this.element(edit.sourceId);
        const target = this.element(edit.targetId);
        const check = this.rules.checkConnection(edit.connectionTypeId, source, target);
        if (!check.allowed) throw new EditRefused(check.cause);
        const connectionType = this.context.connectionTypes.find((type) => type.id === edit.connectionTypeId);
        const id = pendingId();
        this.modeling.connect(source as never, target as never, {
          id,
          businessObject: { kind: "connection", connection: { id, connection_type_id: edit.connectionTypeId, source_node_id: edit.sourceId, target_node_id: edit.targetId }, connectionType, change: null, pending: true },
        } as never);
        return;
      }
      default:
        return;
    }
  }
}
