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
