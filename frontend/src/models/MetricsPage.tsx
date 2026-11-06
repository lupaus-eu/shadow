import { useCallback, useEffect, useMemo, useState } from "react";

import { useOrganization } from "../shell/organization-outlet";
import { Alert, Badge, Button, EmptyState, Field, Select, TextInput, useConfirm } from "../ui";
import { createMetric, deleteMetric, loadGraph, loadMetrics, loadSeries, RuleError, saveValues, StaleVersionError, updateMetric, type GraphNode, type Metric, type Series } from "./client";
import { modelMessages } from "./messages";
import { useModel } from "./ModelShell";

const monthKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`;
const addMonths = (start: string, count: number) => {
  const [year, month] = start.split("-").map(Number);
  return monthKey(new Date(year, month - 1 + count, 1));
};

/** `…/models/:modelId/metrics`: the version's KPIs, their formulas and monthly values. */
export function MetricsPage() {
  const { locale } = useOrganization();
  const { organizationId, modelId, version, writable } = useModel();
  const text = modelMessages(locale);
  const confirm = useConfirm();
  const [metrics, setMetrics] = useState<Metric[] | null>(null);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState({ key: "", name: "" });

  const reload = useCallback(async () => {
    try {
      const [list, graph] = await Promise.all([loadMetrics(organizationId, modelId, version.id), loadGraph(organizationId, modelId, version.is_baseline ? null : version.id)]);
      setMetrics(list);
      setNodes(graph.nodes);
    } catch { setError(text.failed); }
  }, [organizationId, modelId, version.id, version.is_baseline, text.failed]);
  useEffect(() => { setSelectedId(null); void reload(); }, [reload]);

  const selected = metrics?.find((item) => item.id === selectedId) ?? null;

  async function act(action: () => Promise<unknown>, rule = text.metricInvalid) {
    setError(null);
    try { await action(); } catch (cause) {
      setError(cause instanceof RuleError ? rule : cause instanceof StaleVersionError ? text.stale : text.failed);
    }
    await reload();
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="flex flex-col gap-3">
        <h2 className="m-0 text-[15px] font-semibold">{text.metricsTitle}</h2>
        <p className="m-0 text-[13px] text-ink-muted">{text.metricsDescription}</p>
        {metrics !== null && metrics.length === 0 ? <EmptyState title={text.noMetrics} /> : null}
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {(metrics ?? []).map((metric) => (
            <li key={metric.id}>
              <button type="button" aria-current={metric.id === selectedId} onClick={() => setSelectedId(metric.id)} className="flex w-full cursor-pointer items-center gap-2 rounded-[8px] border border-line bg-surface px-3 py-2 text-left text-[13px] aria-[current=true]:border-accent">
                <span className="flex min-w-0 flex-1 flex-col"><strong className="truncate">{metric.name}</strong><span className="text-xs text-ink-muted">{metric.key}</span></span>
                {metric.derived ? <Badge>{text.derived}</Badge> : null}
              </button>
            </li>
          ))}
        </ul>
        {writable ? (
          <form className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-line bg-surface p-3" onSubmit={(event) => { event.preventDefault(); void act(async () => { const created = await createMetric(organizationId, modelId, version.id, { key: draft.key, name: draft.name, unit: null, node_id: null, formula: null }); setDraft({ key: "", name: "" }); setSelectedId(created.id); }); }}>
            <h3 className="m-0 text-[13px] font-semibold">{text.newMetric}</h3>
            <Field label={text.metricName}>{(control) => <TextInput {...control} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />}</Field>
            <Field label={text.metricKey} hint={text.metricKeyHint}>{(control) => <TextInput {...control} value={draft.key} onChange={(event) => setDraft({ ...draft, key: event.target.value })} />}</Field>
            <Button type="submit" variant="primary" disabled={!draft.name.trim() || !/^[a-z][a-z0-9_]{0,39}$/.test(draft.key)}>{text.newMetric}</Button>
          </form>
        ) : null}
      </aside>
      <section className="flex min-w-0 flex-col gap-3">
        {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}
        {selected ? (
          <MetricEditor key={`${selected.id}-${selected.version}`} metric={selected} nodes={nodes} writable={writable} text={text}
            onSave={(input) => act(() => updateMetric(organizationId, modelId, version.id, selected, input))}
            onDelete={async () => { if (await confirm({ title: selected.name, confirmLabel: text.delete, destructive: true })) { setSelectedId(null); await act(() => deleteMetric(organizationId, modelId, version.id, selected), text.metricReadByFormulas(metrics?.filter((item) => item.formula?.includes(selected.key)).map((item) => item.key).join(", ") ?? "")); } }}
            loadSeries={() => loadSeries(organizationId, modelId, version.id, selected.id)}
            saveValues={(values) => saveValues(organizationId, modelId, version.id, selected.id, values)} />
        ) : <p className="m-0 text-[13px] text-ink-muted">{text.noSelection}</p>}
      </section>
    </div>
  );
}

type Text = ReturnType<typeof modelMessages>;

function MetricEditor({ metric, nodes, writable, text, onSave, onDelete, loadSeries, saveValues }: { metric: Metric; nodes: GraphNode[]; writable: boolean; text: Text; onSave: (input: { key: string; name: string; unit: string | null; node_id: string | null; formula: string | null }) => Promise<void>; onDelete: () => Promise<void>; loadSeries: () => Promise<Series>; saveValues: (values: { period: string; value: number | null }[]) => Promise<Series> }) {
  const [name, setName] = useState(metric.name);
  const [unit, setUnit] = useState(metric.unit ?? "");
  const [nodeId, setNodeId] = useState(metric.node_id ?? "");
  const [formula, setFormula] = useState(metric.formula ?? "");
  return (
    <>
      <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4">
        <h2 className="m-0 text-[15px] font-semibold">{metric.name} <span className="text-xs font-normal text-ink-muted">{metric.key}</span></h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={text.metricName}>{(control) => <TextInput {...control} value={name} disabled={!writable} onChange={(event) => setName(event.target.value)} />}</Field>
          <Field label={text.metricUnit}>{(control) => <TextInput {...control} value={unit} disabled={!writable} onChange={(event) => setUnit(event.target.value)} />}</Field>
          <Field label={text.metricNode}>{(control) => <Select {...control} value={nodeId} disabled={!writable} onChange={(event) => setNodeId(event.target.value)}><option value="">{text.noNode}</option>{nodes.map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}</Select>}</Field>
          <Field label={text.formula} hint={text.formulaHint}>{(control) => <TextInput {...control} value={formula} disabled={!writable} onChange={(event) => setFormula(event.target.value)} />}</Field>
        </div>
        {writable ? <div className="flex gap-2"><Button variant="primary" disabled={!name.trim()} onClick={() => void onSave({ key: metric.key, name, unit: unit.trim() || null, node_id: nodeId || null, formula: formula.trim() || null })}>{text.save}</Button><Button variant="ghost-danger" onClick={() => void onDelete()}>{text.delete}</Button></div> : null}
      </div>
      <Values key={metric.formula ?? ""} metric={metric} writable={writable} text={text} loadSeries={loadSeries} saveValues={saveValues} />
    </>
  );
}

function Values({ metric, writable, text, loadSeries, saveValues }: { metric: Metric; writable: boolean; text: Text; loadSeries: () => Promise<Series>; saveValues: (values: { period: string; value: number | null }[]) => Promise<Series> }) {
  const [series, setSeries] = useState<Record<string, number>>({});
  const [start, setStart] = useState(() => monthKey(new Date(new Date().getFullYear(), 0, 1)));
  const [count, setCount] = useState(24);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [failed, setFailed] = useState(false);
  const [saved, setSaved] = useState(false);
  const apply = (loaded: Series) => setSeries(Object.fromEntries(loaded.points.filter((point) => point.value !== null).map((point) => [point.period, point.value as number])));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void loadSeries().then(apply).catch(() => setFailed(true)); }, [metric.id, metric.version, metric.formula]);
  const periods = useMemo(() => Array.from({ length: count }, (_, index) => addMonths(start, index)), [start, count]);
  const editable = writable && !metric.derived;

  async function save() {
    setFailed(false);
    setSaved(false);
    const values = Object.entries(edits).map(([period, raw]) => ({ period, value: raw.trim() === "" ? null : Number(raw.replace(",", ".")) })).filter((point) => point.value === null || Number.isFinite(point.value));
    try { apply(await saveValues(values)); setEdits({}); setSaved(true); } catch { setFailed(true); }
  }

  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4">
      <h3 className="m-0 text-[14px] font-semibold">{text.values}</h3>
      <div className="flex flex-wrap items-end gap-3">
        <Field label={text.from} className="w-44">{(control) => <TextInput {...control} type="month" value={start.slice(0, 7)} onChange={(event) => event.target.value && setStart(`${event.target.value}-01`)} />}</Field>
        <Field label={text.months} className="w-28">{(control) => <Select {...control} value={count} onChange={(event) => setCount(Number(event.target.value))}>{[12, 24, 36, 60].map((value) => <option key={value} value={value}>{value}</option>)}</Select>}</Field>
        {editable ? <Button variant="primary" disabled={Object.keys(edits).length === 0} onClick={() => void save()}>{text.save}</Button> : null}
        {saved ? <span role="status" className="text-[13px] text-success-ink">{text.saved}</span> : null}
      </div>
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      <LineChart periods={periods} series={series} edits={edits} label={text.chart} unit={metric.unit} />
      <div className="max-h-80 overflow-auto"><table className="w-full text-[13px]"><tbody>
        {periods.map((period) => (
          <tr key={period}>
            <th scope="row" className="w-28 py-0.5 pr-3 text-left font-normal text-ink-muted">{period.slice(0, 7)}</th>
            <td><input aria-label={`${metric.name} ${period.slice(0, 7)}`} inputMode="decimal" disabled={!editable} className="h-8 w-40 rounded-[6px] border border-line bg-surface px-2 text-right" value={edits[period] ?? (series[period] !== undefined ? String(Math.round(series[period] * 1e6) / 1e6) : "")} onChange={(event) => setEdits({ ...edits, [period]: event.target.value })} /></td>
          </tr>
        ))}
      </tbody></table></div>
    </div>
  );
}

function LineChart({ periods, series, edits, label, unit }: { periods: string[]; series: Record<string, number>; edits: Record<string, string>; label: string; unit: string | null }) {
  const points = periods.map((period, index) => {
    const raw = edits[period];
    const value = raw !== undefined ? (raw.trim() === "" ? undefined : Number(raw.replace(",", "."))) : series[period];
    return { index, value: value !== undefined && Number.isFinite(value) ? value : undefined };
  });
  const known = points.filter((point): point is { index: number; value: number } => point.value !== undefined);
  if (known.length < 2) return null;
  const low = Math.min(...known.map((point) => point.value));
  const high = Math.max(...known.map((point) => point.value));
  const span = high - low || 1;
  const x = (index: number) => 40 + (index / Math.max(periods.length - 1, 1)) * 560;
  const y = (value: number) => 130 - ((value - low) / span) * 110;
  return (
    <svg role="img" aria-label={label} viewBox="0 0 620 150" width="100%" className="text-accent">
      <line x1="40" y1="130" x2="600" y2="130" stroke="#bbb" />
      <text x="4" y="24" fontSize="10" fill="#666">{Math.round(high * 100) / 100}</text>
      <text x="4" y="130" fontSize="10" fill="#666">{Math.round(low * 100) / 100}</text>
      {unit ? <text x="600" y="145" fontSize="10" textAnchor="end" fill="#666">{unit}</text> : null}
      <polyline fill="none" stroke="currentColor" strokeWidth="2" points={known.map((point) => `${x(point.index)},${y(point.value)}`).join(" ")} />
    </svg>
  );
}
