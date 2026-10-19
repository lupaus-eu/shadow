import { authenticatedFetch } from "./client";

export type PredictionCutoffMode = "asOfStart" | "allCurrentScenario";

// ADR-014's supported result kinds in their canonical display order.
export const MODEL_KINDS = [
  "naive",
  "seasonal_naive",
  "average",
  "mlforecast",
  "sarima",
  "prophet"
] as const;

// ADR-014: only these result kinds use the seasonal period.
export const SEASONAL_PERIOD_MODEL_KINDS: readonly string[] = ["seasonal_naive", "sarima"];

export function selectionUsesSeasonalPeriod(modelKinds: Iterable<string>): boolean {
  return [...modelKinds].some((kind) => SEASONAL_PERIOD_MODEL_KINDS.includes(kind));
}

export type PredictionRequest = {
  targetScenarioIds: string[];
  startDate: string;
  endDate: string;
  cutoffMode: PredictionCutoffMode;
  confidenceLevel: number;
  manualSeasonalPeriods: Record<string, number>;
  modelKinds: string[];
};

export type PredictionCreateRequest = PredictionRequest & { name: string };

export type PredictionRequestState =
  "queued" | "running" | "cancelling" | "completed" | "cancelled" | "failed";

export type PredictionRequestSummaryDto = {
  id: string;
  name: string;
  state: PredictionRequestState;
  submittedTime: string;
  startTime: string | null;
  finishTime: string | null;
  failureCode: string | null;
  failureReason: string | null;
  completedPredictionId: string | null;
};

export type PredictionPreflightMetricDto = {
  scenarioId: string;
  metricId: string;
  status: string;
  reason: string | null;
  seasonalPeriod: number | null;
  seasonalPeriodSource: string | null;
  requiresManualSeasonalPeriod: boolean;
};

export type PredictionPreflightDto = {
  metrics: PredictionPreflightMetricDto[];
};

export type PredictionVersionDto = {
  id: string;
  name: string;
  startDate: string;
  endDate: string;
  cutoffMode: PredictionCutoffMode;
  confidenceLevel: number;
  createdTime: string;
};

export type PredictionPointDto = {
  date: string;
  value: number;
  lowerBound: number | null;
  upperBound: number | null;
};

export type PredictionModelResultDto = {
  kind: string;
  status: string;
  reason: string | null;
  predictionIntervalStatus: "available" | "unavailable" | "not_applicable";
  predictionIntervalReason: string | null;
  crossValidationStatus: string;
  crossValidationMae: number | null;
  configuration: Record<string, unknown>;
  points: PredictionPointDto[];
};

export type PredictionTargetDto = {
  scenarioId: string;
  metricId: string;
  metricName: string;
  timeUnit: string;
  unit: string | null;
  status: string;
  reason: string | null;
  seasonalPeriod: number | null;
  seasonalPeriodSource: string | null;
  sourceSnapshot: Record<string, unknown>;
  inputSnapshot: Record<string, unknown>;
  results: PredictionModelResultDto[];
};

export type PredictionVersionDetailDto = PredictionVersionDto & {
  modelConfiguration: Record<string, unknown>;
  targets: PredictionTargetDto[];
};

export class PredictionsApiError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(detail || `Prediction request failed (${status}).`);
    this.name = "PredictionsApiError";
    this.status = status;
  }
}

function predictionsPath(orgId: string) {
  return `/api/v1/organisations/${encodeURIComponent(orgId)}/predictions`;
}

function predictionRequestsPath(orgId: string) {
  return `/api/v1/organisations/${encodeURIComponent(orgId)}/prediction-requests`;
}

// Shows only FastAPI's safe detail text, never echoed validation input.
function errorDetail(text: string): string {
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    return text;
  }
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item as { msg?: unknown } | null)?.msg)
      .filter((message): message is string => typeof message === "string")
      .join(" ");
  }
  // Authentication and CSRF errors use the application's error envelope.
  const message = (payload as { error?: { message?: unknown } | null } | null)?.error?.message;
  return typeof message === "string" ? message : text;
}

async function requestJson<T>(path: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
  const response = await authenticatedFetch(
    path,
    {
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init
    },
    signal
  );
  if (!response.ok) {
    throw new PredictionsApiError(
      response.status,
      errorDetail(await response.text().catch(() => ""))
    );
  }
  return (await response.json()) as T;
}

export function preflightPredictions(
  orgId: string,
  payload: PredictionRequest,
  signal?: AbortSignal
): Promise<PredictionPreflightDto> {
  return requestJson(
    `${predictionsPath(orgId)}/preflight`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    signal
  );
}

export function createPrediction(
  orgId: string,
  payload: PredictionCreateRequest,
  signal?: AbortSignal
): Promise<PredictionRequestSummaryDto> {
  return requestJson(
    predictionsPath(orgId),
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    signal
  );
}

export function fetchPredictionRequests(
  orgId: string,
  signal?: AbortSignal
): Promise<PredictionRequestSummaryDto[]> {
  return requestJson(predictionRequestsPath(orgId), { method: "GET" }, signal);
}

export function fetchPredictionRequest(
  orgId: string,
  requestId: string,
  signal?: AbortSignal
): Promise<PredictionRequestSummaryDto> {
  return requestJson(
    `${predictionRequestsPath(orgId)}/${encodeURIComponent(requestId)}`,
    { method: "GET" },
    signal
  );
}

export function cancelPredictionRequest(
  orgId: string,
  requestId: string,
  signal?: AbortSignal
): Promise<PredictionRequestSummaryDto> {
  return requestJson(
    `${predictionRequestsPath(orgId)}/${encodeURIComponent(requestId)}/cancel`,
    { method: "POST" },
    signal
  );
}

export function fetchPredictions(
  orgId: string,
  signal?: AbortSignal
): Promise<PredictionVersionDto[]> {
  return requestJson(predictionsPath(orgId), { method: "GET" }, signal);
}

export function fetchPrediction(
  orgId: string,
  predictionId: string,
  signal?: AbortSignal
): Promise<PredictionVersionDetailDto> {
  return requestJson(
    `${predictionsPath(orgId)}/${encodeURIComponent(predictionId)}`,
    { method: "GET" },
    signal
  );
}
