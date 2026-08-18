import { authenticatedFetch } from "./client";

export type ScenarioDto = {
  id: string;
  name: string;
  description: string;
  protected: boolean;
};

export type ScenarioUpdateRequest = {
  name: string;
  description: string;
};

export type ScenarioCopyRequest = {
  sourceScenarioId: string;
  sourceOrgStateId: string;
  name?: string;
  description: string;
};

export type OrgStateDto = {
  id: string;
  name: string;
  description: string;
  targetDate: string;
};

export type OrgStateCreateRequest = {
  name: string;
  description: string;
  targetDate: string;
};

export type OrgStateUpdateRequest = OrgStateCreateRequest;

export type CleanOrgStatesResponse = {
  cleaned: number;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail ? `API request failed (${status}). ${detail}` : `API request failed (${status}).`);
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

function nestedRecords(
  item: Record<string, unknown>,
  keys: string[]
): Record<string, unknown>[] {
  const records: Record<string, unknown>[] = [item];

  for (const key of keys) {
    const value = item[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      records.push(value as Record<string, unknown>);
    }
  }

  return records;
}

function pickString(
  items: Record<string, unknown>[],
  keys: string[],
  fallback = ""
): string {
  for (const item of items) {
    for (const key of keys) {
      const value = item[key];
      if (typeof value === "string") return value;
      if (typeof value === "number") return String(value);
    }
  }
  return fallback;
}

