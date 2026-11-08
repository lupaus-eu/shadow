import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";

import { useOrganization } from "../shell/organization-outlet";
import { useModel } from "./ModelShell";
import { Alert, Button, Field, IconButton, Select, TextArea, TextInput, cx } from "../ui";
import {
  ChainBrokenError, createConnection, createEditsEvent, createNode, deleteConnection, deleteNode, RuleError, saveNodePositions, StaleVersionError, updateNode,
  type GraphConnection, type GraphNode, type LineEvent,
} from "./client";
import { EditRefused } from "./canvas/diagram";
import type { GraphData, GraphEdit } from "./canvas/graph-types";
import { ShadowCanvas, type CanvasTarget, type ShadowCanvasHandle } from "./canvas/ShadowCanvas";
import { useCanvasView } from "./canvas/useCanvasView";
import { TypePanel } from "./canvas/TypePanel";
import { readTypeCollapse, writeTypeCollapse, type TypeCollapse } from "./canvas/type-collapse";
import { groupNodes, hideAllTypes, nextPlacement, searchMatches, showAllTypes, toggleType, type CanvasFilter } from "./canvas/type-list";
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<{ sourceId: string; connectionTypeId: string } | null>(null);
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
  const send = (edit: GraphEdit): Promise<void> => {
    const run = async () => {
      setNotice(null);
      try {
        if (edit.kind === "node.move") {
          // A move is a position of the line, not an edit of an event.
          await saveNodePositions(organizationId, modelId, lineId, edit.moves.map((move) => ({ node_id: move.id, x: move.x, y: move.y })));
          return;
        }
        // A line that has no event yet gets an "Edits" event first.
        const target = editTarget.current ?? await createEditsEvent(organizationId, modelId, lineId, text.editsEvent);
        switch (edit.kind) {
          case "node.create": await createNode(organizationId, modelId, target, { node_type_id: edit.nodeTypeId, name: edit.name, x: edit.x, y: edit.y }); break;
          case "node.update": await updateNode(organizationId, modelId, target, byId.get(edit.id) ?? ({ id: edit.id } as GraphNode), { name: edit.name, description: edit.description }); break;
          case "node.delete": await deleteNode(organizationId, modelId, target, { id: edit.id } as GraphNode); break;
          case "connection.create": await createConnection(organizationId, modelId, target, { connection_type_id: edit.connectionTypeId, source_node_id: edit.sourceId, target_node_id: edit.targetId }); break;
          case "connection.delete": await deleteConnection(organizationId, modelId, target, { id: edit.id } as GraphConnection); break;
        }
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

  /** Draws an edit and sends it. A refusal before sending (read-only, a rule) gets its notice here; a refused write got its notice in `send`. */
  const edit = (change: GraphEdit): Promise<void> =>
    (canvas.current?.applyEdit(change) ?? Promise.resolve()).catch((cause) => {
      if (cause instanceof EditRefused) setNotice(cause.cause === "read_only" ? text.readOnly : cause.cause === "missing" ? text.failed : cause.cause === "duplicate" ? text.connectionDuplicate : text.notAllowed);
    });

  function onElementClick(target: CanvasTarget): boolean {
    if (target.kind === "root") { setConnecting(null); return false; }
    if (!connecting || target.kind !== "node") return false;
    const sourceId = connecting.sourceId;
    setConnecting(null);
    if (sourceId !== target.id) void edit({ kind: "connection.create", connectionTypeId: connecting.connectionTypeId, sourceId, targetId: target.id });
    return true;
  }

  /** Esc in the drawing: leaves connect mode if it is on (true), otherwise lets the canvas clear the selection. */
  function cancelConnect(): boolean {
    if (!connecting) return false;
    setConnecting(null);
    return true;
  }
  const toolbarTexts = { toolbar: text.zoomToolbar, zoomIn: text.zoomIn, zoomOut: text.zoomOut, fit: text.zoomFit, actualSize: text.zoomActual, zoomLevel: text.zoomLevel };

  // "/" focuses the search box (the canvas keymap only delivers keys while focus is in the drawing and not in a text field).
  const keyBindings = useMemo(() => [{ id: "panel.search", keys: ["/"], run: () => { searchInput.current?.focus(); searchInput.current?.select(); } }], []);

  if (status === "failed") return <Alert tone="danger" role="alert">{text.failed}</Alert>;
  if (!graph) return <p role="status" className="text-ink-muted">{text.loading}</p>;

  const addNode = writable ? <AddNode graph={graph} onAdd={(input) => edit({ kind: "node.create", nodeTypeId: input.node_type_id, name: input.name, x: input.x, y: input.y })} text={text} count={nodes.length} /> : null;
  const details = (
    <>
      {selectedNode ? (
        <NodePanel key={`${selectedNode.id}-${selectedNode.name}-${selectedNode.description ?? ""}`} graph={graph} node={selectedNode} writable={writable} connecting={connecting !== null} text={text}
          onSave={(changes) => void edit({ kind: "node.update", id: selectedNode.id, name: changes.name, description: changes.description })}
          onDelete={() => { setSelectedId(null); void edit({ kind: "node.delete", id: selectedNode.id }); }}
          onConnect={(connectionTypeId) => setConnecting({ sourceId: selectedNode.id, connectionTypeId })}
          onCancel={() => setConnecting(null)} />
      ) : selectedConnection ? (
        <ConnectionPanel connection={selectedConnection} writable={writable} byId={byId} connectionTypes={connectionTypes} text={text}
          onDelete={() => { setSelectedId(null); void edit({ kind: "connection.delete", id: selectedConnection.id }); }} />
      ) : <p className="m-0 text-[13px] text-ink-muted">{text.noSelection}</p>}
      {connecting ? <Alert tone="info" role="status">{text.connectHint}</Alert> : null}
    </>
  );
  const hiding = (next: ReadonlySet<string>) => {
    setHiddenTypes(next);
    // A node that is no longer drawn cannot stay selected.
    if (selectedNode && next.has(selectedNode.node_type_id)) setSelectedId(null);
  };
  const addOfType = (typeId: string) => {
    const type = graph.nodeTypes.find((item) => item.id === typeId);
    if (!type) return;
    const sameType = nodes.filter((node) => node.node_type_id === typeId).length;
    void edit({ kind: "node.create", nodeTypeId: typeId, name: `${type.name} ${sameType + 1}`, ...nextPlacement(nodes.length) });
  };
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
      <div ref={area} style={{ height: areaHeight }} className="flex min-h-0 gap-3">
        {phone ? null : <Panel side="left" title={text.panelNodes} collapsed={panels.left} onToggle={() => toggle("left")} text={text}>{nodeList}</Panel>}
        <div className="min-w-0 flex-1 overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface">
          <ShadowCanvas ref={canvas} graph={graph} readOnly={!writable} selectedId={selectedId} onSelect={setSelectedId} onElementClick={onElementClick} send={send} connecting={connecting !== null} onEscape={cancelConnect} view={view} filter={filter} keyBindings={keyBindings} toolbarTexts={toolbarTexts} label={text.canvasLabel} />
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

function AddNode({ graph, onAdd, text, count }: { graph: GraphData; onAdd: (input: { node_type_id: string; name: string; x: number; y: number }) => Promise<void>; text: Text; count: number }) {
  const [typeId, setTypeId] = useState(graph.nodeTypes[0]?.id ?? "");
  const [name, setName] = useState("");
  const place = nextPlacement(count);
  return (
    <form className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4" onSubmit={(event) => { event.preventDefault(); if (name.trim() && typeId) void onAdd({ node_type_id: typeId, name, ...place }).then(() => setName("")); }}>
      <h2 className="m-0 text-[14px] font-semibold">{text.addNode}</h2>
      <Field label={text.nodeType}>{(control) => <Select {...control} value={typeId} onChange={(event) => setTypeId(event.target.value)}>{graph.nodeTypes.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}</Select>}</Field>
      <Field label={text.nodeName}>{(control) => <TextInput {...control} value={name} onChange={(event) => setName(event.target.value)} />}</Field>
      <Button type="submit" variant="primary" disabled={!name.trim()}>{text.add}</Button>
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

function ConnectionPanel({ connection, writable, byId, connectionTypes, text, onDelete }: { connection: GraphConnection; writable: boolean; byId: Map<string, GraphNode>; connectionTypes: Map<string, { name: string }>; text: Text; onDelete: () => void }) {
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4">
      <h2 className="m-0 text-[14px] font-semibold">{connectionTypes.get(connection.connection_type_id)?.name}</h2>
      <p className="m-0 text-[13px]">{byId.get(connection.source_node_id)?.name} → {byId.get(connection.target_node_id)?.name}</p>
      {writable ? <Button variant="ghost-danger" onClick={onDelete}>{text.deleteConnection}</Button> : null}
    </div>
  );
}
