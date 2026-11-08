import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useOutletContext, useParams, useSearchParams } from "react-router";

import { usePageTitle } from "../shell/AppShell";
import { modelHref, modelsHref } from "../shell/nav";
import { useOrganization } from "../shell/organization-outlet";
import { Alert, Button, Field, Select, useConfirm } from "../ui";
import { createScenario, deleteLine, loadLines, loadModels, RuleError, startingEvent, type ModelLine, type ModelSummary } from "./client";
import { modelMessages } from "./messages";

export type ModelOutlet = { organizationId: string; modelId: string; model: ModelSummary; line: ModelLine; lines: ModelLine[]; writable: boolean; reloadLines: () => Promise<void> };
export const useModel = () => useOutletContext<ModelOutlet>();

const TAB = "inline-flex h-9 items-center rounded-[8px] px-3 text-[13px] font-medium text-ink-muted no-underline hover:bg-surface-sunken aria-[current=page]:bg-accent-soft aria-[current=page]:text-accent";

/** `/organizations/:organizationId/models/:modelId/*`: the model's tabs and the line (Base line or Scenario) everything below shows. */
export function ModelShell() {
  const { workspace, locale } = useOrganization();
  const { modelId = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const text = modelMessages(locale);
  const organizationId = workspace.organization.id;
  const writable = workspace.subscription.writable;
  const confirm = useConfirm();
  const [model, setModel] = useState<ModelSummary | null>(null);
  const [lines, setLines] = useState<ModelLine[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
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

  // The selected line is the `line` search parameter (the Base line when absent). Ticket 09 of the model timeline replaces this picker.
  const requested = search.get("line");
  const line = lines?.find((item) => item.id === requested) ?? lines?.find((item) => item.kind === "base");
  const select = (id: string | null) => setSearch(id ? { line: id } : {});

  async function fork() {
    const name = window.prompt(text.scenarioName, "");
    if (!name?.trim() || !line) return;
    setNotice(null);
    try {
      const branchEventId = await startingEvent(organizationId, modelId, line);
      if (!branchEventId) { setNotice(text.failed); return; }
      const created = await createScenario(organizationId, modelId, name.trim(), branchEventId);
      await reloadLines();
      select(created.id);
    } catch (cause) {
      setNotice(cause instanceof RuleError ? text.scenarioDuplicate : text.failed);
    }
  }
  async function remove() {
    if (!line || line.kind === "base") return;
    if (!(await confirm({ title: text.deleteScenarioConfirm(line.name), confirmLabel: text.deleteScenario, destructive: true }))) return;
    setNotice(null);
    try { await deleteLine(organizationId, modelId, line); select(null); await reloadLines(); } catch (cause) {
      setNotice(cause instanceof RuleError ? text.scenarioHasChildren : text.failed);
    }
  }

  if (failed) return <Alert tone="danger" role="alert">{text.failed}</Alert>;
  if (!model || !lines || !line) return <p role="status" className="text-ink-muted">{text.loading}</p>;
  const suffix = line.kind === "base" ? "" : `?line=${line.id}`;
  const tab = (path: string, label: string, end = false) => <NavLink end={end} className={TAB} to={`${modelHref(organizationId, modelId)}${path}${suffix}`}>{label}</NavLink>;
  return (
    <div className="flex flex-col gap-4">
      <Link className="inline-flex w-fit text-[13px] text-ink-muted" to={modelsHref(organizationId)}>{text.back}</Link>
      <h1 className="m-0 text-xl font-semibold">{model.name}</h1>
      <div className="flex flex-wrap items-end gap-3">
        <Field label={text.line} className="w-56">{(control) => <Select {...control} value={line.id} onChange={(event) => select(lines.find((item) => item.id === event.target.value)?.kind === "base" ? null : event.target.value)}>{lines.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select>}</Field>
        {writable ? <Button onClick={() => void fork()}>{text.newScenario}</Button> : null}
        {writable && line.kind !== "base" ? <Button variant="ghost-danger" onClick={() => void remove()}>{text.deleteScenario}</Button> : null}
      </div>
      <nav aria-label={model.name} className="flex flex-wrap gap-1 border-b border-line pb-2">
        {tab("", text.tabs.structure, true)}
        {tab("/types", text.tabs.types)}
        {tab("/metrics", text.tabs.metrics)}
        {tab("/simulations", text.tabs.simulations)}
        {tab("/analysis", text.tabs.analysis)}
      </nav>
      {notice ? <Alert tone="danger" role="alert">{notice}</Alert> : null}
      <Outlet context={{ organizationId, modelId, model, line, lines, writable, reloadLines } satisfies ModelOutlet} />
    </div>
  );
}
