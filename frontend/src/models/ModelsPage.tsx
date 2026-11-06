import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";

import { Section } from "../admin/Section";
import { usePageTitle } from "../shell/AppShell";
import { modelHref } from "../shell/nav";
import { useOrganization } from "../shell/organization-outlet";
import { Alert, Button, EmptyState, Field, TextInput, useConfirm } from "../ui";
import { createModel, deleteModel, loadModels, renameModel, RuleError, StaleVersionError, type ModelSummary } from "./client";
import { modelMessages } from "./messages";

/** `/organizations/:organizationId/models`: the Organization's models; Owners and Admins manage them. */
export function ModelsPage() {
  const { workspace, locale } = useOrganization();
  const text = modelMessages(locale);
  const organizationId = workspace.organization.id;
  const manager = workspace.membership.role !== "member";
  const writable = workspace.subscription.writable;
  const confirm = useConfirm();
  usePageTitle(text.title);
  const [models, setModels] = useState<ModelSummary[] | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(() => void loadModels(organizationId).then(setModels).catch(() => setError(text.failed)), [organizationId, text.failed]);
  useEffect(refresh, [refresh]);

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try { await action(); } catch (cause) {
      setError(cause instanceof RuleError ? text.duplicate : cause instanceof StaleVersionError ? text.stale : text.failed);
    }
    refresh();
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      <Section title={text.title} description={text.description}>
        {!writable ? <Alert tone="warning">{text.readOnly}</Alert> : null}
        {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}
        {models !== null && models.length === 0 ? <EmptyState title={text.empty} /> : null}
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {(models ?? []).map((model) => (
            <li key={model.id} className="flex flex-wrap items-center gap-3 rounded-[10px] border border-line px-4 py-3">
              {renaming?.id === model.id ? (
                <form className="flex flex-1 items-end gap-2" onSubmit={(event) => { event.preventDefault(); void act(async () => { await renameModel(organizationId, model, renaming.name, model.description); setRenaming(null); }); }}>
                  <Field label={text.nameLabel} className="flex-1">{(control) => <TextInput {...control} value={renaming.name} onChange={(event) => setRenaming({ id: model.id, name: event.target.value })} />}</Field>
                  <Button type="submit" variant="primary" disabled={!renaming.name.trim()}>{text.rename}</Button>
                  <Button onClick={() => setRenaming(null)}>{text.cancel}</Button>
                </form>
              ) : (
                <>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <Link className="font-semibold text-ink" to={modelHref(organizationId, model.id)}>{model.name}</Link>
                    <span className="text-xs text-ink-muted">{text.nodesCount(model.nodes)}{model.description ? ` · ${model.description}` : ""}</span>
                  </div>
                  <Link className="text-[13px]" to={modelHref(organizationId, model.id)}>{text.open}</Link>
                  {manager && writable ? <Button size="sm" onClick={() => setRenaming({ id: model.id, name: model.name })}>{text.rename}</Button> : null}
                  {manager && writable ? <Button size="sm" variant="ghost-danger" onClick={() => void (async () => { if (await confirm({ title: text.deleteConfirm(model.name), confirmLabel: text.delete, destructive: true })) await act(() => deleteModel(organizationId, model)); })()}>{text.delete}</Button> : null}
                </>
              )}
            </li>
          ))}
        </ul>
        {manager && writable ? (
          <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); if (name.trim()) void act(async () => { await createModel(organizationId, name, description.trim() || null); setName(""); setDescription(""); }); }}>
            <Field label={text.nameLabel} className="min-w-56 flex-1">{(control) => <TextInput {...control} value={name} onChange={(event) => setName(event.target.value)} />}</Field>
            <Field label={text.descriptionLabel} className="min-w-56 flex-1">{(control) => <TextInput {...control} value={description} onChange={(event) => setDescription(event.target.value)} />}</Field>
            <Button type="submit" variant="primary" disabled={!name.trim()}>{text.create}</Button>
          </form>
        ) : null}
      </Section>
    </div>
  );
}
