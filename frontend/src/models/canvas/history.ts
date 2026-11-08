import type { EditResult, GraphData, GraphEdit } from "./graph-types";

/**
 * The person's session history on the canvas: one undo stack and one redo stack of entries, in memory only. Each entry carries the
 * server counterpart of itself in both directions as plain steps (create, delete, rename, re-route, connect, move), so an undo is
 * "write the inverse" and a redo is "write it again". Nothing here knows diagram-js or the routes: the diagram's command stack only
 * draws the optimistic change, and this journal is keyed by element id, because ids change underneath it (a node deleted and then
 * brought back by an undo is a new element on the server; `aliases` follows it, so older entries still find it).
 *
 * Before an entry runs, the state is read afresh and every step is checked against it: if the element is gone or somebody changed it
 * since (a different name, other connections, another place), the entry is refused and dropped, and the stacks stay as they were
 * otherwise. If the server rejects a write (409 stale, 422 chain broken, anything else after the first step) the entry is dropped too.
 */

export type NodeSnapshot = { name: string; description: string | null; nodeTypeId: string };
export type ConnectionSnapshot = { connectionTypeId: string; sourceRef: string; targetRef: string };
export type Place = { x: number; y: number };

export type HistoryStep =
  | { kind: "node.create"; ref: string; nodeTypeId: string; name: string; description: string | null; x: number; y: number }
  /** `touching` is what must be attached to the node when it goes: its connections (they leave with it). */
  | { kind: "node.delete"; ref: string; expect: NodeSnapshot; touching: ConnectionSnapshot[] }
  | { kind: "node.update"; ref: string; name: string; description: string | null; expect: { name: string; description: string | null } }
  | { kind: "node.move"; moves: { ref: string; to: Place; from: Place }[] }
  | { kind: "connection.create"; ref: string; connectionTypeId: string; sourceRef: string; targetRef: string }
  | { kind: "connection.delete"; ref: string; expect: ConnectionSnapshot }
  | { kind: "connection.reroute"; ref: string; sourceRef: string; targetRef: string; expect: { sourceRef: string; targetRef: string } };

export type HistoryLabel = "create" | "delete" | "rename" | "connect" | "move" | "reroute";
export type HistoryEntry = { label: HistoryLabel; undo: HistoryStep[]; redo: HistoryStep[] };
export type HistoryDirection = "undo" | "redo";
export type HistoryState = { canUndo: boolean; canRedo: boolean; busy: boolean };

/** How the canvas reaches the server for the history: a fresh read of the state, and one write at a time. */
export type HistoryPort = {
  fresh(): Promise<GraphData | null>;
  write(edit: GraphEdit): Promise<EditResult>;
  /** True for a refusal of the server (stale version, a rule, a broken chain): the entry can never apply as it is and is dropped even when nothing was written yet. Anything else (a network failure) keeps it. */
  isRefusal(error: unknown): boolean;
};

export type HistoryOutcome =
  | { status: "idle" }
  | { status: "done"; direction: HistoryDirection; label: HistoryLabel }
  /** The entry could not be applied because an element is gone or somebody changed it; it was dropped. */
  | { status: "refused"; direction: HistoryDirection; label: HistoryLabel; reason: "missing" | "changed" }
  /** The server refused a write (or the read failed). `dropped` says whether the entry left the stacks; a failure before the first write keeps it. */
  | { status: "rejected"; direction: HistoryDirection; label: HistoryLabel; error: unknown; dropped: boolean };

const MAX_ENTRIES = 200;
/** Positions are floats on the server and whole numbers when the canvas writes them. */
const SAME_PLACE = 0.5;

const connectionKey = (type: string, source: string, target: string) => `${type}|${source}|${target}`;

export class GraphHistory {
  private undoStack: HistoryEntry[] = [];
  private redoStack: HistoryEntry[] = [];
  private readonly aliases = new Map<string, string>();
  private running = false;
  private readonly listeners = new Set<(state: HistoryState) => void>();