function pickBoolean(items: Record<string, unknown>[], keys: string[]): boolean {
  for (const item of items) {
    for (const key of keys) {
      const value = item[key];
      if (typeof value === "boolean") return value;
      if (typeof value === "string") {
        const normalized = value.trim().toLowerCase();
        if (normalized === "true") return true;
        if (normalized === "false") return false;
      }
    }
  }
  return false;
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

function normalizeScenario(payload: unknown, index = 0): ScenarioDto {
  const item = asRecord(payload);
  const candidates = nestedRecords(item, [
    "scenario",
    "scenarioSummary",
    "scenario_summary",
    "metadata",
    "summary",
    "data",
    "value"
  ]);
  const id = pickString(candidates, [
    "id",
    "_id",
    "uuid",
    "key",
    "slug",
    "scenarioId",
    "scenario_id",
    "scenarioUuid",
    "scenario_uuid"
  ]);
  const name = pickString(
    candidates,
    [
      "name",
      "scenarioName",
      "scenario_name",
      "title",
      "label",
      "displayName",
      "display_name"
    ],
    id || `Scenario ${index + 1}`
  );
  const description = pickString(candidates, [
    "description",
    "desc",
    "details",
    "scenarioDescription",
    "scenario_description",
    "summaryText",
    "summary_text"
  ]);
  const realityKey = (id || name).trim().toLowerCase();

  return {
    id: id || name,
    name,
    description,
    protected:
      realityKey === "reality" ||
      pickBoolean(candidates, [
        "protected",
        "isProtected",
        "is_protected",
        "protectedScenario",
        "protected_scenario",
        "readOnly",
        "read_only",
        "readonly",
        "locked"
      ])
  };
}

function normalizeScenarios(payload: unknown): ScenarioDto[] {
  return pickArray(payload, ["scenarios", "items", "data"]).map(
    (item, index) => normalizeScenario(item, index)
  );
}

function normalizeOrgState(payload: unknown, index = 0): OrgStateDto {
  const item = asRecord(payload);
  const candidates = nestedRecords(item, [
    "orgState",
    "org_state",
    "state",
    "stateSummary",
    "state_summary",
    "metadata",
    "summary",
    "data",
    "value"
  ]);

  const id = pickString(candidates, [
      "id",
      "_id",
      "uuid",
      "key",
      "slug",
      "orgStateId",
      "org_state_id",
      "stateId",
      "state_id"
    ]);
  const targetDate = pickString(candidates, [
      "targetDate",
      "target_date",
      "date",
      "effectiveDate",
      "effective_date",
      "asOfDate",
      "as_of_date"
    ]);
  const name = pickString(
    candidates,
    [
      "name",
      "orgStateName",
      "org_state_name",
      "stateName",
      "state_name",
      "title",
      "label",
      "displayName",
      "display_name"
    ],
    id || targetDate || `Org state ${index + 1}`
  );

  return {
    id: id || name,
    name,
    description: pickString(candidates, [
      "description",
      "desc",
      "details",
      "orgStateDescription",
      "org_state_description",
      "stateDescription",
      "state_description",
      "summaryText",
      "summary_text"
    ]),
    targetDate
  };
}

function normalizeOrgStates(payload: unknown): OrgStateDto[] {
  return pickArray(payload, ["orgStates", "org_states", "items", "data"]).map(
    (item, index) => normalizeOrgState(item, index)
  );
}

function normalizeCleanOrgStatesResponse(payload: unknown): CleanOrgStatesResponse {
  const item = asRecord(payload);
  const cleaned = item.cleaned;

  return {
    cleaned: typeof cleaned === "number" && Number.isFinite(cleaned) ? cleaned : 0
  };
}

function orgPath(orgId: string) {
  return `/api/v1/organisations/${encodeURIComponent(orgId)}/scenarios`;
}

function scenarioPath(orgId: string, scenarioId: string) {
  return `${orgPath(orgId)}/${encodeURIComponent(scenarioId)}`;
}

function orgStatesPath(orgId: string, scenarioId: string) {
  return `${scenarioPath(orgId, scenarioId)}/org-states`;
}

function orgStatePath(orgId: string, scenarioId: string, orgStateId: string) {
  return `${orgStatesPath(orgId, scenarioId)}/${encodeURIComponent(orgStateId)}`;
}

export async function fetchScenarios(
  orgId: string,
  signal?: AbortSignal
): Promise<ScenarioDto[]> {
  return normalizeScenarios(
    await requestJson<unknown>(orgPath(orgId), { method: "GET" }, signal)
  );
}

export async function fetchScenario(
  orgId: string,
  scenarioId: string,
  signal?: AbortSignal
): Promise<ScenarioDto> {
  return normalizeScenario(
    await requestJson<unknown>(
      scenarioPath(orgId, scenarioId),
      { method: "GET" },
      signal
    )
  );
}

export async function updateScenario(
  orgId: string,
  scenarioId: string,
  payload: ScenarioUpdateRequest,
  signal?: AbortSignal
): Promise<ScenarioDto> {
  return normalizeScenario(
    await requestJson<unknown>(
      scenarioPath(orgId, scenarioId),
      {
        method: "PATCH",
        body: JSON.stringify(payload)
      },
      signal
    )
  );
}

export async function deleteScenario(
  orgId: string,
  scenarioId: string,
  signal?: AbortSignal
): Promise<void> {
  return requestJson<void>(
    scenarioPath(orgId, scenarioId),
    { method: "DELETE" },
    signal
  );
}

export async function copyScenario(
  orgId: string,
  payload: ScenarioCopyRequest,
  signal?: AbortSignal
): Promise<ScenarioDto> {
  return normalizeScenario(
    await requestJson<unknown>(
      `${orgPath(orgId)}/copy`,
      {
        method: "POST",
        body: JSON.stringify(payload)
      },
      signal
    )
  );
}

export async function fetchOrgStates(
  orgId: string,
  scenarioId: string,
  signal?: AbortSignal
): Promise<OrgStateDto[]> {
  return normalizeOrgStates(
    await requestJson<unknown>(
      orgStatesPath(orgId, scenarioId),
      { method: "GET" },
      signal
    )
  );
}

export async function createOrgState(
  orgId: string,
  scenarioId: string,
  payload: OrgStateCreateRequest,
  signal?: AbortSignal
): Promise<OrgStateDto> {
  return normalizeOrgState(
    await requestJson<unknown>(
      orgStatesPath(orgId, scenarioId),
      {
        method: "POST",
        body: JSON.stringify(payload)
      },
      signal
    )
  );
}

export async function updateOrgState(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  payload: OrgStateUpdateRequest,
  signal?: AbortSignal
): Promise<OrgStateDto> {
  return normalizeOrgState(
    await requestJson<unknown>(
      orgStatePath(orgId, scenarioId, orgStateId),
      {
        method: "PATCH",
        body: JSON.stringify(payload)
      },
      signal
    )
  );
}

export async function deleteOrgState(
  orgId: string,
  scenarioId: string,
  orgStateId: string,
  signal?: AbortSignal
): Promise<void> {
  return requestJson<void>(
    orgStatePath(orgId, scenarioId, orgStateId),
    { method: "DELETE" },
    signal
  );
}

export async function cleanOrgStates(
  orgId: string,
  scenarioId: string,
  signal?: AbortSignal
): Promise<CleanOrgStatesResponse> {
  return normalizeCleanOrgStatesResponse(
    await requestJson<unknown>(
      `${orgStatesPath(orgId, scenarioId)}/clean`,
      { method: "POST" },
      signal
    )
  );
}
