import { useCallback, useEffect, useState } from "react";

import { useOrganization } from "../shell/organization-outlet";
import { Alert, Button, EmptyState, Field, Select, TextInput, useConfirm } from "../ui";
import { deleteSimulation, loadMetrics, loadSimulation, loadSimulations, runSimulation, type Metric, type Simulation, type SimulationMethod, type SimulationResult } from "./client";
import { ForecastChart } from "./ForecastChart";
import { modelMessages } from "./messages";
import { useModel } from "./ModelShell";

/** `…/models/:modelId/simulations`: forecast runs of the version, with what-if changes. */
export function SimulationsPage() {
  const { locale } = useOrganization();
  const { organizationId, modelId, version, writable } = useModel();
  const text = modelMessages(locale);
  const confirm = useConfirm();
  const [runs, setRuns] = useState<Simulation[] | null>(null);
  const [inputs, setInputs] = useState<Metric[]>([]);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [method, setMethod] = useState<SimulationMethod>("linear");
  const [horizon, setHorizon] = useState(12);
  const [changes, setChanges] = useState<Record<string, string>>({});

  const reload = useCallback(async () => {
    try {
      const [list, metrics] = await Promise.all([loadSimulations(organizationId, modelId, version.id), loadMetrics(organizationId, modelId, version.id)]);
      setRuns(list);
      setInputs(metrics.filter((metric) => !metric.derived));
    } catch { setError(text.failed); }
  }, [organizationId, modelId, version.id, text.failed]);
  useEffect(() => { setResult(null); void reload(); }, [reload]);

  async function run() {
    setBusy(true);
    setError(null);
    const adjustments = Object.entries(changes).map(([metric_key, raw]) => ({ metric_key, change_pct: Number(raw.replace(",", ".")) })).filter((item) => Number.isFinite(item.change_pct) && item.change_pct !== 0);
    try { setResult(await runSimulation(organizationId, modelId, version.id, { name, method, horizon_months: horizon, adjustments })); setName(""); } catch { setError(text.runFailed); }
    setBusy(false);
    await reload();
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <aside className="flex flex-col gap-3">
        <h2 className="m-0 text-[15px] font-semibold">{text.simulationsTitle}</h2>
        <p className="m-0 text-[13px] text-ink-muted">{text.simulationsDescription}</p>
        {runs !== null && runs.length === 0 ? <EmptyState title={text.noSimulations} /> : null}
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {(runs ?? []).map((item) => (
            <li key={item.id} className="flex items-center gap-2 rounded-[8px] border border-line bg-surface px-3 py-2 text-[13px]">
              <button type="button" className="flex min-w-0 flex-1 cursor-pointer flex-col border-0 bg-transparent p-0 text-left" onClick={() => void loadSimulation(organizationId, modelId, version.id, item.id).then(setResult).catch(() => setError(text.failed))}>
                <strong className="truncate">{item.name}</strong>
                <span className="text-xs text-ink-muted">{text.methods[item.method]} · {item.horizon_months}</span>
              </button>
              {writable ? <Button size="sm" variant="ghost-danger" onClick={() => void (async () => { if (await confirm({ title: item.name, confirmLabel: text.delete, destructive: true })) { await deleteSimulation(organizationId, modelId, version.id, item.id); if (result?.simulation.id === item.id) setResult(null); await reload(); } })()}>{text.delete}</Button> : null}
            </li>
          ))}
        </ul>
        {writable ? (
          <form className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-line bg-surface p-3" onSubmit={(event) => { event.preventDefault(); if (name.trim()) void run(); }}>
            <h3 className="m-0 text-[13px] font-semibold">{text.runSimulation}</h3>
            <Field label={text.simulationName}>{(control) => <TextInput {...control} value={name} onChange={(event) => setName(event.target.value)} />}</Field>
            <Field label={text.method}>{(control) => <Select {...control} value={method} onChange={(event) => setMethod(event.target.value as SimulationMethod)}>{(Object.keys(text.methods) as SimulationMethod[]).map((key) => <option key={key} value={key}>{text.methods[key]}</option>)}</Select>}</Field>
            <Field label={text.horizon}>{(control) => <Select {...control} value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>{[6, 12, 24, 36, 60].map((value) => <option key={value} value={value}>{value}</option>)}</Select>}</Field>
            {inputs.length > 0 ? (
              <fieldset className="m-0 flex flex-col gap-1 border-0 p-0">
                <legend className="mb-1 p-0 text-[13px] font-medium">{text.adjustments}</legend>
                {inputs.map((metric) => <label key={metric.id} className="flex items-center justify-between gap-2 text-[13px]"><span className="truncate">{metric.name}</span><input aria-label={`${metric.name} %`} inputMode="decimal" className="h-8 w-20 rounded-[6px] border border-line bg-surface px-2 text-right" value={changes[metric.key] ?? ""} onChange={(event) => setChanges({ ...changes, [metric.key]: event.target.value })} /></label>)}
              </fieldset>
            ) : null}
            <Button type="submit" variant="primary" disabled={!name.trim() || busy}>{text.runSimulation}</Button>
          </form>
        ) : null}
      </aside>
      <section className="flex min-w-0 flex-col gap-3">
        {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}
        {result ? <Result result={result} text={text} /> : null}
      </section>
    </div>
  );
}

function Result({ result, text }: { result: SimulationResult; text: ReturnType<typeof modelMessages> }) {
  const skipped = Object.entries(result.simulation.skipped);
  return (
    <>
      <h2 className="m-0 text-[15px] font-semibold">{result.simulation.name}</h2>
      {result.simulation.history_end ? <p className="m-0 text-[13px] text-ink-muted">{text.historyEnd(result.simulation.history_end.slice(0, 7))}</p> : null}
      {result.metrics.map((metric) => (
        <div key={metric.key} className="flex flex-col gap-1 rounded-[var(--radius-card)] border border-line bg-surface p-4">
          <h3 className="m-0 text-[14px] font-semibold">{metric.name} <span className="text-xs font-normal text-ink-muted">{metric.key}{metric.unit ? ` · ${metric.unit}` : ""}</span></h3>
          <ForecastChart metric={metric} bandLabel={text.forecastBand} />
        </div>
      ))}
      {skipped.length > 0 ? <Alert tone="info"><strong>{text.skippedMetrics}:</strong> {skipped.map(([key, reason]) => `${key} (${text.skippedReasons[reason] ?? reason})`).join(", ")}</Alert> : null}
    </>
  );
}