  get state(): HistoryState {
    return { canUndo: this.undoStack.length > 0, canRedo: this.redoStack.length > 0, busy: this.running };
  }

  subscribe(listener: (state: HistoryState) => void): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  /** Adds an entry the person just made; a new edit ends the redo line. */
  record(entry: HistoryEntry): void {
    this.undoStack.push(entry);
    if (this.undoStack.length > MAX_ENTRIES) this.undoStack.shift();
    this.redoStack = [];
    this.emit();
  }

  /** Forgets everything: the line or event changed, or the canvas closed. */
  clear(): void {
    this.undoStack = [];
    this.redoStack = [];
    this.aliases.clear();
    this.emit();
  }

  /** The labels of the entries, oldest first (for tests and announcements). */
  labels(): { undo: HistoryLabel[]; redo: HistoryLabel[] } {
    return { undo: this.undoStack.map((entry) => entry.label), redo: this.redoStack.map((entry) => entry.label) };
  }

  /** The id an element has now, following the ids it was given when it was brought back. */
  resolve(ref: string): string {
    let id = ref;
    for (let hops = 0; hops < 50; hops++) {
      const next = this.aliases.get(id);
      if (next === undefined || next === id) return id;
      id = next;
    }
    return id;
  }

  undo(port: HistoryPort): Promise<HistoryOutcome> { return this.run("undo", port); }
  redo(port: HistoryPort): Promise<HistoryOutcome> { return this.run("redo", port); }

  private emit() {
    const state = this.state;
    for (const listener of this.listeners) listener(state);
  }

  private async run(direction: HistoryDirection, port: HistoryPort): Promise<HistoryOutcome> {
    const from = direction === "undo" ? this.undoStack : this.redoStack;
    const entry = from[from.length - 1];
    if (!entry || this.running) return { status: "idle" };
    const label = entry.label;
    const steps = direction === "undo" ? entry.undo : entry.redo;
    this.running = true;
    this.emit();
    const drop = () => { from.pop(); };
    let written = 0;
    try {
      let graph: GraphData | null;
      try {
        graph = await port.fresh();
      } catch (error) {
        return { status: "rejected", direction, label, error, dropped: false };
      }
      if (!graph) return { status: "rejected", direction, label, error: new Error("read failed"), dropped: false };
      const refusal = this.check(steps, graph);
      if (refusal) {
        drop();
        return { status: "refused", direction, label, reason: refusal };
      }
      for (const step of steps) {
        const result = await port.write(this.edit(step));
        written++;
        if ((step.kind === "node.create" || step.kind === "connection.create") && result && result.id && result.id !== step.ref) this.aliases.set(step.ref, result.id);
      }
      drop();
      (direction === "undo" ? this.redoStack : this.undoStack).push(entry);
      return { status: "done", direction, label };
    } catch (error) {
      // Nothing was written: the entry can be tried again (a network failure). After the first write the entry is half done and cannot be offered again.
      const dropped = written > 0 || port.isRefusal(error);
      if (dropped) drop();
      return { status: "rejected", direction, label, error, dropped };
    } finally {
      this.running = false;
      this.emit();
    }
  }

  /** The write for a step, with the ids the elements have now. */
  private edit(step: HistoryStep): GraphEdit {
    switch (step.kind) {
      case "node.create": return { kind: "node.create", nodeTypeId: step.nodeTypeId, name: step.name, description: step.description, x: step.x, y: step.y };
      case "node.delete": return { kind: "node.delete", id: this.resolve(step.ref) };
      case "node.update": return { kind: "node.update", id: this.resolve(step.ref), name: step.name, description: step.description };
      case "node.move": return { kind: "node.move", moves: step.moves.map((move) => ({ id: this.resolve(move.ref), x: move.to.x, y: move.to.y })) };
      case "connection.create": return { kind: "connection.create", connectionTypeId: step.connectionTypeId, sourceId: this.resolve(step.sourceRef), targetId: this.resolve(step.targetRef) };
      case "connection.delete": return { kind: "connection.delete", id: this.resolve(step.ref) };
      case "connection.reroute": return { kind: "connection.reroute", id: this.resolve(step.ref), sourceId: this.resolve(step.sourceRef), targetId: this.resolve(step.targetRef) };
    }
  }

