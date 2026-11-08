import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";

import { useOrganization } from "../shell/organization-outlet";
import { useModel } from "./ModelShell";
import { Alert, Button, Dialog, Field, IconButton, Select, TextArea, TextInput, cx, useConfirm } from "../ui";
import {
  ChainBrokenError, createConnection, createEditsEvent, createNode, deleteConnection, deleteNode, RuleError, saveNodePositions, StaleVersionError, updateConnection, updateNode,
  type GraphConnection, type GraphNode, type LineEvent,
} from "./client";
import { EditRefused } from "./canvas/diagram";
import { deleteSummary, planConnection } from "./canvas/draw";
import type { HistoryOutcome } from "./canvas/history";
import type { EditResult, GraphData, GraphEdit } from "./canvas/graph-types";
import { ShadowCanvas, type CanvasTarget, type ShadowCanvasHandle } from "./canvas/ShadowCanvas";
import { useCanvasView } from "./canvas/useCanvasView";
import { TypePanel } from "./canvas/TypePanel";
import { readTypeCollapse, writeTypeCollapse, type TypeCollapse } from "./canvas/type-collapse";
import { groupNodes, hideAllTypes, searchMatches, showAllTypes, toggleType, type CanvasFilter } from "./canvas/type-list";
import { useGraphState } from "./canvas/useGraphState";
import { modelMessages } from "./messages";
import { readPanels, writePanels, type PanelState } from "./panel-state";

const MIN_CANVAS_HEIGHT = 320;
const SHEET_HANDLE = 48;

/** The height that makes the element end at the bottom of the viewport, so the page itself does not scroll. Re-measured when the window or the content above changes. */
function useFillHeight(ref: RefObject<HTMLElement | null>, reserve: number) {
  const [height, setHeight] = useState(480);
  useLayoutEffect(() => {
    const update = () => {
      const top = ref.current?.getBoundingClientRect().top ?? 0;
      // 12 px is the bottom padding of the wide page.
      setHeight(Math.max(MIN_CANVAS_HEIGHT, Math.floor(window.innerHeight - top - 12 - reserve)));
    };
    update();
    window.addEventListener("resize", update);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(document.body);
    return () => { window.removeEventListener("resize", update); observer?.disconnect(); };
  }, [ref, reserve]);
  return height;
}

function useIsPhone() {
  const query = "(max-width: 767px)";
  const [phone, setPhone] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const change = () => setPhone(list.matches);
    list.addEventListener("change", change);
    return () => list.removeEventListener("change", change);
  }, []);
  return phone;
}

