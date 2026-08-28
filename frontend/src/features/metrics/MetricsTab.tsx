import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState
} from "react";
import type { ChangeEvent, FormEvent } from "react";
import EmptyTab from "../../components/EmptyTab";
import {
  createDerivedMetric,
  fetchTimeseries,
  updateDerivedMetric,
  updateTimeserieValues
} from "../../api/timeseries";
import type {
  DerivedMetricCreateRequest,
  TimeserieCellValue,
  TimeserieDto,
  TimeserieTimeUnit,
  TimeserieValueDto,
  TimeserieValueUnit
} from "../../api/timeseries";
import { useWorkspaceSelection } from "../../workspace/WorkspaceSelectionContext";

type DraftState = Record<string, Record<string, string>>;
type SavingRowsState = Record<string, boolean>;
type ParsedDateParts = {
  year: number;
  month: number;
  day: number;
  date: Date;
};

const METRICS_SORT_OPTIONS = [
  { value: "name-asc", label: "Timeserie name, asc.", field: "name", direction: 1 },
  { value: "name-desc", label: "Timeserie name, desc.", field: "name", direction: -1 },
  { value: "id-asc", label: "Col name, asc.", field: "id", direction: 1 },
  { value: "id-desc", label: "Col name, desc.", field: "id", direction: -1 },
  {
    value: "description-asc",
    label: "Description, asc.",
    field: "description",
    direction: 1
  },
  {
    value: "description-desc",
    label: "Description, desc.",
    field: "description",
    direction: -1
  },
  { value: "unit-asc", label: "Unit, asc.", field: "unit", direction: 1 },
  { value: "unit-desc", label: "Unit, desc.", field: "unit", direction: -1 },
  {
    value: "time-unit-asc",
    label: "Time unit, asc.",
    field: "timeUnit",
    direction: 1
  },
  {
    value: "time-unit-desc",
    label: "Time unit, desc.",
    field: "timeUnit",
    direction: -1
  },
  {
    value: "value-unit-asc",
    label: "Value unit, asc.",
    field: "valueUnit",
    direction: 1
  },
  {
    value: "value-unit-desc",
    label: "Value unit, desc.",
    field: "valueUnit",
    direction: -1
  }
] as const;

type MetricsSortValue = "" | (typeof METRICS_SORT_OPTIONS)[number]["value"];

const TIME_UNIT_SORT_ORDER: Record<TimeserieTimeUnit, number> = {
  day: 0,
  week: 1,
  month: 2,
  year: 3
};

function sortTimeseries(items: TimeserieDto[]): TimeserieDto[] {
  return [...items].sort((a, b) => a.id.localeCompare(b.id));
}

function sortTimeseriesForDisplay(
  items: TimeserieDto[],
  sortValue: MetricsSortValue
): TimeserieDto[] {
  const option = METRICS_SORT_OPTIONS.find((item) => item.value === sortValue);
  if (!option) return items;

  return [...items].sort((a, b) => {
    const comparison =
      option.field === "timeUnit"
        ? TIME_UNIT_SORT_ORDER[a.timeUnit] - TIME_UNIT_SORT_ORDER[b.timeUnit]
        : a[option.field].localeCompare(b[option.field], undefined, {
            numeric: true,
            sensitivity: "base"
          });
    return comparison * option.direction;
  });
}

function metricsCountText(count: number): string {
  return `${count} timeserie(s)`;
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function loadErrorMessage(error: unknown): string {
  return `Could not load metrics. ${messageFromError(error)}`;
}

function saveErrorMessage(error: unknown): string {
  return `Could not save metrics. ${messageFromError(error)}`;
}

function formatDateValue(date: Date): string {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function todayDateValue(): string {
  const today = new Date();
  return formatDateValue(
    new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()))
  );
}

function parseDateParts(value: string): ParsedDateParts | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }

  return { year, month, day, date };
}

function isValidDateValue(value: string): boolean {
  return parseDateParts(value) !== null;
}

function isValidStartDateForTimeUnit(
  value: string,
  timeUnit: TimeserieTimeUnit
): boolean {
  const parts = parseDateParts(value);
  if (!parts) return false;

  if (timeUnit === "day") return true;
  if (timeUnit === "week") return parts.date.getUTCDay() === 1;
  if (timeUnit === "month") return parts.day === 1;
  return parts.month === 1 && parts.day === 1;
}

