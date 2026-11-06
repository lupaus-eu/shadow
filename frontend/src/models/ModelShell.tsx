import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useOutletContext, useParams, useSearchParams } from "react-router";

import { usePageTitle } from "../shell/AppShell";
import { modelHref, modelsHref } from "../shell/nav";
import { useOrganization } from "../shell/organization-outlet";
import { Alert, Button, Field, Select, useConfirm } from "../ui";
import { createVersion, deleteVersion, loadModels, loadVersions, RuleError, type ModelSummary, type ModelVersion } from "./client";
import { modelMessages } from "./messages";

export type ModelOutlet = { organizationId: string; modelId: string; model: ModelSummary; version: ModelVersion; versions: ModelVersion[]; writable: boolean; reloadVersions: () => Promise<void> };
export const useModel = () => useOutletContext<ModelOutlet>();

const TAB = "inline-flex h-9 items-center rounded-[8px] px-3 text-[13px] font-medium text-ink-muted no-underline hover:bg-surface-sunken aria-[current=page]:bg-accent-soft aria-[current=page]:text-accent";

/** `/organizations/:organizationId/models/:modelId/*`: the model's tabs and the version everything below shows. */
export function ModelShell() {
  const { workspace, locale } = useOrganization();
  const { modelId = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const text = modelMessages(locale);
  const organizationId = workspace.organization.id;
  const writable = workspace.subscription.writable;
  const confirm = useConfirm();
  const [model, setModel] = useState<ModelSummary | null>(null);
  const [versions, setVersions] = useState<ModelVersion[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  usePageTitle(model?.name ?? text.title);

  const reloadVersions = useCallback(async () => {
    try {
      const [models, loaded] = await Promise.all([loadModels(organizationId), loadVersions(organizationId, modelId)]);
      setModel(models.find((item) => item.id === modelId) ?? null);
      setVersions(loaded);
      setFailed(false);
    } catch { setFailed(true); }
  }, [organizationId, modelId]);
  useEffect(() => { void reloadVersions(); }, [reloadVersions]);

  const requested = search.get("version");
  const version = versions?.find((item) => item.id === requested) ?? versions?.find((item) => item.is_baseline);
  const select = (id: string | null) => setSearch(id ? { version: id } : {});

  async function fork() {
    const name = window.prompt(text.versionName, "");
    if (!name?.trim() || !version) return;
    setNotice(null);
    try { const created = await createVersion(organizationId, modelId, name.trim(), version.id); await reloadVersions(); select(created.id); } catch (cause) {
      setNotice(cause instanceof RuleError ? text.versionDuplicate : text.failed);
    }
  }
  async function remove() {
    if (!version || version.is_baseline) return;
    if (!(await confirm({ title: text.deleteVersionConfirm(version.name), confirmLabel: text.deleteVersion, destructive: true }))) return;
    setNotice(null);
    try { await deleteVersion(organizationId, modelId, version); select(null); await reloadVersions(); } catch (cause) {
      setNotice(cause instanceof RuleError ? text.versionHasForks : text.failed);
    }
  }

  if (failed) return <Alert tone="danger" role="alert">{text.failed}</Alert>;
  if (!model || !versions || !version) return <p role="status" className="text-ink-muted">{text.loading}</p>;
  const suffix = version.is_baseline ? "" : `?version=${version.id}`;
  const tab = (path: string, label: string, end = false) => <NavLink end={end} className={TAB} to={`${modelHref(organizationId, modelId)}${path}${suffix}`}>{label}</NavLink>;
  return (
    <div className="flex flex-col gap-4">
      <Link className="inline-flex w-fit text-[13px] text-ink-muted" to={modelsHref(organizationId)}>{text.back}</Link>
      <h1 className="m-0 text-xl font-semibold">{model.name}</h1>
      <div className="flex flex-wrap items-end gap-3">
        <Field label={text.version} className="w-56">{(control) => <Select {...control} value={version.id} onChange={(event) => select(versions.find((item) => item.id === event.target.value)?.is_baseline ? null : event.target.value)}>{versions.map((item) => <option key={item.id} value={item.id}>{item.is_baseline ? text.baseline : item.name}</option>)}</Select>}</Field>
        {writable ? <Button onClick={() => void fork()}>{text.newVersion}</Button> : null}
        {writable && !version.is_baseline ? <Button variant="ghost-danger" onClick={() => void remove()}>{text.deleteVersion}</Button> : null}
      </div>
      <nav aria-label={model.name} className="flex flex-wrap gap-1 border-b border-line pb-2">
        {tab("", text.tabs.structure, true)}
        {tab("/metrics", text.tabs.metrics)}
      </nav>
      {notice ? <Alert tone="danger" role="alert">{notice}</Alert> : null}
      <Outlet context={{ organizationId, modelId, model, version, versions, writable, reloadVersions } satisfies ModelOutlet} />
    </div>
  );
}
