import type Canvas from "diagram-js/lib/core/Canvas.js";
import type CommandStack from "diagram-js/lib/command/CommandStack.js";
import type EventBus from "diagram-js/lib/core/EventBus.js";
import type Modeling from "diagram-js/lib/features/modeling/Modeling.js";

import type { GraphEdit, GraphEditSender } from "../graph-types";
import type { ConnectionRefusal, GraphContext, GraphRules } from "./GraphRules";
import { isConnectionElement, isNodeElement, pendingId, type GraphElement, type NodeObject, type RegistryLike } from "./model";
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
 */
export class GraphModeling {
  static $inject = ["modeling", "commandStack", "eventBus", "canvas", "elementRegistry", "graphContext", "graphRules"];

  private send: GraphEditSender | null = null;
  private readonly moves = new Map<string, { x: number; y: number }>();
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
    eventBus.on("commandStack.elements.move.postExecuted", (event: { context: { shapes: GraphElement[] } }) => {
      for (const shape of event.context.shapes) this.moves.set(shape.id, { x: Math.round(shape.x), y: Math.round(shape.y) });
      this.batch ??= { before: -1, after: -1 };
      this.schedule();
    });
    eventBus.on("diagram.destroy", () => { if (this.timer) clearTimeout(this.timer); this.timer = null; });
    eventBus.on("commandStack.changed", (event: { trigger: string | null }) => {
      if (event.trigger !== "execute" || !this.batch) return;
      this.batch.after = this.index();
      if (this.batch.before < 0) this.batch.before = this.batch.after - 1;
    });
  }

  setSender(send: GraphEditSender | null) {
    this.send = send;
  }

  hasUnsavedMove(id: string) {
    return this.moves.has(id);
  }

  /** Sends the collected moves now (the canvas is being closed, or the quiet time is over). */
  async flush(): Promise<void> {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    if (this.moves.size === 0) return;
    const moves = [...this.moves].map(([id, at]) => ({ id, ...at }));
    const batch = this.batch ?? { before: this.index(), after: this.index() };
    this.moves.clear();
    this.batch = null;
    try {
      await this.dispatch({ kind: "node.move", moves });
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
    const before = this.index();
    this.optimistic(edit);
    const after = this.index();
    try {
      await this.dispatch(edit);
    } catch (error) {
      this.rollback(before, after);
      throw error;
    }
  }

  private dispatch(edit: GraphEdit): Promise<void> {
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
          node: { id: pendingId(), node_type_id: edit.nodeTypeId, name: edit.name, description: null, x: edit.x, y: edit.y },
          nodeType: undefined,
          change: null,
          pending: true,
        };
        // The type is looked up from a sibling of the same type, if there is one; a load replaces this element with the real one anyway.
        const sibling = this.registry.filter(isNodeElement).find((item) => item.businessObject.kind === "node" && (item.businessObject as NodeObject).node.node_type_id === edit.nodeTypeId);
        businessObject.nodeType = (sibling?.businessObject as NodeObject | undefined)?.nodeType;
        this.modeling.createShape({ id: businessObject.node.id, width: NODE_WIDTH, height: NODE_HEIGHT, businessObject } as never, { x: edit.x + NODE_WIDTH / 2, y: edit.y + NODE_HEIGHT / 2 }, root as never);
        return;
      }
      case "node.update":
        this.commandStack.execute("shadow.node.update", { element: this.element(edit.id), name: edit.name, description: edit.description });
        return;
      case "node.delete":
        this.modeling.removeElements([this.element(edit.id) as never]);
        return;
      case "connection.delete":
        this.modeling.removeElements([this.element(edit.id) as never]);
        return;
      case "connection.create": {
        const source = this.element(edit.sourceId);
        const target = this.element(edit.targetId);
        const check = this.rules.checkConnection(edit.connectionTypeId, source, target);
        if (!check.allowed) throw new EditRefused(check.cause);
        const sibling = this.registry.filter(isConnectionElement).find((item) => (item.businessObject as { connection: { connection_type_id: string } }).connection.connection_type_id === edit.connectionTypeId);
        const connectionType = (sibling?.businessObject as { connectionType?: never } | undefined)?.connectionType;
        const id = pendingId();
        this.modeling.connect(source as never, target as never, {
          id,
          businessObject: { kind: "connection", connection: { id, connection_type_id: edit.connectionTypeId, source_node_id: edit.sourceId, target_node_id: edit.targetId }, connectionType, change: null, pending: true },
        } as never);
        return;
      }
    }
  }
}