function normaliseDateToUnitStart(
  value: string,
  timeUnit: TimeserieTimeUnit
): string {
  const parts = parseDateParts(value);
  if (!parts) return value;
  const date = new Date(parts.date);

  if (timeUnit === "week") {
    const day = date.getUTCDay();
    const diff = day === 0 ? -6 : 1 - day;
    date.setUTCDate(date.getUTCDate() + diff);
  } else if (timeUnit === "month") {
    date.setUTCDate(1);
  } else if (timeUnit === "year") {
    date.setUTCMonth(0, 1);
  }

  return formatDateValue(date);
}

function addTimeUnit(value: string, timeUnit: TimeserieTimeUnit): string {
  const parts = parseDateParts(value);
  if (!parts) return value;
  const date = new Date(parts.date);

  if (timeUnit === "day") {
    date.setUTCDate(date.getUTCDate() + 1);
  } else if (timeUnit === "week") {
    date.setUTCDate(date.getUTCDate() + 7);
  } else if (timeUnit === "month") {
    date.setUTCMonth(date.getUTCMonth() + 1);
  } else {
    date.setUTCFullYear(date.getUTCFullYear() + 1);
  }

  return formatDateValue(date);
}

function nextValidDateForRow(
  timeserie: TimeserieDto,
  columns: string[]
): string {
  const validDates = columns.filter((date) =>
    isValidStartDateForTimeUnit(date, timeserie.timeUnit)
  );
  if (validDates.length === 0) {
    return normaliseDateToUnitStart(todayDateValue(), timeserie.timeUnit);
  }

  return addTimeUnit(validDates[validDates.length - 1], timeserie.timeUnit);
}

function formatCellValue(value: TimeserieCellValue): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function baselineValueForDate(timeserie: TimeserieDto, date: string): string {
  const value = timeserie.values.find((item) => item.date === date);
  return value ? formatCellValue(value.value) : "";
}

function draftValueForDate(
  timeserie: TimeserieDto,
  date: string,
  draftValues: DraftState
): string {
  if (Object.hasOwn(draftValues[timeserie.id] ?? {}, date)) {
    return draftValues[timeserie.id][date];
  }

  return baselineValueForDate(timeserie, date);
}

function buildInitialDrafts(items: TimeserieDto[]): DraftState {
  return Object.fromEntries(
    items.map((timeserie) => [
      timeserie.id,
      Object.fromEntries(
        timeserie.values.map((value) => [
          value.date,
          formatCellValue(value.value)
        ])
      )
    ])
  );
}

function draftForUpdatedTimeserie(timeserie: TimeserieDto): Record<string, string> {
  return Object.fromEntries(
    timeserie.values.map((value) => [value.date, formatCellValue(value.value)])
  );
}

function buildDateColumns(items: TimeserieDto[], manualDates: string[]): string[] {
  const dates = new Set<string>(manualDates);
  for (const timeserie of items) {
    for (const value of timeserie.values) {
      dates.add(value.date);
    }
  }

  return [...dates].filter(isValidDateValue).sort();
}

function parseDraftCellValue(
  valueUnit: TimeserieValueUnit,
  value: string
): { kind: "blank" } | { kind: "value"; value: TimeserieCellValue } | { kind: "error" } {
  if (value.trim() === "") return { kind: "blank" };

  if (valueUnit === "number") {
    const parsed = Number(value);
    return Number.isFinite(parsed)
      ? { kind: "value", value: parsed }
      : { kind: "error" };
  }

  if (valueUnit === "boolean") {
    if (value === "true") return { kind: "value", value: true };
    if (value === "false") return { kind: "value", value: false };
    return { kind: "error" };
  }

  return { kind: "value", value };
}

function buildSavePayload(
  timeserie: TimeserieDto,
  columns: string[],
  draftValues: DraftState
): { values: TimeserieValueDto[] } | { error: string } {
  const values: TimeserieValueDto[] = [];

  for (const date of columns) {
    if (!isValidStartDateForTimeUnit(date, timeserie.timeUnit)) continue;

    const parsed = parseDraftCellValue(
      timeserie.valueUnit,
      draftValueForDate(timeserie, date, draftValues)
    );
    if (parsed.kind === "error") {
      return {
        error: `${timeserie.name} has an invalid ${timeserie.valueUnit} value for ${date}.`
      };
    }
    if (parsed.kind === "blank") continue;

    values.push({ date, value: parsed.value });
  }

  return { values };
}

