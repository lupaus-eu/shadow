import { ListTree } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, Outlet, useMatch, useOutletContext, useParams, useSearchParams } from "react-router";

import { usePageTitle, useAccount } from "../shell/AppShell";
import { modelHref, modelsHref } from "../shell/nav";
import { useOrganization, type OrganizationOutlet } from "../shell/organization-outlet";
import { Alert, Button, useConfirm } from "../ui";
import { acknowledgeStart, adoptLine, createScenario, deleteLine, loadChanges, loadLines, loadModels, renameLine, RuleError, StaleVersionError, type LineChange, type ModelLine, type ModelSummary } from "./client";
import { modelMessages } from "./messages";
import { adoptMessage, canAdopt, canManageLine, canWriteLine, deleteLineMessage, shownChange, tabQuery, type Role } from "./timeline";
import { timelineMessages } from "./timeline-messages";
import { ChangeEditor, type EditorTarget } from "./timeline/ChangeEditor";
import { ChangePanel } from "./timeline/ChangePanel";
import { LineKind, LinePicker, NameDialog } from "./timeline/LineBar";
import { refusalMessage } from "./timeline/refusals";

export type ModelOutlet = {
  organizationId: string; modelId: string; model: ModelSummary; line: ModelLine; lines: ModelLine[]; writable: boolean; reloadLines: () => Promise<void>;
  /** The changes of the selected line, oldest first. */
  changes: LineChange[];
  /** The change shown (`?change=`, else the line's last); null for a line without changes. Ticket 08 of the structure canvas draws into it. */
  change: LineChange | null;
  /** False while an change before the line's last is shown: the canvas is then read-only. */
  changeIsLast: boolean;
  /** Reads the changes (and the lines' counts) again after an edit. */
  reloadChanges: () => Promise<void>;
  role: Role;
  /** The person's role may write the selected line (Base line: Owner or Admin; Scenario: any Member). */
  canWriteLine: boolean;
};
export const useModel = () => useOutletContext<ModelOutlet>();

const TAB = "inline-flex h-9 items-center rounded-[8px] px-3 text-[13px] font-medium text-ink-muted no-underline hover:bg-surface-sunken aria-[current=page]:bg-accent-soft aria-[current=page]:text-accent";
const ADOPT_REASONS = new Set(["parent_moved_on", "dates_precede", "nothing_to_adopt", "base_line", "limit_reached"]);

type Notice = { tone: "danger" | "success"; message: string };
type Dialogs = { kind: "scenario" } | { kind: "rename" } | { kind: "change"; target: EditorTarget } | null;

