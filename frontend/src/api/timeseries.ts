export type TimeserieTimeUnit = "day" | "week" | "month" | "year";
export type TimeserieValueUnit = "number" | "string" | "boolean";

export type TimeserieDto = {
  id: string;
  name: string;
  description: string;
  unit: string;
  timeUnit: TimeserieTimeUnit;
  valueUnit: TimeserieValueUnit;
};

export type TimeserieCreateRequest = {
  id: string;
  name: string;
  description?: string | null;
  unit?: string | null;
  timeUnit: TimeserieTimeUnit;
  valueUnit: TimeserieValueUnit;
};

export type TimeserieExistsDto = {
  id: string;
  exists: boolean;
};

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

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ?? "";

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) return path;
  return `${API_BASE_URL.replace(/\/+$/, "")}${path}`;
}

async function requestJson<T>(
  path: string,
  init?: RequestInit,
  signal?: AbortSignal
): Promise<T> {
  const res = await fetch(buildApiUrl(path), {
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...init?.headers
    },
    ...init,
    signal
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

function timeseriesPath(orgId: string, scenarioId: string) {
  return `/api/v1/organisations/${encodeURIComponent(orgId)}/scenarios/${encodeURIComponent(
    scenarioId
  )}/timeseries`;
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
  return requestJson<TimeserieDto>(
    timeseriesPath(orgId, scenarioId),
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    signal
  );
}

export async function fetchTimeserie(
  orgId: string,
  scenarioId: string,
  timeserieId: string,
  signal?: AbortSignal
): Promise<TimeserieDto> {
  return requestJson<TimeserieDto>(
    timeseriePath(orgId, scenarioId, timeserieId),
    { method: "GET" },
    signal
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