function rowHasChanges(
  timeserie: TimeserieDto,
  columns: string[],
  draftValues: DraftState
): boolean {
  const dates = new Set<string>(columns);
  for (const value of timeserie.values) dates.add(value.date);

  for (const date of dates) {
    if (!isValidStartDateForTimeUnit(date, timeserie.timeUnit)) continue;
    if (
      draftValueForDate(timeserie, date, draftValues) !==
      baselineValueForDate(timeserie, date)
    ) {
      return true;
    }
  }

  return false;
}

function parseCsvImport(
  text: string,
  timeserie: TimeserieDto
): { values: Record<string, string>; dates: string[] } | { error: string } {
  const rows = text
    .split(/\r?\n/)
    .map((row) => row.trim())
    .filter(Boolean);
  const values: Record<string, string> = {};

  for (const row of rows) {
    const separator = row.includes(";") ? ";" : ",";
    const parts = row.split(separator);
    if (parts.length !== 2) {
      return { error: "CSV rows must contain date and value." };
    }

    const date = parts[0].trim();
    const rawValue = parts[1].trim();
    if (!isValidDateValue(date)) {
      return { error: `${date || "CSV date"} is not a valid date.` };
    }
    if (!isValidStartDateForTimeUnit(date, timeserie.timeUnit)) {
      return {
        error: `${date} is not valid for ${timeserie.name} ${timeserie.timeUnit} values.`
      };
    }

    const parsed = parseDraftCellValue(timeserie.valueUnit, rawValue);
    if (parsed.kind === "error") {
      return {
        error: `${timeserie.name} has an invalid ${timeserie.valueUnit} CSV value for ${date}.`
      };
    }

    values[date] =
      parsed.kind === "blank" ? "" : formatCellValue(parsed.value);
  }

  return { values, dates: Object.keys(values) };
}

