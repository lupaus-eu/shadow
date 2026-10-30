import { authenticatedFetch } from "./client";

// ADR-015: `clientName` is a label the OAuth client declared itself; the UI
// always shows it isolated and labelled as self-declared.
export type ConsentRequestDto = {
  clientName: string;
  clientNameSelfDeclared: true;
  redirectIsLoopback: boolean;
  redirectHost: string;
  scope: string;
  resource: string;
  expiresTime: string;
};

export type ConsentDecisionDto = {
  redirectUrl: string;
};

export type AiConnectionDto = {
  grantKey: string;
  clientId: string;
  clientName: string;
  scope: string;
  resource: string;
  createdTime: string;
  lastUsedTime: string | null;
  expiresTime: string;
};

export type UserAiConnectionsRevokeDto = {
  revokedCount: number;
};

export type AiChangeSetStatus =
  "draft" | "submitted" | "applied" | "rejected" | "failed" | "discarded";

// TASK-069K review API. `scenarioKey` is the derived scenario reference: null
// when the change set creates or copies a scenario or touches several.
export type AiChangeSetListItemDto = {
  id: string;
  scenarioKey: string | null;
  title: string;
  rationale: string | null;
  status: AiChangeSetStatus;
  operationCount: number;
  clientId: string;
  clientName: string;
  createdBy: number;
  createdByName: string;
  createdTime: string;
  modifiedTime: string;
  reviewedBy: number | null;
  reviewedByName: string | null;
  reviewedTime: string | null;
  reviewNote: string | null;
  // ADR-015 amendment: `web` for the Metrics tab, `mcp` for an approved MCP
  // client call, which also names the reviewing client.
  reviewedVia: "web" | "mcp" | null;
  reviewClientId: string | null;
  reviewClientName: string | null;
};

export type AiOperationErrorDto = {
  code: string;
  message: string;
  statusCode?: number | null;
};

export type AiOperationResultDto = {
  position: number;
  opType: string;
  status: "ok" | "error" | "not_run";
  scenarioKey?: string | null;
  key?: string | null;
  error?: AiOperationErrorDto | null;
};

export type AiExecutionResultDto = {
  ok: boolean;
  operations: AiOperationResultDto[];
  refs: Record<string, string>;
};

export type AiApplyOutcomeDto = {
  status: "applied" | "failed";
  step?: string | null;
  error?: AiOperationErrorDto | null;
  operations: AiOperationResultDto[];
  refs: Record<string, string>;
};

export type AiNodeReplacementDto = {
  kind: "node";
  scenarioKey: string;
  orgStateKey: string;
  nodeKey: string;
  missing: boolean;
  message?: string | null;
  fields?: Record<string, unknown> | null;
  checksum?: string | null;
};

export type AiTimeserieReplacementDto = {
  kind: "timeserie";
  scenarioKey: string;
  timeserieKey: string;
  missing: boolean;
  message?: string | null;
  valueCount?: number | null;
  firstDate?: string | null;
  lastDate?: string | null;
  checksum?: string | null;
};

export type AiFrozenValuesDto = {
  generatorVersion: number;
  valueCount: number;
  firstDate: string | null;
  lastDate: string | null;
  values: Array<{ date: string; value: number }> | null;
};

export type AiChangeSetOperationDto = {
  position: number;
  type: string;
  ref: string | null;
  // The stored operation JSON as it was staged: snake_case addressing fields
  // around a camelCase `payload` (or `spec` for generated values).
  operation: Record<string, unknown>;
  error: AiOperationErrorDto | null;
  frozenValues: AiFrozenValuesDto | null;
  replacesExisting: boolean;
  replaces: AiNodeReplacementDto | AiTimeserieReplacementDto | null;
};

export type AiChangeSetDetailDto = AiChangeSetListItemDto & {
  operations: AiChangeSetOperationDto[];
  reviewFingerprint: string;
  validationResult: AiExecutionResultDto | null;
  appliedResult: AiApplyOutcomeDto | null;
};

export type AiChangeSetApplyDto = {
  changeSet: AiChangeSetListItemDto;
  operations: AiOperationResultDto[];
  refs: Record<string, string>;
};

export type AiChangeSetListOptions = {
  status?: AiChangeSetStatus;
  scenarioKey?: string;
  includeUnscoped?: boolean;
  limit?: number;
};

// Carries the HTTP status and the `/api/v1` error code so pages can tell
// expired, decided and unknown consent requests apart.
export class AiApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "AiApiError";
    this.status = status;
    this.code = code;
  }
}

function errorFromPayload(payload: unknown): { code: string; message: string } {
  if (!payload || typeof payload !== "object") return { code: "", message: "" };

  const error = (payload as { error?: unknown }).error;
  if (error && typeof error === "object") {
    const code = (error as { code?: unknown }).code;
    const message = (error as { message?: unknown }).message;
    return {
      code: typeof code === "string" ? code : "",
      message: typeof message === "string" ? message : ""
    };
  }

  const detail = (payload as { detail?: unknown }).detail;
  return { code: "", message: typeof detail === "string" ? detail : "" };
}

async function responseError(response: Response, action: string): Promise<AiApiError> {
  const text = await response.text().catch(() => "");
  let parsed = { code: "", message: "" };

  if (text) {
    try {
      parsed = errorFromPayload(JSON.parse(text));
    } catch {
      parsed = { code: "", message: "" };
    }
  }

  const message = parsed.message
    ? `Failed to ${action} (${response.status}): ${parsed.message}`
    : `Failed to ${action} (${response.status}).`;
  return new AiApiError(response.status, parsed.code, message);
}

