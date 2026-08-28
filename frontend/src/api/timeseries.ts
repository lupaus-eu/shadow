import { authenticatedFetch } from "./client";

export type TimeserieTimeUnit = "day" | "week" | "month" | "year";
export type TimeserieValueUnit = "number" | "string" | "boolean";
export type TimeserieCellValue = number | string | boolean;

export type TimeserieValueDto = {
  date: string;
  value: TimeserieCellValue;
};

export type TimeserieDto = {
  id: string;
  name: string;
  shortName?: string;
  description: string;
  unit: string;
  timeUnit: TimeserieTimeUnit;
  valueUnit: TimeserieValueUnit;
  values: TimeserieValueDto[];
  isDerived?: boolean;
  derivedFormula?: string | null;
  shortNameEditable?: boolean;
};

export type TimeserieCreateRequest = {
  id: string;
  name: string;
  shortName?: string | null;
  description?: string | null;
  unit?: string | null;
  timeUnit: TimeserieTimeUnit;
  valueUnit: TimeserieValueUnit;
};

export type TimeserieExistsDto = {
  id: string;
  exists: boolean;
  shortName: string;
  shortNameEditable?: boolean;
};

export type TimeserieValuesUpdateRequest = {
  values: TimeserieValueDto[];
};

export type DerivedMetricCreateRequest = {
  name: string;
  unit: string | null;
  formula: string;
};

export type DerivedMetricUpdateRequest = Partial<DerivedMetricCreateRequest>;

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(
      detail ? `API request failed (${status}). ${detail}` : `API request failed (${status}).`
    );
    this.name = "ApiError";
    this.status = status;
  }
}

async function requestJson<T>(
  path: string,
  init?: RequestInit,
  signal?: AbortSignal
): Promise<T> {
  const res = await authenticatedFetch(path, {
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...init?.headers
    },
    ...init
  }, signal);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function pickString(
  item: Record<string, unknown>,
  keys: string[],
  fallback = ""
): string {
  for (const key of keys) {
    const value = item[key];
    if (typeof value === "string") return value;
    if (typeof value === "number") return String(value);
  }
  return fallback;
}

function pickArray(payload: unknown, keys: string[]): unknown[] {
  if (Array.isArray(payload)) return payload;

  const item = asRecord(payload);
  for (const key of keys) {
    const value = item[key];
    if (Array.isArray(value)) return value;
  }

  return [];
}

function normalizeTimeUnit(value: string): TimeserieTimeUnit {
  if (value === "day" || value === "week" || value === "month" || value === "year") {
    return value;
  }
  return "month";
}

function normalizeValueUnit(value: string): TimeserieValueUnit {
  if (value === "number" || value === "string" || value === "boolean") {
    return value;
  }
  return "number";
}