/** `/organizations/:organizationId/models/:modelId`: the nodes and connections of a line on a canvas. Edits are changes of the line's last event (ticket 09 of the model timeline adds the event list and the choice of event). */
export function ModelCanvas() {
  const { locale } = useOrganization();
  const { organizationId, modelId, line, writable } = useModel();
  const lineId = line.id;
  const text = modelMessages(locale);
  const source = useMemo(() => ({ organizationId, modelId, lineId }), [organizationId, modelId, lineId]);
  const { graph, event, status, reload } = useGraphState(source);
  // The view (pan and zoom) is kept while this line stays open on this tab; another line or another tab starts fresh.
  const view = useCanvasView(`${organizationId}|${modelId}|${lineId}`);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<readonly string[]>([]);
  // Exactly one selected element is shown in the details; several show a count and Delete.
  const selectedId = selectedIds.length === 1 ? selectedIds[0] : null;
  const setSelectedId = (id: string | null) => setSelectedIds(id ? [id] : []);
  // Connect mode: the node to connect from (null until it is clicked) and, when the panel started it, the connection type to use.
  const [connecting, setConnecting] = useState<{ sourceId: string | null; connectionTypeId: string | null } | null>(null);
  const [picker, setPicker] = useState<{ sourceId: string; targetId: string; types: { id: string; name: string }[] } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const confirm = useConfirm();
  const canvas = useRef<ShadowCanvasHandle>(null);
  const area = useRef<HTMLDivElement>(null);
  const phone = useIsPhone();
  const [panels, setPanels] = useState<PanelState>(() => readPanels());
  const [sheetOpen, setSheetOpen] = useState(false);
  const areaHeight = useFillHeight(area, phone ? SHEET_HANDLE : 0);
  // The type panel: which types are hidden and the search live in memory; the collapse choices are remembered per model.
  const [hiddenTypes, setHiddenTypes] = useState<ReadonlySet<string>>(() => new Set());
  const [query, setQuery] = useState("");
  const [collapse, setCollapse] = useState<TypeCollapse>(() => readTypeCollapse(modelId));
  const searchInput = useRef<HTMLInputElement>(null);
  const toggle = (side: keyof PanelState) => setPanels((old) => { const next = { ...old, [side]: !old[side] }; writePanels(next); return next; });

  // Edits of an event go one after the other, each against the event's current version, which is read again after every write.
  const editTarget = useRef<LineEvent | null>(null);
  editTarget.current = event;
  const queue = useRef<Promise<unknown>>(Promise.resolve());

  const nodes = graph?.nodes ?? [];
  const byId = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const groups = useMemo(() => (graph ? groupNodes(graph) : []), [graph]);
  const found = useMemo(() => searchMatches(groups, query, hiddenTypes), [groups, query, hiddenTypes]);
  const filter = useMemo<CanvasFilter>(() => ({ hiddenTypeIds: hiddenTypes, matchIds: found ? new Set(found.map((node) => node.id)) : null }), [hiddenTypes, found]);
  const matchIds = filter.matchIds;
  const connectionTypes = useMemo(() => new Map((graph?.connectionTypes ?? []).map((type) => [type.id, type])), [graph]);
  const selectedNode = selectedId ? byId.get(selectedId) : undefined;
  const selectedConnection = selectedId && !selectedNode ? graph?.connections.find((item) => item.id === selectedId) : undefined;

  const noticeFor = (cause: unknown, rule: string) =>
    cause instanceof StaleVersionError ? text.stale : cause instanceof ChainBrokenError ? text.chainBroken : cause instanceof RuleError ? rule : text.failed;

  /** The canvas calls this for every edit it has already drawn; a rejection makes it undo the drawing. The server's answer is then loaded. */
  const send = (edit: GraphEdit): Promise<EditResult> => {
    const run = async (): Promise<EditResult> => {
      setNotice(null);
      try {
        if (edit.kind === "node.move") {
          // A move is a position of the line, not an edit of an event.
          await saveNodePositions(organizationId, modelId, lineId, edit.moves.map((move) => ({ node_id: move.id, x: move.x, y: move.y })));
          return undefined;
        }
        // A line that has no event yet gets an "Edits" event first.
        const target = editTarget.current ?? await createEditsEvent(organizationId, modelId, lineId, text.editsEvent);
        switch (edit.kind) {
          case "node.create": return { id: (await createNode(organizationId, modelId, target, { node_type_id: edit.nodeTypeId, name: edit.name, description: edit.description ?? null, x: edit.x, y: edit.y })).id };
          case "node.update": await updateNode(organizationId, modelId, target, byId.get(edit.id) ?? ({ id: edit.id } as GraphNode), { name: edit.name, description: edit.description }); break;
          case "node.delete": await deleteNode(organizationId, modelId, target, { id: edit.id } as GraphNode); break;
          case "connection.create": return await createConnection(organizationId, modelId, target, { connection_type_id: edit.connectionTypeId, source_node_id: edit.sourceId, target_node_id: edit.targetId });
          case "connection.delete": await deleteConnection(organizationId, modelId, target, { id: edit.id } as GraphConnection); break;
          case "connection.reroute": await updateConnection(organizationId, modelId, target, { id: edit.id } as GraphConnection, { source_node_id: edit.sourceId, target_node_id: edit.targetId }); break;
          case "elements.delete": {
            // Each delete changes the event's version by one; the answer of a delete carries none, so the next one counts on from here.
            let version = target.version;
            for (const id of edit.connectionIds) { await deleteConnection(organizationId, modelId, { ...target, version }, { id } as GraphConnection); version++; }
            for (const id of edit.nodeIds) { await deleteNode(organizationId, modelId, { ...target, version }, { id } as GraphNode); version++; }
            break;
          }
        }
        return undefined;
      } catch (cause) {
        setNotice(noticeFor(cause, edit.kind === "connection.create" ? text.notAllowed : text.failed));
        throw cause;
      } finally {
        const loaded = await reload();
        if (loaded) editTarget.current = loaded.event;
      }
    };
    const next = queue.current.then(run, run);
    queue.current = next.catch(() => undefined);
    return next;
  };

  const refusalText = (cause: string, sourceId?: string, targetId?: string) => {
    if (cause === "read_only") return text.readOnly;
    if (cause === "missing") return text.failed;
    if (cause === "self") return text.refusalSelf;
    if (cause === "duplicate") return text.refusalDuplicate;
    const typeName = (id?: string) => graph?.nodeTypes.find((type) => type.id === byId.get(id ?? "")?.node_type_id)?.name;
    const a = typeName(sourceId);
    const b = typeName(targetId);
    return a && b ? text.refusalNotAllowed(a, b) : text.notAllowed;
  };
  const say = (message: string) => setAnnouncement((old) => (old === message ? `${message}\u00A0` : message));
  const refuse = (message: string) => { setNotice(message); say(message); };

  /** Draws an edit and sends it. A refusal before sending (read-only, a rule) gets its notice here; a refused write got its notice in `send`. */
  const edit = (change: GraphEdit): Promise<void> =>
    (canvas.current?.applyEdit(change) ?? Promise.resolve()).catch((cause) => {
      if (cause instanceof EditRefused) refuse(refusalText(cause.cause, "sourceId" in change ? change.sourceId : undefined, "targetId" in change ? change.targetId : undefined));
    });

  /** Two nodes were joined (a drag from the context pad, or two clicks): refuse with the reason, create, or ask which connection. */
  function requestConnection(sourceId: string, targetId: string, preset?: string | null) {
    if (!graph) return;
    const plan = planConnection(graph, sourceId, targetId, preset);
    if (plan.kind === "refused") {
      refuse(plan.cause === "not_allowed" && plan.sourceType && plan.targetType ? text.refusalNotAllowed(plan.sourceType, plan.targetType) : refusalText(plan.cause));
    } else if (plan.kind === "create") {
      setNotice(null);
      void edit({ kind: "connection.create", connectionTypeId: plan.connectionTypeId, sourceId, targetId });
    } else {
      setPicker({ sourceId, targetId, types: plan.types.map((type) => ({ id: type.id, name: type.name })) });
    }
  }

  /** Asks before deleting, naming what goes (the nodes and every connection touching them), then deletes the set as one step. */
  async function requestDelete(ids: readonly string[]) {
    if (!graph || !writable || ids.length === 0) return;
    const nodeIds = ids.filter((id) => byId.has(id));
    const connectionIds = ids.filter((id) => !byId.has(id));
    const summary = deleteSummary(graph, nodeIds, connectionIds);
    if (summary.nodes.length + summary.connections.length === 0) return;
    const label = (item: (typeof summary.connections)[number]) => `${item.source?.name ?? "?"} \u2192 ${item.target?.name ?? "?"} (${item.type?.name ?? "?"})`;
    const ok = await confirm({ title: text.deleteTitle(summary.nodes.map((node) => node.name), summary.connections.map(label)), confirmLabel: text.deleteElements, destructive: true });
    if (!ok) return;
    setSelectedIds([]);
    setNotice(null);
    void edit({ kind: "elements.delete", nodeIds: summary.nodes.map((node) => node.id), connectionIds: summary.alone });
    say(text.deleteElements);
  }
  const deleteRef = useRef(requestDelete);
  deleteRef.current = requestDelete;
  const selectedRef = useRef(selectedIds);
  selectedRef.current = selectedIds;

  function onElementClick(target: CanvasTarget): boolean {
    if (target.kind === "root") { setConnecting(null); return false; }
    if (!connecting || target.kind !== "node") return false;
    if (connecting.sourceId === null) { setConnecting({ ...connecting, sourceId: target.id }); return true; }
    const { sourceId, connectionTypeId } = connecting;
    setConnecting(null);
    requestConnection(sourceId, target.id, connectionTypeId);
    return true;
  }

  /** Esc in the drawing: leaves connect mode if it is on (true), otherwise lets the canvas clear the selection. */
  function cancelConnect(): boolean {
    if (!connecting) return false;
    setConnecting(null);
    return true;
  }

  /** What an undo or redo came to: said in a sentence, and a refusal also drops the step from the person's history (done by the history). */
  function onHistory(outcome: HistoryOutcome) {
    if (outcome.status === "idle") return;
    const what = text.historyLabel[outcome.label] ?? outcome.label;
    if (outcome.status === "done") { setNotice(null); say(outcome.direction === "undo" ? text.undone(what) : text.redone(what)); return; }
    if (outcome.status === "refused") {
      const undo = outcome.direction === "undo";
      refuse(outcome.reason === "changed" ? (undo ? text.undoChanged : text.redoChanged) : undo ? text.undoMissing : text.redoMissing);
      return;
    }
    refuse(noticeFor(outcome.error, text.failed));
  }
  const readGraph = async () => {
    const loaded = await new Promise<Awaited<ReturnType<typeof reload>>>((resolve) => {
      const run = async () => { const result = await reload(); if (result) editTarget.current = result.event; resolve(result); };
      queue.current = queue.current.then(run, run);
    });
    return loaded?.graph ?? null;
  };
  const toolbarTexts = { toolbar: text.zoomToolbar, zoomIn: text.zoomIn, zoomOut: text.zoomOut, fit: text.zoomFit, actualSize: text.zoomActual, zoomLevel: text.zoomLevel, undo: text.undo, redo: text.redo, connect: text.connectMode, lasso: text.lassoTool };

  // "/" focuses the search box (the canvas keymap only delivers keys while focus is in the drawing and not in a text field).
  // The drawing keys read refs, because the canvas registers them once when its diagram is created.
  const writableRef = useRef(writable);
  writableRef.current = writable;
  const connectingRef = useRef(connecting);
  connectingRef.current = connecting;
  const keyBindings = useMemo(() => [
    { id: "panel.search", keys: ["/"], run: () => { searchInput.current?.focus(); searchInput.current?.select(); } },
    { id: "draw.connect", keys: ["c"], run: () => { if (!writableRef.current) return false; setConnecting(connectingRef.current ? null : { sourceId: null, connectionTypeId: null }); } },
    { id: "draw.lasso", keys: ["l"], run: () => { canvas.current?.setLasso(true); } },
    { id: "draw.delete", keys: ["Delete", "Backspace"], run: () => { if (!writableRef.current || selectedRef.current.length === 0) return false; void deleteRef.current(selectedRef.current); } },
    { id: "draw.rename", keys: ["F2"], run: () => { if (!writableRef.current || selectedRef.current.length !== 1) return false; return canvas.current?.renameNode(selectedRef.current[0]); } },
  ], []);

  // The undo history belongs to one line and one event: it is forgotten when either changes (the first edit of a line without events creates one: that is no change).
  const eventId = event?.id ?? null;
  const lastEvent = useRef<string | null>(null);
  useEffect(() => {
    if (lastEvent.current && eventId && lastEvent.current !== eventId) canvas.current?.clearHistory();
    if (eventId) lastEvent.current = eventId;
  }, [eventId]);
  useEffect(() => { lastEvent.current = null; }, [lineId]);

  if (status === "failed") return <Alert tone="danger" role="alert">{text.failed}</Alert>;
  if (!graph) return <p role="status" className="text-ink-muted">{text.loading}</p>;

  const addNode = writable ? <AddNode graph={graph} onAdd={(typeId) => { canvas.current?.addNode(typeId); }} text={text} /> : null;
  const details = (
    <>
      {selectedNode ? (
        <NodePanel key={`${selectedNode.id}-${selectedNode.name}-${selectedNode.description ?? ""}`} graph={graph} node={selectedNode} writable={writable} connecting={connecting !== null} text={text}
          onSave={(changes) => void edit({ kind: "node.update", id: selectedNode.id, name: changes.name, description: changes.description })}
          onDelete={() => void requestDelete([selectedNode.id])}
          onConnect={(connectionTypeId) => setConnecting({ sourceId: selectedNode.id, connectionTypeId })}
          onCancel={() => setConnecting(null)} />
      ) : selectedConnection ? (
        <ConnectionPanel key={`${selectedConnection.id}-${selectedConnection.source_node_id}-${selectedConnection.target_node_id}`} connection={selectedConnection} writable={writable} byId={byId} connectionTypes={connectionTypes} text={text}
          onDelete={() => void requestDelete([selectedConnection.id])}
          onReroute={(sourceId, targetId) => void edit({ kind: "connection.reroute", id: selectedConnection.id, sourceId, targetId })} />
      ) : selectedIds.length > 1 ? (
        <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4">
          <h2 className="m-0 text-[14px] font-semibold">{text.selectedMany(selectedIds.length)}</h2>
          {writable ? <Button variant="ghost-danger" onClick={() => void requestDelete(selectedIds)}>{text.deleteSelected}</Button> : null}
        </div>
      ) : <p className="m-0 text-[13px] text-ink-muted">{text.noSelection}</p>}
      {connecting ? <Alert tone="info" role="status">{connecting.sourceId === null ? text.connectModeHint : text.connectHint}</Alert> : null}
    </>
  );
  const hiding = (next: ReadonlySet<string>) => {
    setHiddenTypes(next);
    // A node that is no longer drawn cannot stay selected.
    if (selectedNode && next.has(selectedNode.node_type_id)) setSelectedId(null);
  };
  const addOfType = (typeId: string) => { canvas.current?.addNode(typeId); };
  const nodeList = (
    <TypePanel
      groups={groups} hidden={hiddenTypes} collapse={collapse} query={query} matches={matchIds} selectedId={selectedId} markers={graph.markers} writable={writable}
      texts={{ ...text, selectAll: text.selectAllTypes, deselectAll: text.deselectAllTypes }} searchRef={searchInput} onQuery={setQuery}
      onSubmitSearch={() => { const first = found?.[0]; if (first) canvas.current?.centreOnNode(first.id); }}
      onToggleType={(typeId) => hiding(toggleType(hiddenTypes, typeId))}
      onSelectAll={() => hiding(showAllTypes())} onDeselectAll={() => hiding(hideAllTypes(groups))}
      onToggleCollapse={(typeId, wasOpen) => setCollapse((old) => { const next = { ...old, [typeId]: wasOpen }; writeTypeCollapse(modelId, next); return next; })}
      onAdd={addOfType}
      onSelectNode={(id) => { setSelectedId(id); canvas.current?.centreOnNode(id, { zoom: true }); }}
    />
  );
  const rightContent = <>{addNode}{details}</>;

  return (
    <div className="flex flex-col gap-3">
      {!writable ? <Alert tone="warning">{text.readOnly}</Alert> : null}
      {notice ? <Alert tone="danger" role="alert">{notice}</Alert> : null}
      <div role="status" aria-live="polite" className="sr-only">{announcement}</div>
      <Dialog open={picker !== null} onOpenChange={(open) => { if (!open) setPicker(null); }} title={text.chooseConnection}
        description={picker ? text.chooseConnectionHint(byId.get(picker.sourceId)?.name ?? "", byId.get(picker.targetId)?.name ?? "") : undefined}
        footer={<Button onClick={() => setPicker(null)}>{text.cancel}</Button>}>
        <div className="flex flex-col gap-2">
          {picker?.types.map((type) => (
            <Button key={type.id} onClick={() => { const chosen = picker; setPicker(null); void edit({ kind: "connection.create", connectionTypeId: type.id, sourceId: chosen.sourceId, targetId: chosen.targetId }); }}>{type.name}</Button>
          ))}
        </div>
      </Dialog>
      <div ref={area} style={{ height: areaHeight }} className="flex min-h-0 gap-3">
        {phone ? null : <Panel side="left" title={text.panelNodes} collapsed={panels.left} onToggle={() => toggle("left")} text={text}>{nodeList}</Panel>}
        <div className="min-w-0 flex-1 overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface">
          <ShadowCanvas ref={canvas} graph={graph} readOnly={!writable} selectedIds={selectedIds} onSelect={setSelectedIds}
            drawing={{ connect: (a, b) => requestConnection(a, b), remove: (ids) => void requestDelete(ids), create: (input) => { say(text.nodeAdded); void edit({ kind: "node.create", nodeTypeId: input.nodeTypeId, name: input.name, x: input.x, y: input.y }); }, rename: (id, name) => { const node = byId.get(id); void edit({ kind: "node.update", id, name, description: node?.description ?? null }); } }}
            drawingTexts={{ connect: text.padConnect, remove: text.padRemove, nodeName: text.nodeName, namePlaceholder: text.namePlaceholder }}
            readGraph={readGraph} isRefusal={(error) => error instanceof StaleVersionError || error instanceof RuleError} onHistory={onHistory}
            onToggleConnect={() => setConnecting((old) => (old ? null : { sourceId: null, connectionTypeId: null }))} onElementClick={onElementClick} send={send} connecting={connecting !== null} onEscape={cancelConnect} view={view} filter={filter} keyBindings={keyBindings} toolbarTexts={toolbarTexts} label={text.canvasLabel} />
        </div>
        {phone ? null : <Panel side="right" title={text.panelDetails} collapsed={panels.right} onToggle={() => toggle("right")} text={text}>{rightContent}</Panel>}
      </div>
      {phone ? (
        <section aria-label={text.panelDetails} className="fixed inset-x-0 bottom-0 z-20 flex flex-col border-t border-line bg-surface shadow-[var(--shadow-overlay)]">
          <button type="button" aria-expanded={sheetOpen} aria-controls="canvas-sheet" onClick={() => setSheetOpen((open) => !open)} style={{ height: SHEET_HANDLE }} className="flex w-full cursor-pointer items-center justify-center gap-2 border-0 bg-transparent text-[13px] font-medium text-ink">
            {sheetOpen ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronUp size={16} aria-hidden="true" />}
            {sheetOpen ? text.hidePanels : text.showPanels}
          </button>
          <div id="canvas-sheet" hidden={!sheetOpen} className={cx("max-h-[55dvh] flex-col gap-4 overflow-y-auto p-3", sheetOpen ? "flex" : "hidden")}>
            {rightContent}
            <section aria-label={text.panelNodes} className="flex flex-col gap-2"><h2 className="m-0 text-[14px] font-semibold">{text.panelNodes}</h2>{nodeList}</section>
          </div>
        </section>
      ) : null}
    </div>
  );
}

