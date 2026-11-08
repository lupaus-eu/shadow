import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";

import { useOrganization } from "../shell/organization-outlet";
import { useModel } from "./ModelShell";
import { Alert, Button, Field, IconButton, Select, TextArea, TextInput, cx } from "../ui";
import {
  ChainBrokenError, createConnection, createEditsEvent, createNode, deleteConnection, deleteNode, loadGraph, RuleError, saveNodePositions, StaleVersionError, updateNode,
  type Graph, type GraphConnection, type GraphNode, type LineEvent,
} from "./client";
import { modelMessages } from "./messages";
import { readPanels, writePanels, type PanelState } from "./panel-state";

const NODE_WIDTH = 150;
const NODE_HEIGHT = 46;
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

/** The size of an element, kept up to date; the SVG viewBox follows it so one unit is one pixel. */
function useElementSize(ref: RefObject<HTMLElement | null>) {
  const [size, setSize] = useState({ width: 900, height: 480 });
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const update = () => setSize((old) => (old.width === element.clientWidth && old.height === element.clientHeight ? old : { width: element.clientWidth, height: element.clientHeight }));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return size;
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

const centre = (node: GraphNode) => ({ x: node.x + NODE_WIDTH / 2, y: node.y + NODE_HEIGHT / 2 });

/** The point where the line from this node's centre towards `to` leaves the node's rectangle. */
function edgePoint(node: GraphNode, to: { x: number; y: number }) {
  const from = centre(node);
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (dx === 0 && dy === 0) return from;
  const scale = Math.min(NODE_WIDTH / 2 / Math.abs(dx || 1e-9), NODE_HEIGHT / 2 / Math.abs(dy || 1e-9));
  return { x: from.x + dx * scale, y: from.y + dy * scale };
}

/** `/organizations/:organizationId/models/:modelId`: the nodes and connections of a line on a canvas. Edits are changes of the line's last event (ticket 09 of the model timeline adds the event list and the choice of event). */
export function ModelCanvas() {
  const { locale } = useOrganization();
  const { organizationId, modelId, line, writable } = useModel();
  const lineId = line.id;
  const text = modelMessages(locale);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ kind: "node" | "connection"; id: string } | null>(null);
  const [connecting, setConnecting] = useState<{ sourceId: string; connectionTypeId: string } | null>(null);
  const [drag, setDrag] = useState<{ id: string; dx: number; dy: number; moved: boolean } | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const area = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const phone = useIsPhone();
  const [panels, setPanels] = useState<PanelState>(() => readPanels());
  const [sheetOpen, setSheetOpen] = useState(false);
  const areaHeight = useFillHeight(area, phone ? SHEET_HANDLE : 0);
  const size = useElementSize(stage);
  const toggle = (side: keyof PanelState) => setPanels((old) => { const next = { ...old, [side]: !old[side] }; writePanels(next); return next; });

  const reload = useCallback(async () => {
    try {
      setGraph(await loadGraph(organizationId, modelId, lineId));
      setFailed(false);
    } catch { setFailed(true); }
  }, [organizationId, modelId, lineId]);
  useEffect(() => { void reload(); }, [reload]);

  const nodes = graph?.nodes ?? [];
  const byId = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const types = useMemo(() => new Map((graph?.node_types ?? []).map((type) => [type.id, type])), [graph]);
  const connectionTypes = useMemo(() => new Map((graph?.connection_types ?? []).map((type) => [type.id, type])), [graph]);
  const selectedNode = selected?.kind === "node" ? byId.get(selected.id) : undefined;
  const selectedConnection = selected?.kind === "connection" ? graph?.connections.find((item) => item.id === selected.id) : undefined;

  async function act(action: () => Promise<unknown>, rule = text.failed) {
    setNotice(null);
    try { await action(); } catch (cause) {
      setNotice(cause instanceof StaleVersionError ? text.stale : cause instanceof ChainBrokenError ? text.chainBroken : cause instanceof RuleError ? rule : text.failed);
    }
    await reload();
  }

  /** An edit goes into the line's last event; a line that has none yet gets an "Edits" event first. */
  const edit = (action: (event: LineEvent) => Promise<unknown>, rule = text.failed) => act(async () => action(graph?.event ?? await createEditsEvent(organizationId, modelId, lineId, text.editsEvent)), rule);

  function pointer(event: React.PointerEvent) {
    const box = svg.current?.getBoundingClientRect();
    // The viewBox is the container size, so a client pixel is one canvas unit.
    return { x: event.clientX - (box?.left ?? 0), y: event.clientY - (box?.top ?? 0) };
  }

  function startDrag(event: React.PointerEvent, node: GraphNode) {
    if (!writable || connecting) return;
    const at = pointer(event);
    (event.target as Element).setPointerCapture?.(event.pointerId);
    setDrag({ id: node.id, dx: at.x - node.x, dy: at.y - node.y, moved: false });
  }

  function moveDrag(event: React.PointerEvent) {
    if (!drag || !graph) return;
    const at = pointer(event);
    const x = at.x - drag.dx;
    const y = at.y - drag.dy;
    setGraph({ ...graph, nodes: graph.nodes.map((node) => (node.id === drag.id ? { ...node, x, y } : node)) });
    if (!drag.moved) setDrag({ ...drag, moved: true });
  }

  function endDrag() {
    if (!drag) return;
    const node = byId.get(drag.id);
    const moved = drag.moved;
    setDrag(null);
    if (!node || !moved) return;
    // A move is a position of the line, not an edit of an event.
    void act(() => saveNodePositions(organizationId, modelId, lineId, [{ node_id: node.id, x: Math.round(node.x), y: Math.round(node.y) }]));
  }

  function clickNode(node: GraphNode) {
    if (!connecting) { setSelected({ kind: "node", id: node.id }); return; }
    const source = byId.get(connecting.sourceId);
    setConnecting(null);
    if (!source || source.id === node.id) return;
    void edit((event) => createConnection(organizationId, modelId, event, { connection_type_id: connecting.connectionTypeId, source_node_id: source.id, target_node_id: node.id }), text.notAllowed);
  }

  if (failed) return <Alert tone="danger" role="alert">{text.failed}</Alert>;
  if (!graph) return <p role="status" className="text-ink-muted">{text.loading}</p>;

  const addNode = writable ? <AddNode graph={graph} onAdd={(input) => edit((event) => createNode(organizationId, modelId, event, input))} text={text} count={nodes.length} /> : null;
  const details = (
    <>
      {selectedNode ? (
        <NodePanel key={`${selectedNode.id}-${selectedNode.name}-${selectedNode.description ?? ""}`} graph={graph} node={selectedNode} writable={writable} connecting={connecting !== null} text={text}
          onSave={(changes) => edit((event) => updateNode(organizationId, modelId, event, selectedNode, changes))}
          onDelete={() => { setSelected(null); void edit((event) => deleteNode(organizationId, modelId, event, selectedNode)); }}
          onConnect={(connectionTypeId) => setConnecting({ sourceId: selectedNode.id, connectionTypeId })}
          onCancel={() => setConnecting(null)} />
      ) : selectedConnection ? (
        <ConnectionPanel connection={selectedConnection} writable={writable} byId={byId} connectionTypes={connectionTypes} text={text}
          onDelete={() => { setSelected(null); void edit((event) => deleteConnection(organizationId, modelId, event, selectedConnection)); }} />
      ) : <p className="m-0 text-[13px] text-ink-muted">{text.noSelection}</p>}
      {connecting ? <Alert tone="info" role="status">{text.connectHint}</Alert> : null}
    </>
  );
  const nodeList = (
    <ul className="m-0 flex list-none flex-col gap-1 p-0">
      {nodes.length === 0 ? <li className="text-[13px] text-ink-muted">{text.noNodes}</li> : null}
      {nodes.map((node) => (
        <li key={node.id}>
          <button type="button" aria-pressed={selected?.kind === "node" && selected.id === node.id} onClick={() => setSelected({ kind: "node", id: node.id })} className="flex min-h-8 w-full cursor-pointer items-center gap-2 rounded-[6px] border-0 bg-transparent px-2 py-1 text-left text-[13px] text-ink hover:bg-surface-sunken aria-pressed:bg-accent-soft pointer-coarse:min-h-11">
            <span aria-hidden="true" className="size-3 shrink-0 rounded-[3px] border border-line" style={{ background: types.get(node.node_type_id)?.color ?? "#ddd" }} />
            <span className="min-w-0 flex-1 truncate">{node.name}</span>
            <span className="shrink-0 text-xs text-ink-muted">{types.get(node.node_type_id)?.name}</span>
          </button>
        </li>
      ))}
    </ul>
  );
  const rightContent = <>{addNode}{details}</>;

  return (
    <div className="flex flex-col gap-3">
      {!writable ? <Alert tone="warning">{text.readOnly}</Alert> : null}
      {notice ? <Alert tone="danger" role="alert">{notice}</Alert> : null}
      <div ref={area} style={{ height: areaHeight }} className="flex min-h-0 gap-3">
        {phone ? null : <Panel side="left" title={text.panelNodes} collapsed={panels.left} onToggle={() => toggle("left")} text={text}>{nodeList}</Panel>}
        <div ref={stage} className="min-w-0 flex-1 overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface">
          <svg ref={svg} role="group" aria-label={text.canvasLabel} viewBox={`0 0 ${size.width} ${size.height}`} width="100%" height="100%" style={{ display: "block", touchAction: "none" }} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag} onPointerDown={(event) => { if (event.target === event.currentTarget) { setSelected(null); setConnecting(null); } }}>
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="currentColor" /></marker>
            </defs>
            {graph.connections.map((connection) => {
              const source = byId.get(connection.source_node_id);
              const target = byId.get(connection.target_node_id);
              const type = connectionTypes.get(connection.connection_type_id);
              if (!source || !target || !type) return null;
              const a = edgePoint(source, centre(target));
              const b = edgePoint(target, centre(source));
              const active = selected?.kind === "connection" && selected.id === connection.id;
              return (
                <g key={connection.id} className="cursor-pointer text-ink-muted" color={active ? "var(--color-accent)" : undefined} onClick={() => setSelected({ kind: "connection", id: connection.id })}>
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={14} />
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="currentColor" strokeWidth={active ? 3 : 1.5} strokeDasharray={type.style === "dashed" ? "6 4" : undefined} markerEnd={type.target_end === "arrow" ? "url(#arrow)" : undefined} markerStart={type.source_end === "arrow" ? "url(#arrow)" : undefined} />
                  <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 6} textAnchor="middle" fontSize={11} fill="currentColor">{type.name}</text>
                </g>
              );
            })}
            {nodes.map((node) => {
              const type = types.get(node.node_type_id);
              const active = selected?.kind === "node" && selected.id === node.id;
              return (
                <g key={node.id} transform={`translate(${node.x} ${node.y})`} className={connecting ? "cursor-crosshair" : "cursor-grab"} onPointerDown={(event) => startDrag(event, node)} onClick={() => clickNode(node)} tabIndex={0} role="button" aria-label={`${node.name} (${type?.name ?? ""})`} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") clickNode(node); }}>
                  <rect width={NODE_WIDTH} height={NODE_HEIGHT} rx={8} fill={type?.color ?? "#ddd"} stroke={active ? "var(--color-accent)" : "#555"} strokeWidth={active ? 3 : 1} />
                  <text x={NODE_WIDTH / 2} y={19} textAnchor="middle" fontSize={13} fontWeight={600} fill="#111">{node.name.length > 20 ? `${node.name.slice(0, 19)}…` : node.name}</text>
                  <text x={NODE_WIDTH / 2} y={35} textAnchor="middle" fontSize={10} fill="#333">{type?.name}</text>
                </g>
              );
            })}
          </svg>
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