function normalizeCellValue(value: unknown): TimeserieCellValue {
  if (typeof value === "boolean" || typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return "";
}

function normalizeTimeserieValue(payload: unknown): TimeserieValueDto {
  const item = asRecord(payload);
  return {
    date: pickString(item, ["date", "targetDate", "target_date"]),
    value: normalizeCellValue(item.value)
  };
}

function normalizeTimeserie(payload: unknown, index = 0): TimeserieDto {
  const item = asRecord(payload);
  const id = pickString(item, [
    "id",
    "key",
    "timeserieId",
    "timeserie_id",
    "timeserieKey",
    "timeserie_key"
  ]);
  const name = pickString(
    item,
    ["name", "timeserieName", "timeserie_name", "title", "label"],
    id || `Timeserie ${index + 1}`
  );

  return {
    id: id || name,
    name,
    shortName: pickString(item, ["shortName", "short_name"]),
    description: pickString(item, ["description", "details", "desc"]),
    unit: pickString(item, ["unit", "valueLabel", "value_label"]),
    timeUnit: normalizeTimeUnit(pickString(item, ["timeUnit", "time_unit"])),
    valueUnit: normalizeValueUnit(pickString(item, ["valueUnit", "value_unit"])),
    values: pickArray(item.values, ["values", "items", "data"]).map(
      normalizeTimeserieValue
    ),
    isDerived: item.isDerived === true || item.is_derived === true,
    derivedFormula:
      typeof item.derivedFormula === "string"
        ? item.derivedFormula
        : typeof item.derived_formula === "string"
          ? item.derived_formula
          : null,
    shortNameEditable:
      item.shortNameEditable !== false && item.short_name_editable !== false
  };
}

function normalizeTimeseries(payload: unknown): TimeserieDto[] {
  return pickArray(payload, ["timeseries", "items", "data"]).map((item, index) =>
    normalizeTimeserie(item, index)
  );
}

function scenarioPath(orgId: string, scenarioId: string) {
  return `/api/v1/organisations/${encodeURIComponent(orgId)}/scenarios/${encodeURIComponent(
    scenarioId
  )}`;
}

function timeseriesPath(orgId: string, scenarioId: string) {
  return `${scenarioPath(orgId, scenarioId)}/timeseries`;
}

function timeseriePath(orgId: string, scenarioId: string, timeserieId: string) {
  return `${timeseriesPath(orgId, scenarioId)}/${encodeURIComponent(timeserieId)}`;
}

export async function createTimeserie(
  orgId: string,
  scenarioId: string,
  payload: TimeserieCreateRequest,
  signal?: AbortSignal
): Promise<TimeserieDto> {
  return normalizeTimeserie(
    await requestJson<unknown>(
      timeseriesPath(orgId, scenarioId),
      {
        method: "POST",
        body: JSON.stringify(payload)
      },
      signal
    )
  );
}

export async function fetchTimeseries(
  orgId: string,
  scenarioId: string,
  signal?: AbortSignal
): Promise<TimeserieDto[]> {
  return normalizeTimeseries(
    await requestJson<unknown>(
      timeseriesPath(orgId, scenarioId),
      { method: "GET" },
      signal
    )
  );
}

export async function fetchTimeserie(
  orgId: string,
  scenarioId: string,
  timeserieId: string,
  signal?: AbortSignal
): Promise<TimeserieDto> {
  return normalizeTimeserie(
    await requestJson<unknown>(
      timeseriePath(orgId, scenarioId, timeserieId),
      { method: "GET" },
      signal
    )
  );
}

export async function fetchTimeserieExists(
  orgId: string,
  scenarioId: string,
  timeserieId: string,
  signal?: AbortSignal
): Promise<TimeserieExistsDto> {
  return requestJson<TimeserieExistsDto>(
    `${timeseriePath(orgId, scenarioId, timeserieId)}/exists`,
    { method: "GET" },
    signal
  );
}

export async function deleteTimeserie(
  orgId: string,
  scenarioId: string,
  timeserieId: string,
  signal?: AbortSignal
): Promise<void> {
  return requestJson<void>(
    timeseriePath(orgId, scenarioId, timeserieId),
    { method: "DELETE" },
    signal
  );
}

export async function updateTimeserieValues(
  orgId: string,
  scenarioId: string,
  timeserieId: string,
  payload: TimeserieValuesUpdateRequest,
  signal?: AbortSignal
): Promise<TimeserieDto> {
  return normalizeTimeserie(
    await requestJson<unknown>(
      `${timeseriePath(orgId, scenarioId, timeserieId)}/values`,
      {
        method: "PATCH",
        body: JSON.stringify(payload)
      },
      signal
    )
  );
}

export async function updateTimeserieShortName(
  orgId: string,
  scenarioId: string,
  timeserieId: string,
  shortName: string | null,
  signal?: AbortSignal
): Promise<TimeserieDto> {
  return normalizeTimeserie(
    await requestJson<unknown>(
      `${timeseriePath(orgId, scenarioId, timeserieId)}/short-name`,
      { method: "PATCH", body: JSON.stringify({ shortName }) },
      signal
    )
  );
}

export async function createDerivedMetric(
  orgId: string,
  scenarioId: string,
  payload: DerivedMetricCreateRequest,
  signal?: AbortSignal
): Promise<TimeserieDto> {
  return normalizeTimeserie(
    await requestJson<unknown>(
      `${scenarioPath(orgId, scenarioId)}/derived-metrics`,
      { method: "POST", body: JSON.stringify(payload) },
      signal
    )
  );
}

export async function updateDerivedMetric(
  orgId: string,
  scenarioId: string,
  timeserieId: string,
  payload: DerivedMetricUpdateRequest,
  signal?: AbortSignal
): Promise<TimeserieDto> {
  return normalizeTimeserie(
    await requestJson<unknown>(
      `${scenarioPath(orgId, scenarioId)}/derived-metrics/${encodeURIComponent(timeserieId)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
      signal
    )
  );
}