/** A collapsible side panel: a column when open, a narrow rail with one button when collapsed. */
function Panel({ side, title, collapsed, onToggle, text, children }: { side: "left" | "right"; title: string; collapsed: boolean; onToggle: () => void; text: Text; children: ReactNode }) {
  // The chevron points where the panel goes when it collapses (left panel to the left, right panel to the right).
  const closeIcon = side === "left" ? <ChevronLeft size={16} /> : <ChevronRight size={16} />;
  const openIcon = side === "left" ? <ChevronRight size={16} /> : <ChevronLeft size={16} />;
  const id = `canvas-panel-${side}`;
  return (
    <aside aria-label={title} className={cx("flex shrink-0 flex-col gap-3 overflow-hidden", collapsed ? "w-10 items-center" : side === "left" ? "w-[220px]" : "w-[280px]")}>
      <div className={cx("flex items-center gap-2", collapsed ? "flex-col" : "justify-between")}>
        {collapsed ? null : <h2 className="m-0 text-[14px] font-semibold">{title}</h2>}
        <IconButton label={collapsed ? text.expandPanel(title) : text.collapsePanel(title)} icon={collapsed ? openIcon : closeIcon} onClick={onToggle} aria-expanded={!collapsed} aria-controls={id} />
        {collapsed ? <span className="text-xs font-semibold text-ink-muted [writing-mode:vertical-rl]" aria-hidden="true">{title}</span> : null}
      </div>
      <div id={id} hidden={collapsed} className={cx("min-h-0 flex-1 flex-col gap-4 overflow-y-auto", collapsed ? "hidden" : "flex")}>{children}</div>
    </aside>
  );
}