  /**
   * Whether the steps still fit the state read just now. An element a step needs must exist (unless an earlier step of the entry
   * creates it) and must still be what the entry left: the same name and description, the same connections, the same ends, the same place.
   */
  private check(steps: HistoryStep[], graph: GraphData): "missing" | "changed" | null {
    const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
    const connections = new Map(graph.connections.map((connection) => [connection.id, connection]));
    const nodeTypes = new Set(graph.nodeTypes.map((type) => type.id));
    const connectionTypes = new Set(graph.connectionTypes.map((type) => type.id));
    const created = new Set<string>();
    const deleted = new Set<string>();
    const present = (ref: string) => created.has(ref) || (!deleted.has(ref) && nodes.has(this.resolve(ref)));

    for (const step of steps) {
      switch (step.kind) {
        case "node.create":
          if (!nodeTypes.has(step.nodeTypeId)) return "missing";
          created.add(step.ref);
          break;
        case "node.delete": {
          const node = nodes.get(this.resolve(step.ref));
          if (!node) return "missing";
          if (node.name !== step.expect.name || (node.description ?? null) !== step.expect.description || node.node_type_id !== step.expect.nodeTypeId) return "changed";
          const wanted = step.touching.map((item) => connectionKey(item.connectionTypeId, this.resolve(item.sourceRef), this.resolve(item.targetRef))).sort();
          const actual = graph.connections.filter((item) => item.source_node_id === node.id || item.target_node_id === node.id).map((item) => connectionKey(item.connection_type_id, item.source_node_id, item.target_node_id)).sort();
          if (wanted.length !== actual.length || wanted.some((key, at) => key !== actual[at])) return "changed";
          deleted.add(step.ref);
          break;
        }
        case "node.update": {
          const node = nodes.get(this.resolve(step.ref));
          if (!node) return "missing";
          if (node.name !== step.expect.name || (node.description ?? null) !== step.expect.description) return "changed";
          break;
        }
        case "node.move": {
          for (const move of step.moves) {
            const node = nodes.get(this.resolve(move.ref));
            if (!node) return "missing";
            if (Math.abs(node.x - move.from.x) > SAME_PLACE || Math.abs(node.y - move.from.y) > SAME_PLACE) return "changed";
          }
          break;
        }
        case "connection.create":
          if (!connectionTypes.has(step.connectionTypeId)) return "missing";
          if (!present(step.sourceRef) || !present(step.targetRef)) return "missing";
          created.add(step.ref);
          break;
        case "connection.delete": {
          const connection = connections.get(this.resolve(step.ref));
          if (!connection) return "missing";
          if (!sameConnection(connection, step.expect, (ref) => this.resolve(ref))) return "changed";
          break;
        }
        case "connection.reroute": {
          const connection = connections.get(this.resolve(step.ref));
          if (!connection) return "missing";
          if (connection.source_node_id !== this.resolve(step.expect.sourceRef) || connection.target_node_id !== this.resolve(step.expect.targetRef)) return "changed";
          if (!present(step.sourceRef) || !present(step.targetRef)) return "missing";
          break;
        }
      }
    }
    return null;
  }
}

const sameConnection = (connection: GraphData["connections"][number], expect: ConnectionSnapshot, resolve: (ref: string) => string) =>
  connection.connection_type_id === expect.connectionTypeId && connection.source_node_id === resolve(expect.sourceRef) && connection.target_node_id === resolve(expect.targetRef);
