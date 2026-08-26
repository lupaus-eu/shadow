import { authenticatedFetch } from "./client";

export type PredictionCutoffMode = "asOfStart" | "allCurrentReality";

export type PredictionRequest = {
  targetScenarioIds: string[];
  startDate: string;
  endDate: string;
  cutoffMode: PredictionCutoffMode;
  manualSeasonalPeriods: Record<string, number>;
};

export type PredictionCreateRequest = PredictionRequest & { name: string };

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
  createdTime: string;
};

export type PredictionPointDto = { date: string; value: number };

export type PredictionModelResultDto = {
  kind: string;
  status: string;
  reason: string | null;
  crossValidationStatus: string;
  crossValidationMae: number | null;
  configuration: Record<string, unknown>;
  points: PredictionPointDto[];
};

export type PredictionTargetDto = {
  scenarioId: string;
  realityScenarioId: string;
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

async function requestJson<T>(
  path: string,
  init: RequestInit,
  signal?: AbortSignal
): Promise<T> {
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
      await response.text().catch(() => "")
    );
  }
  return (await response.json()) as T;
}

export function preflightPredictions(
  orgId: string,
  payload: PredictionRequest,
  signal?: AbortSignal
): Promise<PredictionPreflightDto> {
  return requestJson(`${predictionsPath(orgId)}/preflight`, {
    method: "POST",
    body: JSON.stringify(payload)
  }, signal);
}

export function createPrediction(
  orgId: string,
  payload: PredictionCreateRequest,
  signal?: AbortSignal
): Promise<PredictionVersionDetailDto> {
  return requestJson(predictionsPath(orgId), {
    method: "POST",
    body: JSON.stringify(payload)
  }, signal);
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