type Text = ReturnType<typeof modelMessages>;

function AddNode({ graph, onAdd, text }: { graph: GraphData; onAdd: (typeId: string) => void; text: Text }) {
  const [typeId, setTypeId] = useState(graph.nodeTypes[0]?.id ?? "");
  return (
    <form className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4" onSubmit={(event) => { event.preventDefault(); if (typeId) onAdd(typeId); }}>
      <h2 className="m-0 text-[14px] font-semibold">{text.addNode}</h2>
      <Field label={text.nodeType}>{(control) => <Select {...control} value={typeId} onChange={(event) => setTypeId(event.target.value)}>{graph.nodeTypes.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}</Select>}</Field>
      <Button type="submit" variant="primary" disabled={!typeId}>{text.add}</Button>
    </form>
  );
}

function NodePanel({ graph, node, writable, connecting, text, onSave, onDelete, onConnect, onCancel }: { graph: GraphData; node: GraphNode; writable: boolean; connecting: boolean; text: Text; onSave: (changes: { name: string; description: string | null }) => void; onDelete: () => void; onConnect: (connectionTypeId: string) => void; onCancel: () => void }) {
  const [name, setName] = useState(node.name);
  const [description, setDescription] = useState(node.description ?? "");
  const options = graph.allowedConnections.filter((item) => item.source_node_type_id === node.node_type_id).map((item) => item.connection_type_id);
  const available = graph.connectionTypes.filter((type) => options.includes(type.id));
  const [connectionTypeId, setConnectionTypeId] = useState(available[0]?.id ?? "");
  const related = graph.connections.filter((item) => item.source_node_id === node.id || item.target_node_id === node.id);
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4">
      <h2 className="m-0 text-[14px] font-semibold">{text.selected}</h2>
      <Field label={text.nodeName}>{(control) => <TextInput {...control} value={name} disabled={!writable} onChange={(event) => setName(event.target.value)} />}</Field>
      <Field label={text.nodeDescription}>{(control) => <TextArea {...control} rows={3} value={description} disabled={!writable} onChange={(event) => setDescription(event.target.value)} />}</Field>
      {writable ? <div className="flex gap-2"><Button variant="primary" disabled={!name.trim()} onClick={() => onSave({ name, description: description.trim() || null })}>{text.save}</Button><Button variant="ghost-danger" onClick={onDelete}>{text.deleteNode}</Button></div> : null}
      {writable && available.length > 0 ? (
        <div className="flex flex-col gap-2 border-t border-line pt-3">
          <Field label={text.connectionType}>{(control) => <Select {...control} value={connectionTypeId} onChange={(event) => setConnectionTypeId(event.target.value)}>{available.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}</Select>}</Field>
          {connecting ? <Button onClick={onCancel}>{text.cancel}</Button> : <Button onClick={() => onConnect(connectionTypeId)}>{text.connectFrom}</Button>}
        </div>
      ) : null}
      {related.length > 0 ? <p className="m-0 text-xs text-ink-muted">{text.connections}: {related.length}</p> : null}
    </div>
  );
}