function AddNode({ graph, onAdd, text, count }: { graph: Graph; onAdd: (input: { node_type_id: string; name: string; x: number; y: number }) => Promise<void>; text: Text; count: number }) {
  const [typeId, setTypeId] = useState(graph.node_types[0]?.id ?? "");
  const [name, setName] = useState("");
  const column = count % 8;
  const row = Math.floor(count / 8) % 14;
  return (
    <form className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4" onSubmit={(event) => { event.preventDefault(); if (name.trim() && typeId) void onAdd({ node_type_id: typeId, name, x: 30 + column * 170, y: 30 + row * 60 }).then(() => setName("")); }}>
      <h2 className="m-0 text-[14px] font-semibold">{text.addNode}</h2>
      <Field label={text.nodeType}>{(control) => <Select {...control} value={typeId} onChange={(event) => setTypeId(event.target.value)}>{graph.node_types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}</Select>}</Field>
      <Field label={text.nodeName}>{(control) => <TextInput {...control} value={name} onChange={(event) => setName(event.target.value)} />}</Field>
      <Button type="submit" variant="primary" disabled={!name.trim()}>{text.add}</Button>
    </form>
  );
}

function NodePanel({ graph, node, writable, connecting, text, onSave, onDelete, onConnect, onCancel }: { graph: Graph; node: GraphNode; writable: boolean; connecting: boolean; text: Text; onSave: (changes: { name: string; description: string | null }) => void; onDelete: () => void; onConnect: (connectionTypeId: string) => void; onCancel: () => void }) {
  const [name, setName] = useState(node.name);
  const [description, setDescription] = useState(node.description ?? "");
  const options = graph.allowed_connections.filter((item) => item.source_node_type_id === node.node_type_id).map((item) => item.connection_type_id);
  const available = graph.connection_types.filter((type) => options.includes(type.id));
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