async function requestJson<T>(
  path: string,
  action: string,
  init: RequestInit,
  signal?: AbortSignal
): Promise<T> {
  const response = await authenticatedFetch(
    path,
    {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers
      }
    },
    signal
  );

  if (!response.ok) {
    throw await responseError(response, action);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// The pending request id travels only in the `request` query parameter and in
// JSON bodies, never in a URL path (ADR-015 "Pending Request Id Handling").
export async function fetchConsentRequest(
  requestId: string,
  signal?: AbortSignal
): Promise<ConsentRequestDto> {
  const parameters = new URLSearchParams({ request: requestId });
  return requestJson<ConsentRequestDto>(
    `/api/v1/ai/oauth/consent?${parameters.toString()}`,
    "load authorization request",
    { method: "GET" },
    signal
  );
}

async function decideConsentRequest(
  decision: "approve" | "deny",
  requestId: string,
  signal?: AbortSignal
): Promise<ConsentDecisionDto> {
  const result = await requestJson<ConsentDecisionDto>(
    `/api/v1/ai/oauth/consent/${decision}`,
    `${decision} authorization request`,
    { method: "POST", body: JSON.stringify({ request: requestId }) },
    signal
  );
  if (!result || typeof result.redirectUrl !== "string" || !result.redirectUrl) {
    throw new Error(`Invalid ${decision} response.`);
  }
  return result;
}

export async function approveConsentRequest(
  requestId: string,
  signal?: AbortSignal
): Promise<ConsentDecisionDto> {
  return decideConsentRequest("approve", requestId, signal);
}

export async function denyConsentRequest(
  requestId: string,
  signal?: AbortSignal
): Promise<ConsentDecisionDto> {
  return decideConsentRequest("deny", requestId, signal);
}

const connectionsPath = "/api/v1/ai/connections";

export async function fetchAiConnections(signal?: AbortSignal): Promise<AiConnectionDto[]> {
  return requestJson<AiConnectionDto[]>(
    connectionsPath,
    "fetch AI connections",
    { method: "GET" },
    signal
  );
}

export async function revokeAiConnection(grantKey: string, signal?: AbortSignal): Promise<void> {
  return requestJson<void>(
    `${connectionsPath}/${encodeURIComponent(grantKey)}`,
    "revoke AI connection",
    { method: "DELETE" },
    signal
  );
}

export async function revokeUserAiConnections(
  userId: number,
  signal?: AbortSignal
): Promise<UserAiConnectionsRevokeDto> {
  return requestJson<UserAiConnectionsRevokeDto>(
    `/api/v1/ai/users/${encodeURIComponent(String(userId))}/connections/revoke`,
    "revoke AI connections",
    { method: "POST" },
    signal
  );
}

function changeSetsPath(orgId: string): string {
  return `/api/v1/organisations/${encodeURIComponent(orgId)}/ai/change-sets`;
}

function changeSetPath(orgId: string, changeSetKey: string): string {
  return `${changeSetsPath(orgId)}/${encodeURIComponent(changeSetKey)}`;
}

export async function fetchAiChangeSets(
  orgId: string,
  options: AiChangeSetListOptions = {},
  signal?: AbortSignal
): Promise<AiChangeSetListItemDto[]> {
  const parameters = new URLSearchParams();
  if (options.status) parameters.set("status", options.status);
  if (options.scenarioKey) parameters.set("scenarioKey", options.scenarioKey);
  if (options.includeUnscoped) parameters.set("includeUnscoped", "true");
  if (options.limit !== undefined) parameters.set("limit", String(options.limit));
  const query = parameters.toString();
  return requestJson<AiChangeSetListItemDto[]>(
    query ? `${changeSetsPath(orgId)}?${query}` : changeSetsPath(orgId),
    "fetch AI change sets",
    { method: "GET" },
    signal
  );
}

export async function fetchAiChangeSet(
  orgId: string,
  changeSetKey: string,
  signal?: AbortSignal
): Promise<AiChangeSetDetailDto> {
  return requestJson<AiChangeSetDetailDto>(
    changeSetPath(orgId, changeSetKey),
    "fetch AI change set",
    { method: "GET" },
    signal
  );
}

// Apply sends back the `reviewFingerprint` of the detail the reviewer saw; the
// server answers `409 review_stale` when the replaced data changed since.
export async function applyAiChangeSet(
  orgId: string,
  changeSetKey: string,
  reviewFingerprint: string,
  signal?: AbortSignal
): Promise<AiChangeSetApplyDto> {
  return requestJson<AiChangeSetApplyDto>(
    `${changeSetPath(orgId, changeSetKey)}/apply`,
    "apply AI change set",
    { method: "POST", body: JSON.stringify({ reviewFingerprint }) },
    signal
  );
}

export async function rejectAiChangeSet(
  orgId: string,
  changeSetKey: string,
  note: string | null,
  signal?: AbortSignal
): Promise<AiChangeSetListItemDto> {
  return requestJson<AiChangeSetListItemDto>(
    `${changeSetPath(orgId, changeSetKey)}/reject`,
    "reject AI change set",
    { method: "POST", body: JSON.stringify({ note }) },
    signal
  );
}