export default function MetricsTab(props: { orgId: string }) {
  const { selectedScenario } = useWorkspaceSelection();
  const selectedScenarioId = selectedScenario?.id ?? null;
  const activeScenarioIdRef = useRef<string | null>(selectedScenarioId);
  useLayoutEffect(() => {
    activeScenarioIdRef.current = selectedScenarioId;
  }, [selectedScenarioId]);
  const [timeseries, setTimeseries] = useState<TimeserieDto[]>([]);
  const [draftValues, setDraftValues] = useState<DraftState>({});
  const [manualDate, setManualDate] = useState("");
  const [manualDates, setManualDates] = useState<string[]>([]);
  const [manualDateError, setManualDateError] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [savingRows, setSavingRows] = useState<SavingRowsState>({});
  const [savingAll, setSavingAll] = useState(false);
  const [sortValue, setSortValue] = useState<MetricsSortValue>("");
  const [showManualMetrics, setShowManualMetrics] = useState(true);
  const [showDerivedMetrics, setShowDerivedMetrics] = useState(true);
  const [isDerivedMetricEditorVisible, setDerivedMetricEditorVisible] =
    useState(false);
  const [editingDerivedMetric, setEditingDerivedMetric] =
    useState<TimeserieDto | null>(null);

  const dateColumns = useMemo(
    () => buildDateColumns(timeseries, manualDates),
    [manualDates, timeseries]
  );
  const displayedTimeseries = useMemo(
    () =>
      sortTimeseriesForDisplay(
        timeseries.filter(
          (timeserie) =>
            (showManualMetrics || timeserie.isDerived) &&
            (showDerivedMetrics || !timeserie.isDerived)
        ),
        sortValue
      ),
    [showDerivedMetrics, showManualMetrics, sortValue, timeseries]
  );
  const dirtyRows = useMemo(
    () =>
      timeseries.filter((timeserie) =>
        rowHasChanges(timeserie, dateColumns, draftValues)
      ),
    [dateColumns, draftValues, timeseries]
  );
  const isSaving = savingAll || Object.values(savingRows).some(Boolean);

  const loadMetrics = useCallback(
    async (signal?: AbortSignal, resetGridState = false) => {
      if (resetGridState) {
        setManualDates([]);
        setManualDate("");
        setManualDateError("");
        setActionError("");
        setActionMessage("");
        setEditingDerivedMetric(null);
        setDerivedMetricEditorVisible(false);
      }

      if (!selectedScenario) {
        setTimeseries([]);
        setDraftValues({});
        return;
      }

      try {
        setLoading(true);
        setLoadError("");
        const items = sortTimeseries(
          await fetchTimeseries(props.orgId, selectedScenario.id, signal)
        );
        setTimeseries(items);
        setDraftValues(buildInitialDrafts(items));
      } catch (error) {
        const err = error as { name?: string };
        if (err.name === "AbortError") return;
        setLoadError(loadErrorMessage(error));
        setTimeseries([]);
        setDraftValues({});
      } finally {
        setLoading(false);
      }
    },
    [props.orgId, selectedScenario]
  );

  useEffect(() => {
    const ac = new AbortController();

    async function loadInitialMetrics() {
      await loadMetrics(ac.signal, true);
    }

    void loadInitialMetrics();

    return () => ac.abort();
  }, [loadMetrics]);

  function updateDraftValue(timeserieId: string, date: string, value: string) {
    setDraftValues((current) => ({
      ...current,
      [timeserieId]: {
        ...(current[timeserieId] ?? {}),
        [date]: value
      }
    }));
    setActionError("");
    setActionMessage("");
  }

  function addDateColumn(date: string): boolean {
    if (!isValidDateValue(date)) {
      setManualDateError("Enter a valid date.");
      return false;
    }

    setManualDates((current) =>
      current.includes(date) ? current : [...current, date].sort()
    );
    setManualDateError("");
    return true;
  }

  function onAddManualDate() {
    if (addDateColumn(manualDate)) {
      setManualDate("");
    }
  }

  function onAddNextDate(timeserie: TimeserieDto) {
    const nextDate = nextValidDateForRow(timeserie, dateColumns);
    addDateColumn(nextDate);
  }

  async function saveRow(timeserie: TimeserieDto) {
    if (isSaving) return;

    const payload = buildSavePayload(timeserie, dateColumns, draftValues);
    if ("error" in payload) {
      setActionError(payload.error);
      return;
    }

    try {
      setSavingRows((current) => ({ ...current, [timeserie.id]: true }));
      setActionError("");
      setActionMessage("");
      const updated = await updateTimeserieValues(
        props.orgId,
        selectedScenario?.id ?? "",
        timeserie.id,
        payload
      );
      setTimeseries((current) =>
        sortTimeseries(
          current.map((item) => (item.id === updated.id ? updated : item))
        )
      );
      setDraftValues((current) => ({
        ...current,
        [updated.id]: draftForUpdatedTimeserie(updated)
      }));
      if (timeseries.some((item) => item.isDerived)) {
        await loadMetrics();
      }
      setActionMessage(`Saved ${updated.name}.`);
    } catch (error) {
      setActionError(saveErrorMessage(error));
    } finally {
      setSavingRows((current) => ({ ...current, [timeserie.id]: false }));
    }
  }

  async function saveAllChanges() {
    if (isSaving) return;

    const updates = dirtyRows.map((timeserie) => ({
      timeserie,
      payload: buildSavePayload(timeserie, dateColumns, draftValues)
    }));
    const invalid = updates.find((update) => "error" in update.payload);
    if (invalid && "error" in invalid.payload) {
      setActionError(invalid.payload.error);
      return;
    }

    try {
      setSavingAll(true);
      setActionError("");
      setActionMessage("");
      const results = await Promise.allSettled(
        updates.map((update) =>
          updateTimeserieValues(
            props.orgId,
            selectedScenario?.id ?? "",
            update.timeserie.id,
            update.payload as { values: TimeserieValueDto[] }
          )
        )
      );
      const updatedRows = results.flatMap((result) =>
        result.status === "fulfilled" ? [result.value] : []
      );
      const failedResults = results.filter(
        (result): result is PromiseRejectedResult => result.status === "rejected"
      );
      const updatedById = new Map(
        updatedRows.map((timeserie) => [timeserie.id, timeserie])
      );
      setTimeseries((current) =>
        sortTimeseries(
          current.map((item) => updatedById.get(item.id) ?? item)
        )
      );
      setDraftValues((current) => ({
        ...current,
        ...Object.fromEntries(
          updatedRows.map((timeserie) => [
            timeserie.id,
            draftForUpdatedTimeserie(timeserie)
          ])
        )
      }));
      if (updatedRows.length > 0 && timeseries.some((item) => item.isDerived)) {
        await loadMetrics();
      }

      if (failedResults.length > 0) {
        const savedSummary =
          updatedRows.length > 0 ? ` Saved ${updatedRows.length} row(s).` : "";
        setActionError(
          `Could not save ${failedResults.length} of ${updates.length} row(s).${savedSummary} ${messageFromError(failedResults[0].reason)}`
        );
        return;
      }

      setActionMessage(`Saved ${updatedRows.length} row(s).`);
    } catch (error) {
      setActionError(saveErrorMessage(error));
    } finally {
      setSavingAll(false);
    }
  }

  async function importCsv(timeserie: TimeserieDto, file: File) {
    const sourceScenarioId = selectedScenarioId;
    let text: string;
    try {
      text = await file.text();
    } catch {
      if (activeScenarioIdRef.current !== sourceScenarioId) return;
      setActionError(`Could not read CSV file ${file.name}.`);
      return;
    }

    if (activeScenarioIdRef.current !== sourceScenarioId) return;

    const parsed = parseCsvImport(text, timeserie);
    if ("error" in parsed) {
      setActionError(parsed.error);
      return;
    }

    setManualDates((current) =>
      [...new Set([...current, ...parsed.dates])].sort()
    );
    setDraftValues((current) => ({
      ...current,
      [timeserie.id]: {
        ...(current[timeserie.id] ?? {}),
        ...parsed.values
      }
    }));
    setActionError("");
    setActionMessage(`Imported ${parsed.dates.length} value(s) for ${timeserie.name}.`);
  }

  async function saveDerivedMetric(
    payload: DerivedMetricCreateRequest,
    current: TimeserieDto | null
  ) {
    if (isSaving) return;
    try {
      setSavingAll(true);
      setActionError("");
      const updated = current
        ? await updateDerivedMetric(
            props.orgId,
            selectedScenario?.id ?? "",
            current.id,
            payload
          )
        : await createDerivedMetric(
            props.orgId,
            selectedScenario?.id ?? "",
            payload
          );
      setTimeseries((items) =>
        sortTimeseries(
          current
            ? items.map((item) => (item.id === updated.id ? updated : item))
            : [...items, updated]
        )
      );
      setDraftValues((items) => ({
        ...items,
        [updated.id]: draftForUpdatedTimeserie(updated)
      }));
      setEditingDerivedMetric(null);
      setDerivedMetricEditorVisible(false);
      setActionMessage(`${current ? "Updated" : "Created"} ${updated.name}.`);
    } catch (error) {
      setActionError(messageFromError(error));
    } finally {
      setSavingAll(false);
    }
  }

  if (!selectedScenario) {
    return (
      <EmptyTab
        title="Metrics"
        description="Select a scenario in Scenarios to activate this tab."
      />
    );
  }

  const saveAllDisabled = loading || isSaving || dirtyRows.length === 0;

  return (
    <div className="metrics-tab">
      <section className="scenarios-toolbar" aria-label="Metrics overview">
        <div className="scenarios-toolbar__title">
          <h1 className="page-title">Metrics</h1>
          <span className="scenarios-toolbar__count">
            {metricsCountText(timeseries.length)}
          </span>
        </div>
      </section>

      <div className="metrics-notices">
        {manualDateError ? (
          <ActionError
            message={manualDateError}
            onClose={() => setManualDateError("")}
          />
        ) : null}
        {loadError ? (
          <ActionError
            title="Metrics API error"
            message={loadError}
            onClose={() => setLoadError("")}
          />
        ) : null}
        {actionError ? (
          <ActionError
            message={actionError}
            onClose={() => setActionError("")}
          />
        ) : null}
        {actionMessage ? (
          <MetricsNotice
            variant="info"
            role="status"
            title="Metrics saved"
            message={actionMessage}
            onClose={() => setActionMessage("")}
          />
        ) : null}
      </div>

      {isDerivedMetricEditorVisible ? (
        <DerivedMetricEditor
          key={editingDerivedMetric?.id ?? "new"}
          editing={editingDerivedMetric}
          disabled={isSaving}
          normalMetrics={timeseries.filter(
            (item) => !item.isDerived && item.valueUnit === "number" && item.shortName
          )}
          onSave={saveDerivedMetric}
          onCancel={() => {
            setEditingDerivedMetric(null);
            setDerivedMetricEditorVisible(false);
          }}
        />
      ) : (
        <button
          className="btn btn--secondary metrics-create-derived-button"
          type="button"
          onClick={() => setDerivedMetricEditorVisible(true)}
        >
          Create derived metric
        </button>
      )}

      <div className="metrics-toolbar__actions">
        <div className="metrics-toolbar__visibility-toggles">
          <label className="metrics-toolbar__derived-toggle">
            <input
              type="checkbox"
              checked={showManualMetrics}
              onChange={(event) => setShowManualMetrics(event.target.checked)}
            />
            Show manual metrics timeseries
          </label>
          <label className="metrics-toolbar__derived-toggle">
            <input
              type="checkbox"
              checked={showDerivedMetrics}
              onChange={(event) => setShowDerivedMetrics(event.target.checked)}
            />
            Show derived metrics timeseries
          </label>
        </div>
        <select
          className="select metrics-toolbar__sort-select"
          aria-label="Sort metrics"
          value={sortValue}
          disabled={isSaving}
          onChange={(event) =>
            setSortValue(event.target.value as MetricsSortValue)
          }
        >
          <option value="">Sort by:</option>
          {METRICS_SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <div className="metrics-toolbar__date-actions">
          <input
            className="input metrics-toolbar__date-input"
            type="date"
            aria-label="Date column"
            value={manualDate}
            disabled={isSaving}
            onChange={(event) => setManualDate(event.target.value)}
          />
          <button
            className="btn btn--secondary"
            type="button"
            onClick={onAddManualDate}
            disabled={!manualDate || isSaving}
          >
            Add date
          </button>
        </div>
        <div className="metrics-toolbar__save-actions">
          <button
            className="btn btn--primary"
            type="button"
            onClick={() => void saveAllChanges()}
            disabled={saveAllDisabled}
            aria-busy={savingAll}
          >
            {savingAll ? <SavingLabel /> : "Save changes"}
          </button>
          <button
            className="btn btn--secondary"
            type="button"
            onClick={() => void loadMetrics()}
            disabled={loading || isSaving}
          >
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      {loading ? <p className="muted metrics-loading">Loading metrics...</p> : null}

      {!loading && !loadError && timeseries.length === 0 ? (
        <section className="empty-state" aria-labelledby="metrics-empty-title">
          <p className="eyebrow">Metrics</p>
          <h2 id="metrics-empty-title" className="section-title">
            No metrics available.
          </h2>
          <p className="muted">No timeseries exist in {selectedScenario.name}.</p>
        </section>
      ) : null}

      {!loading && !loadError && timeseries.length > 0 ? (
        <MetricsGrid
          timeseries={displayedTimeseries}
          dateColumns={dateColumns}
          draftValues={draftValues}
          dirtyRows={new Set(dirtyRows.map((timeserie) => timeserie.id))}
          savingRows={savingRows}
          isSaving={isSaving}
          onDraftChange={updateDraftValue}
          onSaveRow={saveRow}
          onAddNextDate={onAddNextDate}
          onImportCsv={importCsv}
          onEditDerived={(timeserie) => {
            setEditingDerivedMetric(timeserie);
            setDerivedMetricEditorVisible(true);
          }}
        />
      ) : null}
    </div>
  );
}

function DerivedMetricEditor(props: {
  editing: TimeserieDto | null;
  disabled: boolean;
  normalMetrics: TimeserieDto[];
  onSave: (
    payload: DerivedMetricCreateRequest,
    current: TimeserieDto | null
  ) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(props.editing?.name ?? "");
  const [unit, setUnit] = useState(props.editing?.unit ?? "");
  const [formula, setFormula] = useState(props.editing?.derivedFormula ?? "");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await props.onSave(
      { name: name.trim(), unit: unit.trim() || null, formula: formula.trim() },
      props.editing
    );
  }

  return (
    <section className="detail-card derived-metric-editor" aria-labelledby="derived-metric-title">
      <div className="detail-card__header">
        <h2 id="derived-metric-title" className="section-title">
          {props.editing ? "Edit derived metric" : "Create derived metric"}
        </h2>
      </div>
      <form onSubmit={(event) => void submit(event)}>
        <div className="form-row">
          <label className="form-label form-label--required" htmlFor="derived-metric-name">
            Name
          </label>
          <input id="derived-metric-name" className="input derived-metric-editor__name" value={name} disabled={props.disabled}
            onChange={(event) => setName(event.target.value)} />
        </div>
        <div className="form-row">
          <label className="form-label" htmlFor="derived-metric-unit">Unit</label>
          <input id="derived-metric-unit" className="input derived-metric-editor__unit" value={unit} disabled={props.disabled}
            onChange={(event) => setUnit(event.target.value)} />
        </div>
        <div className="form-row">
          <label className="form-label form-label--required" htmlFor="derived-metric-formula">
            Formula
          </label>
          <input id="derived-metric-formula" className="input" value={formula} disabled={props.disabled}
            onChange={(event) => setFormula(event.target.value)} />
          <small className="muted">Use +, -, *, /, ** or ^ and normal metric short names.</small>
        </div>
        {props.normalMetrics.length > 0 ? (
          <p className="muted">
            Available short names: {props.normalMetrics.map((item) => item.shortName).join(", ")}
          </p>
        ) : null}
        <div className="form-actions">
          <button className="btn btn--primary" type="submit" disabled={props.disabled || !name.trim() || !formula.trim()}>
            {props.editing ? "Save derived metric" : "Create derived metric"}
          </button>
          <button className="btn btn--secondary" type="button" disabled={props.disabled} onClick={props.onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}

function MetricsGrid(props: {
  timeseries: TimeserieDto[];
  dateColumns: string[];
  draftValues: DraftState;
  dirtyRows: Set<string>;
  savingRows: SavingRowsState;
  isSaving: boolean;
  onDraftChange: (timeserieId: string, date: string, value: string) => void;
  onSaveRow: (timeserie: TimeserieDto) => Promise<void>;
  onAddNextDate: (timeserie: TimeserieDto) => void;
  onImportCsv: (timeserie: TimeserieDto, file: File) => Promise<void>;
  onEditDerived: (timeserie: TimeserieDto) => void;
}) {
  const csvFileInputs = useRef<Record<string, HTMLInputElement | null>>({});

  function onCsvFileChange(timeserie: TimeserieDto, file: File | undefined) {
    if (!file) return;
    void props.onImportCsv(timeserie, file);
  }

  return (
    <div className="metrics-grid-shell" aria-label="Metrics grid">
      <table className="metrics-grid">
        <thead>
          <tr>
            <th scope="col" className="metrics-grid__metric-column">
              Timeserie
            </th>
            <th scope="col" className="metrics-grid__actions-column">
              Actions
            </th>
            {props.dateColumns.map((date) => (
              <th key={date} scope="col" className="metrics-grid__date-column">
                <time dateTime={date}>{date}</time>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.timeseries.map((timeserie) => {
            const rowIsDirty = props.dirtyRows.has(timeserie.id);
            const rowSaving = Boolean(props.savingRows[timeserie.id]);
            const isDerived = timeserie.isDerived === true;

            return (
              <tr
                key={timeserie.id}
                className={[
                  rowIsDirty ? "metrics-grid__row--dirty" : "",
                  isDerived ? "metrics-grid__row--derived" : ""
                ].filter(Boolean).join(" ") || undefined}
              >
                <th scope="row" className="metrics-grid__metric-cell">
                  <div className="metrics-grid__metric">
                    <span className="metrics-grid__metric-heading">
                      <strong>{timeserie.name}</strong>
                      {rowIsDirty ? (
                        <span className="badge badge--accent">Changed</span>
                      ) : null}
                    </span>
                    {!isDerived ? <code>{timeserie.id}</code> : null}
                    {timeserie.shortName ? (
                      <span className="metrics-grid__short-name">
                        Short name: <code>{timeserie.shortName}</code>
                      </span>
                    ) : null}
                    <span className="muted">
                      {timeserie.timeUnit} / {timeserie.valueUnit}
                      {timeserie.unit ? ` / ${timeserie.unit}` : ""}
                    </span>
                    {timeserie.description ? (
                      <span className="metrics-grid__description">
                        {timeserie.description}
                      </span>
                    ) : null}
                    {timeserie.derivedFormula ? (
                      <code>{timeserie.derivedFormula}</code>
                    ) : null}
                  </div>
                </th>
                <td className="metrics-grid__actions-cell">
                  <div className="metrics-row-actions">
                    {isDerived ? (
                      <button
                        className="btn btn--secondary btn--compact"
                        type="button"
                        onClick={() => props.onEditDerived(timeserie)}
                        disabled={props.isSaving}
                      >
                        Edit derived metric
                      </button>
                    ) : null}
                    {!isDerived ? (
                      <>
                        <button
                          className="btn btn--secondary btn--compact"
                          type="button"
                          onClick={() => void props.onSaveRow(timeserie)}
                          disabled={!rowIsDirty || props.isSaving}
                          aria-busy={rowSaving}
                        >
                          {rowSaving ? <SavingLabel /> : "Save row"}
                        </button>
                        <button
                          className="btn btn--secondary btn--compact"
                          type="button"
                          onClick={() => props.onAddNextDate(timeserie)}
                          disabled={props.isSaving}
                        >
                          Add next date
                        </button>
                        <input
                          ref={(element) => {
                            csvFileInputs.current[timeserie.id] = element;
                          }}
                          className="visually-hidden"
                          type="file"
                          accept=".csv,text/csv"
                          aria-label={`CSV file for ${timeserie.name}`}
                          disabled={props.isSaving}
                          onChange={(event: ChangeEvent<HTMLInputElement>) => {
                            const file = event.target.files?.[0];
                            event.target.value = "";
                            onCsvFileChange(timeserie, file);
                          }}
                        />
                        <button
                          className="btn btn--secondary btn--compact"
                          type="button"
                          onClick={() => csvFileInputs.current[timeserie.id]?.click()}
                          disabled={props.isSaving}
                        >
                          Import CSV
                        </button>
                      </>
                    ) : null}
                  </div>
                </td>
                {props.dateColumns.map((date) => (
                  <td key={`${timeserie.id}:${date}`} className="metrics-grid__cell">
                    <CellEditor
                      timeserie={timeserie}
                      date={date}
                      value={draftValueForDate(
                        timeserie,
                        date,
                        props.draftValues
                      )}
                      onChange={(value) =>
                        props.onDraftChange(timeserie.id, date, value)
                      }
                      disabled={isDerived || props.isSaving}
                    />
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CellEditor(props: {
  timeserie: TimeserieDto;
  date: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  const label = `${props.timeserie.name} ${props.date}`;
  const isEditable = isValidStartDateForTimeUnit(
    props.date,
    props.timeserie.timeUnit
  );

  if (!isEditable) {
    return (
      <span
        className="metrics-grid__readonly"
        aria-label={`${label} read-only`}
        title={`${props.date} is not valid for ${props.timeserie.timeUnit} values`}
      >
        Read only
      </span>
    );
  }

  if (props.timeserie.valueUnit === "boolean") {
    return (
      <select
        className="select metrics-grid__cell-control"
        aria-label={label}
        value={props.value}
        onChange={(event) => props.onChange(event.target.value)}
        disabled={props.disabled}
      >
        <option value=""></option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    );
  }

  return (
    <input
      className="input metrics-grid__cell-control"
      type={props.timeserie.valueUnit === "number" ? "number" : "text"}
      step={props.timeserie.valueUnit === "number" ? "any" : undefined}
      inputMode={props.timeserie.valueUnit === "number" ? "decimal" : undefined}
      aria-label={label}
      value={props.value}
      onChange={(event) => props.onChange(event.target.value)}
      disabled={props.disabled}
    />
  );
}

function SavingLabel() {
  return (
    <span className="metrics-saving-label">
      <span className="metrics-saving-spinner" aria-hidden="true" />
      <span>Saving...</span>
    </span>
  );
}

function MetricsNotice(props: {
  variant: "danger" | "info";
  role: "alert" | "status";
  title: string;
  message: string;
  onClose: () => void;
}) {
  const dismissLabel = `Dismiss ${props.title} notice`;

  return (
    <div className={`alert alert--${props.variant} metrics-notice`} role={props.role}>
      <button
        className="metrics-notice__dismiss"
        type="button"
        aria-label={dismissLabel}
        onClick={props.onClose}
      >
        <span aria-hidden="true">×</span>
      </button>
      <p className="alert__title">{props.title}</p>
      <p className="alert__text">{props.message}</p>
    </div>
  );
}

function ActionError(props: {
  title?: string;
  message: string;
  onClose: () => void;
}) {
  if (!props.message) return null;
  return (
    <MetricsNotice
      variant="danger"
      role="alert"
      title={props.title ?? "Action error"}
      message={props.message}
      onClose={props.onClose}
    />
  );
}