function ConnectionPanel({ connection, writable, byId, connectionTypes, text, onDelete, onReroute }: { connection: GraphConnection; writable: boolean; byId: Map<string, GraphNode>; connectionTypes: Map<string, { name: string }>; text: Text; onDelete: () => void; onReroute: (sourceId: string, targetId: string) => void }) {
  const [sourceId, setSourceId] = useState(connection.source_node_id);
  const [targetId, setTargetId] = useState(connection.target_node_id);
  const nodeOptions = [...byId.values()].sort((a, b) => a.name.localeCompare(b.name)).map((node) => <option key={node.id} value={node.id}>{node.name}</option>);
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4">
      <h2 className="m-0 text-[14px] font-semibold">{connectionTypes.get(connection.connection_type_id)?.name}</h2>
      <p className="m-0 text-[13px]">{byId.get(connection.source_node_id)?.name} → {byId.get(connection.target_node_id)?.name}</p>
      {writable ? (
        <>
          <Field label={text.rerouteFrom}>{(control) => <Select {...control} value={sourceId} onChange={(event) => setSourceId(event.target.value)}>{nodeOptions}</Select>}</Field>
          <Field label={text.rerouteTo}>{(control) => <Select {...control} value={targetId} onChange={(event) => setTargetId(event.target.value)}>{nodeOptions}</Select>}</Field>
          <div className="flex gap-2">
            <Button disabled={sourceId === connection.source_node_id && targetId === connection.target_node_id} onClick={() => onReroute(sourceId, targetId)}>{text.reroute}</Button>
            <Button variant="ghost-danger" onClick={onDelete}>{text.deleteConnection}</Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
