import { useEffect, useMemo, useRef, useState } from "react";
import { fetchEvents } from "../../api/events";
import type { EventDto } from "../../api/events";
import {
  createPrediction,
  fetchPrediction,
  fetchPredictions,
  preflightPredictions,
  type PredictionCutoffMode,
  type PredictionPreflightDto,
  type PredictionTargetDto,
  type PredictionVersionDetailDto
} from "../../api/predictions";
import { fetchScenarios } from "../../api/scenarios";
import type { ScenarioDto } from "../../api/scenarios";
import { fetchTimeseries } from "../../api/timeseries";
import type { TimeserieDto } from "../../api/timeseries";
import {
  buildPredictionMetricCharts,
  formatModelKind,
  predictionChartAxisTicks,
  predictionVersionStatus,
  type PredictionChartLine
} from "./predictionChart";

type EventOption = EventDto & {
  selectionId: string;
  scenarioId: string;
  scenarioName: string;
};

const lineColors = ["#c94a11", "#2563eb", "#8b5cf6", "#0f766e", "#b45309", "#be185d"];
const NON_NUMERIC_METRIC_REASON = "Only numeric metrics can be forecast.";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function inputDate(event: EventOption | undefined): string {
  return event?.targetDate ?? "";
}

function isNumericPredictionTarget(target: PredictionTargetDto): boolean {
  // TASK-041B identifies non-numeric targets with this stable eligibility reason.
  // Other ineligible numeric metrics remain selectable so their missing results
  // can be communicated in the chart.
  return target.reason !== NON_NUMERIC_METRIC_REASON;
}

