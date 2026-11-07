import { useCallback, useEffect, useState } from "react";

import { useOrganization } from "../shell/organization-outlet";
import { Alert, Button, Field, Select, TextInput, useConfirm } from "../ui";
import { allowConnection, createConnectionType, createNodeType, deleteConnectionType, deleteNodeType, disallowConnection, loadGraph, RuleError, StaleVersionError, updateConnectionType, updateNodeType, type Graph } from "./client";
import { modelMessages } from "./messages";
import { useModel } from "./ModelShell";

/** `…/models/:modelId/types`: the Model's node types, connection types, and the rules for connecting them. */
export function TypesPage() {
  const { locale } = useOrganization();
  const { organizationId, modelId, writable } = useModel();
  const text = modelMessages(locale);
  const confirm = useConfirm();
  const [graph, setGraph] = useState<Graph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nodeDraft, setNodeDraft] = useState({ name: "", color: "#3b82f6" });
  const [linkDraft, setLinkDraft] = useState({ name: "", style: "solid", arrow: true });
  const [rule, setRule] = useState({ connection_type_id: "", source_node_type_id: "", target_node_type_id: "" });

  const reload = useCallback(async () => {
    try { setGraph(await loadGraph(organizationId, modelId)); } catch { setError(text.failed); }
  }, [organizationId, modelId, text.failed]);
  useEffect(() => { void reload(); }, [reload]);

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try { await action(); } catch (cause) {
      setError(cause instanceof RuleError ? text.typeInUse : cause instanceof StaleVersionError ? text.stale : text.failed);
    }
    await reload();
  }

  if (!graph) return error ? <Alert tone="danger" role="alert">{error}</Alert> : <p role="status" className="text-ink-muted">{text.loading}</p>;
  const nodeTypeName = (id: string) => graph.node_types.find((item) => item.id === id)?.name ?? "";
  const linkTypeName = (id: string) => graph.connection_types.find((item) => item.id === id)?.name ?? "";
  return (
    <div className="flex flex-col gap-6">
      <p className="m-0 text-[13px] text-ink-muted">{text.typesDescription}</p>
      {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}

      <section className="flex flex-col gap-3" aria-label={text.nodeTypes}>
        <h2 className="m-0 text-[15px] font-semibold">{text.nodeTypes}</h2>
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {graph.node_types.map((type) => (
            <li key={type.id} className="flex flex-wrap items-center gap-2">
              <input type="color" aria-label={text.typeColor} defaultValue={type.color} disabled={!writable} onBlur={(event) => event.target.value.toLowerCase() !== type.color.toLowerCase() && void act(() => updateNodeType(organizationId, modelId, type, { color: event.target.value }))} />
              <TextInput aria-label={text.typeName} defaultValue={type.name} disabled={!writable} className="w-56" onBlur={(event) => event.target.value.trim() && event.target.value.trim() !== type.name && void act(() => updateNodeType(organizationId, modelId, type, { name: event.target.value }))} />
              {writable ? <Button variant="ghost-danger" onClick={async () => { if (await confirm({ title: text.deleteConfirm(type.name), confirmLabel: text.delete, destructive: true })) void act(() => deleteNodeType(organizationId, modelId, type)); }}>{text.delete}</Button> : null}
            </li>
          ))}
        </ul>
        {writable ? (
          <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); void act(async () => { await createNodeType(organizationId, modelId, nodeDraft); setNodeDraft({ ...nodeDraft, name: "" }); }); }}>
            <Field label={text.typeName} className="w-56">{(control) => <TextInput {...control} required maxLength={80} value={nodeDraft.name} onChange={(event) => setNodeDraft({ ...nodeDraft, name: event.target.value })} />}</Field>
            <Field label={text.typeColor}>{(control) => <input {...control} type="color" value={nodeDraft.color} onChange={(event) => setNodeDraft({ ...nodeDraft, color: event.target.value })} />}</Field>
            <Button type="submit">{text.add}</Button>
          </form>
        ) : null}
      </section>

      <section className="flex flex-col gap-3" aria-label={text.connectionTypes}>
        <h2 className="m-0 text-[15px] font-semibold">{text.connectionTypes}</h2>
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {graph.connection_types.map((type) => (
            <li key={type.id} className="flex flex-wrap items-center gap-2">
              <TextInput aria-label={text.typeName} defaultValue={type.name} disabled={!writable} className="w-56" onBlur={(event) => event.target.value.trim() && event.target.value.trim() !== type.name && void act(() => updateConnectionType(organizationId, modelId, type, { name: event.target.value }))} />
              <Select aria-label={text.typeStyle} value={type.style} disabled={!writable} onChange={(event) => void act(() => updateConnectionType(organizationId, modelId, type, { style: event.target.value }))}>{Object.entries(text.styles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
              <label className="flex items-center gap-1 text-[13px]"><input type="checkbox" checked={type.target_end === "arrow"} disabled={!writable} onChange={(event) => void act(() => updateConnectionType(organizationId, modelId, type, { target_end: event.target.checked ? "arrow" : "none" }))} />{text.arrowAtTarget}</label>
              <label className="flex items-center gap-1 text-[13px]"><input type="checkbox" checked={type.source_end === "arrow"} disabled={!writable} onChange={(event) => void act(() => updateConnectionType(organizationId, modelId, type, { source_end: event.target.checked ? "arrow" : "none" }))} />{text.arrowAtSource}</label>
              {writable ? <Button variant="ghost-danger" onClick={async () => { if (await confirm({ title: text.deleteConfirm(type.name), confirmLabel: text.delete, destructive: true })) void act(() => deleteConnectionType(organizationId, modelId, type)); }}>{text.delete}</Button> : null}
            </li>
          ))}
        </ul>
        {writable ? (
          <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); void act(async () => { await createConnectionType(organizationId, modelId, { name: linkDraft.name, style: linkDraft.style, source_end: "none", target_end: linkDraft.arrow ? "arrow" : "none" }); setLinkDraft({ ...linkDraft, name: "" }); }); }}>
            <Field label={text.typeName} className="w-56">{(control) => <TextInput {...control} required maxLength={80} value={linkDraft.name} onChange={(event) => setLinkDraft({ ...linkDraft, name: event.target.value })} />}</Field>
            <Field label={text.typeStyle}>{(control) => <Select {...control} value={linkDraft.style} onChange={(event) => setLinkDraft({ ...linkDraft, style: event.target.value })}>{Object.entries(text.styles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>}</Field>
            <Button type="submit">{text.add}</Button>
          </form>
        ) : null}
      </section>

      <section className="flex flex-col gap-3" aria-label={text.allowedRules}>
        <h2 className="m-0 text-[15px] font-semibold">{text.allowedRules}</h2>
        <p className="m-0 text-[13px] text-ink-muted">{text.allowedDescription}</p>
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {graph.allowed_connections.map((item) => (
            <li key={`${item.connection_type_id}${item.source_node_type_id}${item.target_node_type_id}`} className="flex flex-wrap items-center gap-2 text-[13px]">
              <span>{nodeTypeName(item.source_node_type_id)} → {linkTypeName(item.connection_type_id)} → {nodeTypeName(item.target_node_type_id)}</span>
              {writable ? <Button variant="ghost-danger" onClick={() => void act(() => disallowConnection(organizationId, modelId, item))}>{text.removeRule}</Button> : null}
            </li>
          ))}
        </ul>
        {writable ? (
          <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); void act(() => allowConnection(organizationId, modelId, rule)); }}>
            <Field label={text.ruleSource}>{(control) => <Select {...control} required value={rule.source_node_type_id} onChange={(event) => setRule({ ...rule, source_node_type_id: event.target.value })}><option value="" />{graph.node_types.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select>}</Field>
            <Field label={text.connectionTypes}>{(control) => <Select {...control} required value={rule.connection_type_id} onChange={(event) => setRule({ ...rule, connection_type_id: event.target.value })}><option value="" />{graph.connection_types.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select>}</Field>
            <Field label={text.ruleTarget}>{(control) => <Select {...control} required value={rule.target_node_type_id} onChange={(event) => setRule({ ...rule, target_node_type_id: event.target.value })}><option value="" />{graph.node_types.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select>}</Field>
            <Button type="submit">{text.addRule}</Button>
          </form>
        ) : null}
      </section>
    </div>
  );
}