/** `/organizations/:organizationId/models/:modelId/*`: the model's tabs, the line (Base line or Scenario) and, on the Structure tab, the change everything below shows. */
export function ModelShell() {
  const organization = useOrganization();
  const { workspace, locale } = organization;
  const { userAccount } = useAccount();
  const { modelId = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const text = modelMessages(locale);
  const lineText = timelineMessages(locale);
  const organizationId = workspace.organization.id;
  const writable = workspace.subscription.writable;
  const role = workspace.membership.role;
  const confirm = useConfirm();
  const [model, setModel] = useState<ModelSummary | null>(null);
  const [lines, setLines] = useState<ModelLine[] | null>(null);
  const [loadedChanges, setLoadedChanges] = useState<{ lineId: string; items: LineChange[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [dialog, setDialog] = useState<Dialogs>(null);
  // The change list opens by itself only on a wide screen: beside the canvas and its own panels it would squeeze the drawing.
  const [panelOpen, setPanelOpen] = useState(() => (typeof window.matchMedia === "function" ? window.matchMedia("(min-width: 1600px)").matches : false));
  const onStructure = useMatch({ path: modelHref(organizationId, modelId), end: true }) !== null;
  usePageTitle(model?.name ?? text.title);

  const reloadLines = useCallback(async () => {
    try {
      const [models, loaded] = await Promise.all([loadModels(organizationId), loadLines(organizationId, modelId)]);
      setModel(models.find((item) => item.id === modelId) ?? null);
      setLines(loaded);
      setFailed(false);
    } catch { setFailed(true); }
  }, [organizationId, modelId]);
  useEffect(() => { void reloadLines(); }, [reloadLines]);

  // The selected line is the `line` search parameter (the Base line when absent), the shown change the `change` parameter (the line's last when absent).
  const requested = search.get("line");
  const line = lines?.find((item) => item.id === requested) ?? lines?.find((item) => item.kind === "base");
  const lineId = line?.id ?? null;

  const changesRef = useRef(loadedChanges);
  changesRef.current = loadedChanges;
  const reloadChanges = useCallback(async () => {
    if (!lineId) return;
    try {
      const items = await loadChanges(organizationId, modelId, lineId);
      // Nothing is set when the list is the same, so a canvas write that changed no listed value does not redraw the page.
      const old = changesRef.current;
      const same = old !== null && old.lineId === lineId && JSON.stringify(old.items) === JSON.stringify(items);
      if (!same) setLoadedChanges({ lineId, items });
      if (!old || old.lineId !== lineId || old.items.length !== items.length) await reloadLines();
    } catch { setFailed(true); }
  }, [organizationId, modelId, lineId, reloadLines]);
  useEffect(() => {
    if (!lineId) return;
    let current = true;
    loadChanges(organizationId, modelId, lineId).then((items) => { if (current) setLoadedChanges({ lineId, items }); }, () => { if (current) setFailed(true); });
    return () => { current = false; };
  }, [organizationId, modelId, lineId]);

  const changes = useMemo(() => (loadedChanges && loadedChanges.lineId === lineId ? loadedChanges.items : null), [loadedChanges, lineId]);
  const shown = useMemo(() => shownChange(changes ?? [], search.get("change")), [changes, search]);

  /** Shows a line (and optionally one of its changes); the Base line and the last change are the defaults and stay out of the address. */
  const show = (target: ModelLine | null, changeId: string | null = null) => setSearch(new URLSearchParams(tabQuery(target && target.kind !== "base" ? target.id : null, changeId)));
  const showChange = (change: LineChange) => show(line ?? null, change.id === changes?.[changes.length - 1]?.id ? null : change.id);

  if (failed) return <Alert tone="danger" role="alert">{text.failed}</Alert>;
  if (!model || !lines || !line || !changes) return <p role="status" className="text-ink-muted">{text.loading}</p>;

  const parent = lines.find((item) => item.id === line.parent_line_id) ?? null;
  const manage = writable && canManageLine(line, role, userAccount.id);
  const write = writable && canWriteLine(line, role);
  const adoptable = writable && canAdopt(line, lines, role);
  const branchChangeId = shown.change?.id ?? line.branch_change_id;

  async function fork(name: string) {
    if (!branchChangeId) throw new Error(lineText.failed);
    try {
      const created = await createScenario(organizationId, modelId, name, branchChangeId);
      await reloadLines();
      setNotice(null);
      show(created);
    } catch (cause) { throw new Error(refusalMessage(cause, locale)); }
  }
  async function rename(name: string) {
    try { await renameLine(organizationId, modelId, line!, name); await reloadLines(); } catch (cause) {
      if (cause instanceof StaleVersionError) await reloadLines();
      throw new Error(refusalMessage(cause, locale));
    }
  }
  async function remove() {
    if (line!.kind === "base") return;
    if (!(await confirm({ title: lineText.deleteScenarioConfirm(line!.name), confirmLabel: lineText.deleteScenario, destructive: true }))) return;
    setNotice(null);
    try { await deleteLine(organizationId, modelId, line!); show(parent); await reloadLines(); } catch (cause) {
      setNotice({ tone: "danger", message: cause instanceof RuleError && (cause.reason === "has_children" || cause.reason === "base_line") ? deleteLineMessage(cause.detail, locale) : refusalMessage(cause, locale) });
    }
  }
  async function adopt() {
    if (!parent) return;
    if (!(await confirm({ title: lineText.adoptConfirmTitle(line!.name, parent.name), description: lineText.adoptConfirmBody, confirmLabel: lineText.adoptConfirm, destructive: true }))) return;
    setNotice(null);
    try {
      await adoptLine(organizationId, modelId, line!);
      await reloadLines();
      show(parent);
      setNotice({ tone: "success", message: lineText.adopted(parent.name) });
    } catch (cause) {
      setNotice({ tone: "danger", message: cause instanceof RuleError && cause.reason && ADOPT_REASONS.has(cause.reason) ? adoptMessage(cause.detail, locale) : refusalMessage(cause, locale) });
    }
  }
  async function acknowledge() {
    setNotice(null);
    try { await acknowledgeStart(organizationId, modelId, line!); await reloadLines(); } catch (cause) { setNotice({ tone: "danger", message: refusalMessage(cause, locale) }); }
  }

  const tab = (path: string, label: string, end = false, keepChange = false) => (
    <NavLink end={end} className={TAB} to={`${modelHref(organizationId, modelId)}${path}${tabQuery(line.kind === "base" ? null : line.id, keepChange && !shown.isLast ? shown.change?.id ?? null : null)}`}>{label}</NavLink>
  );
  const outlet = (
    <Outlet context={{ ...organization, organizationId, modelId, model, line, lines, writable, reloadLines, changes, change: shown.change, changeIsLast: shown.isLast, reloadChanges, role, canWriteLine: canWriteLine(line, role) } satisfies ModelOutlet & OrganizationOutlet} />
  );
  return (
    <div className="flex flex-col gap-4">
      <Link className="inline-flex w-fit text-[13px] text-ink-muted" to={modelsHref(organizationId)}>{text.back}</Link>
      <h1 className="m-0 text-xl font-semibold">{model.name}</h1>
      <div data-line-kind={line.kind} className={`flex flex-wrap items-end gap-3 rounded-[var(--radius-card)] border-l-4 pl-3 ${line.kind === "base" ? "border-accent bg-accent-soft" : "border-info-ink bg-info-soft"}`}>
        <LinePicker lines={lines} line={line} locale={locale} onSelect={(next) => { setNotice(null); show(next); }} />
        <div className="flex h-9 items-center"><LineKind line={line} locale={locale} /></div>
        {writable ? <Button disabled={!branchChangeId} onClick={() => setDialog({ kind: "scenario" })}>{lineText.newScenarioHere}</Button> : null}
        {manage ? <Button onClick={() => setDialog({ kind: "rename" })}>{lineText.rename}</Button> : null}
        {adoptable ? <Button onClick={() => void adopt()}>{lineText.adopt}</Button> : null}
        {manage && line.kind !== "base" ? <Button variant="ghost-danger" onClick={() => void remove()}>{lineText.deleteScenario}</Button> : null}
        {onStructure ? <Button className="ml-auto" icon={<ListTree size={14} />} aria-expanded={panelOpen} aria-controls="change-panel" onClick={() => setPanelOpen((open) => !open)}>{`${lineText.changes} (${changes.length})`}</Button> : null}
      </div>
      {line.kind === "scenario" && line.start_changed_at
        ? <Alert tone="warning" role="status" action={write ? <Button size="sm" onClick={() => void acknowledge()}>{lineText.acknowledge}</Button> : undefined}>{lineText.startChanged}</Alert> : null}
      <nav aria-label={model.name} className="flex flex-wrap gap-1 border-b border-line pb-2">
        {tab("", text.tabs.structure, true, true)}
        {tab("/types", text.tabs.types)}
        {tab("/metrics", text.tabs.metrics)}
        {tab("/simulations", text.tabs.simulations)}
        {tab("/analysis", text.tabs.analysis)}
      </nav>
      {notice ? <Alert tone={notice.tone} role={notice.tone === "danger" ? "alert" : "status"}>{notice.message}</Alert> : null}
      {onStructure ? (
        <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start">
          <div className="flex min-w-0 flex-1 flex-col gap-2">{outlet}</div>
          <div id="change-panel" hidden={!panelOpen} className="min-w-0 lg:w-72 lg:shrink-0">
            <ChangePanel lineName={line.name} changes={changes} selectedId={shown.change?.id ?? null} canWrite={write} locale={locale} onSelect={showChange} onNew={() => setDialog({ kind: "change", target: { mode: "new" } })}
              onEdit={(change) => setDialog({ kind: "change", target: { mode: "edit", change } })} onOpenLine={(id) => { const next = lines.find((item) => item.id === id); if (next) show(next); }} />
          </div>
        </div>
      ) : outlet}
      {dialog?.kind === "scenario" ? <NameDialog title={lineText.newScenarioTitle} description={lineText.newScenarioFrom(shown.change?.title ?? null)} label={lineText.scenarioName} initial="" submitLabel={lineText.create} locale={locale} onSubmit={fork} onClose={() => setDialog(null)} /> : null}
      {dialog?.kind === "rename" ? <NameDialog title={lineText.renameLine(line.kind)} label={lineText.lineName} initial={line.name} submitLabel={lineText.save} locale={locale} onSubmit={rename} onClose={() => setDialog(null)} /> : null}
      {dialog?.kind === "change" ? (
        <ChangeEditor organizationId={organizationId} modelId={modelId} lineId={line.id} target={dialog.target} canWrite={write} locale={locale} onClose={() => setDialog(null)}
          onChanged={(result) => { void reloadChanges().then(() => { if (result.selectId) setSearch(new URLSearchParams(tabQuery(line.kind === "base" ? null : line.id, result.selectId))); else if (result.removedId && result.removedId === shown.change?.id) show(line.kind === "base" ? null : line); }); }} />
      ) : null}
    </div>
  );
}