function toggleSet(set: Set<string>, value: string): Set<string> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export default function PredictionsTab(props: { orgId: string }) {
  const [scenarios, setScenarios] = useState<ScenarioDto[]>([]);
  const [events, setEvents] = useState<EventOption[]>([]);
  const [versions, setVersions] = useState<PredictionVersionDetailDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [name, setName] = useState("");
  const [targetScenarioIds, setTargetScenarioIds] = useState<Set<string>>(new Set());
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [startEventId, setStartEventId] = useState("");
  const [endEventId, setEndEventId] = useState("");
  const [cutoffMode, setCutoffMode] = useState<PredictionCutoffMode>("asOfStart");
  const [preflight, setPreflight] = useState<PredictionPreflightDto | null>(null);
  const [manualPeriods, setManualPeriods] = useState<Record<string, number>>({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [selectedVersionIds, setSelectedVersionIds] = useState<Set<string>>(new Set());
  const [selectedScenarioFilter, setSelectedScenarioFilter] = useState<Set<string>>(new Set());
  const [selectedModelKinds, setSelectedModelKinds] = useState<Set<string>>(new Set());
  const [selectedMetricIds, setSelectedMetricIds] = useState<Set<string>>(new Set());
  const [plotStartDate, setPlotStartDate] = useState("");
  const [plotEndDate, setPlotEndDate] = useState("");
  const [includeReality, setIncludeReality] = useState(false);
  const [realityTimeseries, setRealityTimeseries] = useState<TimeserieDto[]>([]);
  const [realityError, setRealityError] = useState("");

  const targetScenarios = useMemo(
    () => scenarios.filter((scenario) => !scenario.protected && scenario.id !== "reality"),
    [scenarios]
  );
  const comparisonScenarios = useMemo(() => {
    const names = new Map(scenarios.map((scenario) => [scenario.id, scenario.name]));
    for (const version of versions) for (const target of version.targets) {
      if (!names.has(target.scenarioId)) {
        names.set(target.scenarioId, `Deleted scenario (${target.scenarioId})`);
      }
    }
    return [...names.entries()]
      .filter(([id]) => id !== "reality")
      .sort((left, right) => left[1].localeCompare(right[1]));
  }, [scenarios, versions]);
  const realityScenario = useMemo(
    () => scenarios.find((scenario) => scenario.protected || scenario.id === "reality"),
    [scenarios]
  );
  const scenarioNames = useMemo(
    () => new Map(comparisonScenarios),
    [comparisonScenarios]
  );
  const eventById = useMemo(
    () => new Map(events.map((event) => [event.selectionId, event])),
    [events]
  );
  const availableStartEvents = useMemo(
    () => events.filter((event) => !endDate || event.targetDate < endDate),
    [endDate, events]
  );
  const availableEndEvents = useMemo(
    () => events.filter((event) => !startDate || event.targetDate > startDate),
    [events, startDate]
  );
  const invalidDates = Boolean(startDate && endDate && startDate >= endDate);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    void (async () => {
      try {
        setLoading(true);
        setError("");
        const loadedScenarios = await fetchScenarios(props.orgId, controller.signal);
        const eventLists = await Promise.all(
          loadedScenarios.map(async (scenario) => ({
            scenario,
            items: await fetchEvents(props.orgId, scenario.id, controller.signal)
          }))
        );
        const versionSummaries = await fetchPredictions(props.orgId, controller.signal);
        const details = await Promise.all(
          versionSummaries.map((version) => fetchPrediction(props.orgId, version.id, controller.signal))
        );
        const data = {
          scenarios: loadedScenarios,
          events: eventLists
            .flatMap(({ scenario, items }) => items.map((item) => ({
              ...item,
              selectionId: `${scenario.id}:${item.id}`,
              scenarioId: scenario.id,
              scenarioName: scenario.name
            })))
            .sort((left, right) => left.targetDate.localeCompare(right.targetDate) || left.name.localeCompare(right.name)),
          versions: details
        };
        if (cancelled) return;
        setScenarios(data.scenarios);
        setEvents(data.events);
        setVersions(data.versions);
        const targets = data.scenarios
          .filter((scenario) => !scenario.protected && scenario.id !== "reality")
          .map((scenario) => scenario.id);
        setTargetScenarioIds(new Set(targets));
        setSelectedScenarioFilter(new Set([
          ...targets,
          ...data.versions.flatMap((version) => version.targets.map((target) => target.scenarioId))
        ]));
        setSelectedVersionIds(new Set(data.versions.map((version) => version.id)));
        setSelectedModelKinds(
          new Set(data.versions.flatMap((version) => version.targets.flatMap((target) => target.results.map((result) => result.kind))))
        );
        setSelectedMetricIds(new Set(data.versions.flatMap((version) => version.targets
          .filter(isNumericPredictionTarget)
          .map((target) => target.metricId))));
      } catch (loadError) {
        if (!cancelled && (loadError as { name?: string }).name !== "AbortError") {
          setError(`Could not load Predictions. ${errorMessage(loadError)}`);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [props.orgId, refreshVersion]);

  useEffect(() => {
    if (!includeReality || !realityScenario) return;
    const controller = new AbortController();
    void fetchTimeseries(props.orgId, realityScenario.id, controller.signal)
      .then(setRealityTimeseries)
      .catch((loadError: unknown) => {
        if ((loadError as { name?: string }).name !== "AbortError") {
          setRealityError(`Could not load current Reality data. ${errorMessage(loadError)}`);
        }
      });
    return () => controller.abort();
  }, [includeReality, props.orgId, realityScenario]);

  const allModelKinds = useMemo(
    () => [...new Set(versions.flatMap((version) => version.targets.flatMap((target) => target.results.map((result) => result.kind))))].sort(),
    [versions]
  );
  const allMetrics = useMemo(() => {
    const metrics = new Map<string, { name: string; unit: string | null }>();
    for (const version of versions) for (const target of version.targets) {
      if (!isNumericPredictionTarget(target)) continue;
      metrics.set(target.metricId, { name: target.metricName, unit: target.unit });
    }
    return [...metrics.entries()].sort((left, right) => left[1].name.localeCompare(right[1].name));
  }, [versions]);
  const charts = useMemo(() => buildPredictionMetricCharts({
    versions,
    selectedVersionIds,
    selectedScenarioIds: selectedScenarioFilter,
    selectedModelKinds,
    selectedMetricIds,
    scenarioNames,
    startDate: plotStartDate,
    endDate: plotEndDate,
    realityTimeseries,
    includeReality
  }), [includeReality, plotEndDate, plotStartDate, realityTimeseries, scenarioNames, selectedMetricIds, selectedModelKinds, selectedScenarioFilter, selectedVersionIds, versions]);

  function invalidatePreflight() {
    setPreflight(null);
    setFormError("");
  }

  function updateStartDate(value: string) {
    setStartDate(value);
    setStartEventId("");
    if (value && (eventById.get(endEventId)?.targetDate ?? "") <= value) setEndEventId("");
    invalidatePreflight();
  }

  function updateEndDate(value: string) {
    setEndDate(value);
    setEndEventId("");
    if (value && (eventById.get(startEventId)?.targetDate ?? "") >= value) setStartEventId("");
    invalidatePreflight();
  }

  function selectStartEvent(value: string) {
    const date = inputDate(eventById.get(value));
    setStartEventId(value);
    setStartDate(date);
    if (date && (eventById.get(endEventId)?.targetDate ?? "") <= date) setEndEventId("");
    invalidatePreflight();
  }

  function selectEndEvent(value: string) {
    const date = inputDate(eventById.get(value));
    setEndEventId(value);
    setEndDate(date);
    if (date && (eventById.get(startEventId)?.targetDate ?? "") >= date) setStartEventId("");
    invalidatePreflight();
  }

  async function handlePreflight() {
    if (!targetScenarioIds.size) return setFormError("Select at least one prediction target scenario.");
    if (!startDate || !endDate) return setFormError("Choose both a start and an end date.");
    if (invalidDates) return setFormError("The start date must be earlier than the end date.");
    try {
      setSubmitting(true);
      setFormError("");
      const response = await preflightPredictions(props.orgId, {
        targetScenarioIds: [...targetScenarioIds], startDate, endDate, cutoffMode,
        manualSeasonalPeriods: manualPeriods
      });
      setPreflight(response);
      setManualPeriods((current) => Object.fromEntries(
        response.metrics
          .filter((metric) => metric.requiresManualSeasonalPeriod)
          .map((metric) => [metric.metricId, current[metric.metricId] ?? 2])
      ));
    } catch (requestError) {
      setFormError(`Preflight failed. ${errorMessage(requestError)}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCreate() {
    const missingManualPeriod = preflight?.metrics.some(
      (metric) => metric.requiresManualSeasonalPeriod && (manualPeriods[metric.metricId] ?? 0) < 2
    );
    if (!preflight) return setFormError("Run preflight before creating a prediction version.");
    if (!preflight.metrics.length) return setFormError("Preflight found no forecastable metrics to create.");
    if (!name.trim()) return setFormError("Enter a unique prediction-version name.");
    if (missingManualPeriod) return setFormError("Enter every required manual seasonal period before creating.");
    try {
      setSubmitting(true);
      setFormError("");
      const created = await createPrediction(props.orgId, {
        name: name.trim(), targetScenarioIds: [...targetScenarioIds], startDate, endDate,
        cutoffMode, manualSeasonalPeriods: manualPeriods
      });
      setVersions((current) => [created, ...current]);
      setSelectedVersionIds((current) => new Set(current).add(created.id));
      setSelectedScenarioFilter((current) => new Set([...current, ...created.targets.map((target) => target.scenarioId)]));
      setSelectedModelKinds((current) => new Set([...current, ...created.targets.flatMap((target) => target.results.map((result) => result.kind))]));
      setSelectedMetricIds((current) => new Set([...current, ...created.targets
        .filter(isNumericPredictionTarget)
        .map((target) => target.metricId)]));
      setName("");
      setPreflight(null);
    } catch (requestError) {
      setFormError(`Could not create prediction version. ${errorMessage(requestError)}`);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <section className="predictions-tab" aria-busy="true"><h1 className="page-title">Predictions</h1><p role="status">Loading prediction workspace…</p></section>;
  if (error) return <section className="predictions-tab"><h1 className="page-title">Predictions</h1><div className="alert alert--danger" role="alert"><p className="alert__title">Predictions could not be loaded</p><p className="alert__text">{error}</p><button className="btn btn--secondary" type="button" onClick={() => setRefreshVersion((current) => current + 1)}>Try again</button></div></section>;

  return <section className="predictions-tab" aria-labelledby="predictions-heading">
    <header><p className="eyebrow">Forecasting</p><h1 id="predictions-heading" className="page-title">Predictions</h1><p className="muted">Create immutable, comparable model outputs. Reality remains live manually entered realized data and is never a prediction target.</p></header>
    <div className="predictions-layout">
      <section className="predictions-panel" aria-labelledby="generation-heading">
        <h2 id="generation-heading">Generate a prediction version</h2>
        <label className="form-row"><span className="form-label form-label--required">Version name</span><input className="input" value={name} onChange={(event) => { setName(event.target.value); }} /></label>
        <ScenarioMultiSelect borderless required items={targetScenarios.map((scenario) => [scenario.id, scenario.name])} selected={targetScenarioIds} onChange={(selected) => { setTargetScenarioIds(selected); invalidatePreflight(); }} />
        {!targetScenarios.length ? <p className="alert alert--info" role="status">No active non-Reality scenarios are available for prediction.</p> : null}
        <div className="predictions-date-grid">
          <label className="form-row"><span className="form-label form-label--required">Start date</span><input className="input" type="date" value={startDate} onChange={(event) => updateStartDate(event.target.value)} /></label>
          <label className="form-row"><span className="form-label form-label--required">End date</span><input className="input" type="date" value={endDate} onChange={(event) => updateEndDate(event.target.value)} /></label>
          <label className="form-row"><span className="form-label">Start event</span><select className="select" value={startEventId} onChange={(event) => selectStartEvent(event.target.value)}><option value="">No event selected</option>{availableStartEvents.map((event) => <option value={event.selectionId} key={event.selectionId}>{event.targetDate} · {event.scenarioName} · {event.name}</option>)}</select></label>
          <label className="form-row"><span className="form-label">End event</span><select className="select" value={endEventId} onChange={(event) => selectEndEvent(event.target.value)}><option value="">No event selected</option>{availableEndEvents.map((event) => <option value={event.selectionId} key={event.selectionId}>{event.targetDate} · {event.scenarioName} · {event.name}</option>)}</select></label>
        </div>
        {invalidDates ? <p className="alert alert--danger" role="alert">The start date must be earlier than the end date.</p> : null}
        <fieldset className="predictions-fieldset"><legend className="form-label form-label--required">Reality cutoff</legend><label className="predictions-check"><input type="radio" name="cutoff" checked={cutoffMode === "asOfStart"} onChange={() => { setCutoffMode("asOfStart"); invalidatePreflight(); }} /> As of start — excludes observations on and after the first predicted period.</label><label className="predictions-check"><input type="radio" name="cutoff" checked={cutoffMode === "allCurrentReality"} onChange={() => { setCutoffMode("allCurrentReality"); invalidatePreflight(); }} /> All current Reality — retrospective predictions can leak future knowledge. Historical values entered for the target scenario can still override same-period Reality values.</label></fieldset>
        <div className="form-actions"><button className="btn btn--secondary" type="button" disabled={submitting || invalidDates} onClick={() => void handlePreflight()}>Run preflight</button><button className="btn btn--primary" type="button" disabled={submitting || invalidDates || !preflight || !preflight.metrics.length} onClick={() => void handleCreate()}>Create immutable version</button></div>
        {formError ? <p className="alert alert--danger" role="alert">{formError}</p> : null}
        {preflight ? <PreflightResults preflight={preflight} manualPeriods={manualPeriods} onManualPeriodChange={(metricId, value) => setManualPeriods((current) => ({ ...current, [metricId]: value }))} /> : null}
      </section>
      <section className="predictions-panel" aria-labelledby="library-heading"><h2 id="library-heading">Saved versions</h2>{versions.length ? <div className="predictions-library">{versions.map((version) => <label className="predictions-version" key={version.id}><input type="checkbox" checked={selectedVersionIds.has(version.id)} onChange={() => setSelectedVersionIds((current) => toggleSet(current, version.id))} /><span><strong>{version.name}</strong><small>{new Date(version.createdTime).toLocaleString()} · {version.startDate} to {version.endDate} · {version.cutoffMode}</small><small>{version.targets.length} targets · {predictionVersionStatus(version)}</small></span></label>)}</div> : <div className="empty-state" role="status"><p>No saved prediction versions yet.</p></div>}</section>
    </div>
    <section className="predictions-panel predictions-plots" aria-labelledby="plots-heading"><h2 id="plots-heading">Compare saved results</h2><div className="predictions-filters"><FilterGroup title="Versions" items={versions.map((version) => [version.id, version.name])} selected={selectedVersionIds} onToggle={(id) => setSelectedVersionIds((current) => toggleSet(current, id))} /><ScenarioMultiSelect items={comparisonScenarios} selected={selectedScenarioFilter} onChange={setSelectedScenarioFilter} /><FilterGroup title="Models and baselines" items={allModelKinds.map((kind) => [kind, formatModelKind(kind)])} selected={selectedModelKinds} onToggle={(id) => setSelectedModelKinds((current) => toggleSet(current, id))} /><NumericMetricFilter items={allMetrics.map(([id, metric]) => [id, `${metric.name} (${metric.unit ?? "no unit"})`])} selected={selectedMetricIds} onChange={setSelectedMetricIds} /><div><span className="form-label">Plot date range</span><div className="predictions-plot-dates"><label className="predictions-date-field">Start date<input aria-label="Plot start date" className="input" type="date" value={plotStartDate} onChange={(event) => setPlotStartDate(event.target.value)} /></label><label className="predictions-date-field">End date<input aria-label="Plot end date" className="input" type="date" value={plotEndDate} onChange={(event) => setPlotEndDate(event.target.value)} /></label></div><label className="predictions-check"><input type="checkbox" checked={includeReality} onChange={(event) => { setIncludeReality(event.target.checked); setRealityError(""); }} /> Include current Reality (manually entered realized data)</label></div></div>{realityError ? <p className="alert alert--danger" role="alert">{realityError}</p> : null}{charts.length ? <div className="predictions-chart-grid">{charts.map((chart) => <MetricChart key={chart.metricId} metricName={chart.metricName} unit={chart.unit} lines={chart.lines} missingModelKinds={chart.missingModelKinds} />)}</div> : <div className="empty-state" role="status"><p>Select saved versions, scenarios, models and metrics with available numeric points to plot them.</p></div>}</section>
  </section>;
}

function PreflightResults(props: { preflight: PredictionPreflightDto; manualPeriods: Record<string, number>; onManualPeriodChange: (metricId: string, value: number) => void }) {
  return <section className="predictions-preflight" aria-live="polite"><h3>Preflight eligibility</h3>{props.preflight.metrics.length ? props.preflight.metrics.map((metric) => <div className="predictions-preflight__row" key={`${metric.scenarioId}:${metric.metricId}`}><strong>{metric.scenarioId} · {metric.metricId}</strong><span>{metric.status}{metric.reason ? ` — ${metric.reason}` : ""}</span>{metric.seasonalPeriod ? <span>Automatic seasonal period: {metric.seasonalPeriod} ({metric.seasonalPeriodSource})</span> : null}{metric.requiresManualSeasonalPeriod ? <label>Manual seasonal period <input aria-label={`Manual seasonal period for ${metric.metricId}`} className="input" type="number" min="2" value={props.manualPeriods[metric.metricId] ?? ""} onChange={(event) => props.onManualPeriodChange(metric.metricId, Number(event.target.value))} /></label> : null}</div>) : <p className="alert alert--info" role="status">No forecastable metrics were found for the selected scenarios and date range.</p>}</section>;
}

function FilterGroup(props: { title: string; items: Array<[string, string]>; selected: Set<string>; onToggle: (id: string) => void }) {
  return <fieldset className="predictions-fieldset"><legend className="form-label">{props.title}</legend>{props.items.map(([id, label]) => <label className="predictions-check" key={id}><input type="checkbox" checked={props.selected.has(id)} onChange={() => props.onToggle(id)} /> {label}</label>)}</fieldset>;
}

function NumericMetricFilter(props: { items: Array<[string, string]>; selected: Set<string>; onChange: (selected: Set<string>) => void }) {
  const allSelected = props.items.length > 0 && props.selected.size === props.items.length;
  return <fieldset className="predictions-fieldset"><legend className="form-label">Numeric metrics</legend><label className="predictions-check"><input type="checkbox" checked={allSelected} onChange={(event) => props.onChange(new Set(event.target.checked ? props.items.map(([id]) => id) : []))} /> All numeric metrics</label>{props.items.map(([id, label]) => <label className="predictions-check" key={id}><input type="checkbox" checked={props.selected.has(id)} onChange={() => props.onChange(toggleSet(props.selected, id))} /> {label}</label>)}</fieldset>;
}

function ScenarioMultiSelect(props: { borderless?: boolean; required?: boolean; items: Array<[string, string]>; selected: Set<string>; onChange: (selected: Set<string>) => void }) {
  const dropdownRef = useRef<HTMLDetailsElement>(null);
  const allSelected = props.items.length > 0 && props.selected.size === props.items.length;
  const summary = allSelected
    ? "All active scenarios"
    : props.selected.size
      ? `${props.selected.size} scenario${props.selected.size === 1 ? "" : "s"} selected`
      : "No scenarios selected";

  useEffect(() => {
    function closeWhenClickedOutside(event: PointerEvent) {
      if (!dropdownRef.current?.contains(event.target as Node)) {
        dropdownRef.current?.removeAttribute("open");
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape" || !dropdownRef.current?.open) return;
      dropdownRef.current.open = false;
      dropdownRef.current.querySelector("summary")?.focus();
    }

    document.addEventListener("pointerdown", closeWhenClickedOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeWhenClickedOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  return <fieldset className={`predictions-fieldset${props.borderless ? " predictions-fieldset--borderless" : ""}`}><legend className={`form-label${props.required ? " form-label--required" : ""}`}>Target scenarios</legend><details ref={dropdownRef} className="predictions-multi-dropdown"><summary>{summary}</summary><div className="predictions-multi-dropdown__options"><label className="predictions-check"><input type="checkbox" checked={allSelected} onChange={(event) => props.onChange(new Set(event.target.checked ? props.items.map(([id]) => id) : []))} /> All active prediction scenarios</label>{props.items.map(([id, label]) => <label className="predictions-check" key={id}><input type="checkbox" checked={props.selected.has(id)} onChange={() => props.onChange(toggleSet(props.selected, id))} /> {label}</label>)}</div></details></fieldset>;
}

function formatSeriesList(items: string[]): string {
  if (items.length < 2) return items[0] ?? "";
  if (items.length === 2) return items.join(" and ");
  return `${items.slice(0, -1).join(", ")}, and ${items.at(-1)}`;
}

function MetricChart(props: { metricName: string; unit: string; lines: PredictionChartLine[]; missingModelKinds: string[] }) {
  const points = props.lines.flatMap((line) => line.points.map((point) => ({ ...point, line })));
  const dates = [...new Set(points.map((point) => point.date))].sort();
  const axisTicks = predictionChartAxisTicks(dates);
  const values = points.map((point) => point.value);
  const min = values.length ? Math.min(...values) : 0; const max = values.length ? Math.max(...values) : 1; const span = max - min || 1;
  const width = 720; const height = 260; const padding = { top: 18, right: 18, bottom: 34, left: 56 };
  const x = (date: string) => padding.left + (dates.length < 2 ? (width - padding.left - padding.right) / 2 : (dates.indexOf(date) / (dates.length - 1)) * (width - padding.left - padding.right));
  const y = (value: number) => height - padding.bottom - ((value - min) / span) * (height - padding.top - padding.bottom);
  return <article className="prediction-chart"><header><h3>{props.metricName}</h3><span>{props.unit}</span></header><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${props.metricName} prediction comparison chart in ${props.unit}`}><line className="prediction-chart__axis" x1={padding.left} x2={padding.left} y1={padding.top} y2={height - padding.bottom} /><line className="prediction-chart__axis" x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} /><text x="4" y={padding.top + 4}>{max.toPrecision(5)}</text><text x="4" y={height - padding.bottom}>{min.toPrecision(5)}</text>{axisTicks.filter((tick) => tick.isYearBoundary).map((tick) => <line className="prediction-chart__year-boundary" key={`year-boundary:${tick.date}`} x1={x(tick.date)} x2={x(tick.date)} y1={padding.top} y2={height - padding.bottom} />)}{axisTicks.filter((tick) => tick.isFirst || tick.isYearBoundary).map((tick) => <text className="prediction-chart__year" key={`year:${tick.date}`} x={x(tick.date)} y={height - 4} textAnchor="middle">{tick.year}</text>)}{props.lines.map((line, index) => { const path = line.points.map((point, pointIndex) => `${pointIndex ? "L" : "M"}${x(point.date)} ${y(point.value)}`).join(" "); return <g key={line.id}><path className={line.kind === "reality" ? "prediction-chart__line prediction-chart__line--reality" : "prediction-chart__line"} stroke={line.kind === "reality" ? "#166534" : lineColors[index % lineColors.length]} strokeDasharray={line.strokeDasharray} d={path}><title>{line.provenance}</title></path>{line.points.map((point) => <circle key={`${line.id}:${point.date}`} cx={x(point.date)} cy={y(point.value)} r="3" fill={line.kind === "reality" ? "#166534" : lineColors[index % lineColors.length]}><title>{`${line.label}: ${point.date}, ${point.value} ${props.unit}`}</title></circle>)}</g>; })}{axisTicks.map((tick) => <text className="prediction-chart__date" key={tick.date} x={x(tick.date)} y={height - 18} textAnchor="middle">{tick.label}</text>)}</svg>{props.missingModelKinds.length ? <p className="prediction-chart__no-results" role="status">No results to show for: {formatSeriesList(props.missingModelKinds.map(formatModelKind))}.</p> : null}<ul className="prediction-chart__legend">{props.lines.map((line, index) => <li key={line.id}><span className={line.kind === "reality" ? "prediction-chart__swatch prediction-chart__swatch--reality" : "prediction-chart__swatch"} style={line.kind === "reality" ? undefined : { backgroundColor: lineColors[index % lineColors.length] }} /> <strong>{line.label}</strong><small>{line.provenance}</small></li>)}</ul></article>;
}
