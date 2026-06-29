export type OrganisationDto = {
  id: string;
  name: string;
};

export type OrganisationCreateRequest = {
  name: string;
};

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ?? "";

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) return path;
  return `${API_BASE_URL.replace(/\/+$/, "")}${path}`;
}

function messageFromPayload(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";

  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (!item || typeof item !== "object") return "";
        const msg = (item as { msg?: unknown }).msg;
        return typeof msg === "string" ? msg : "";
      })
      .filter(Boolean)
      .join(" ");
  }

  const error = (payload as { error?: unknown }).error;
  if (error && typeof error === "object") {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }

  return "";
}

async function responseErrorMessage(
  res: Response,
  action: string
): Promise<string> {
  const text = await res.text().catch(() => "");
  let detail = text;

  if (text) {
    try {
      detail = messageFromPayload(JSON.parse(text)) || text;
    } catch {
      detail = text;
    }
  }

  return detail
    ? `Failed to ${action} (${res.status}): ${detail}`
    : `Failed to ${action} (${res.status}).`;
}

export async function fetchOrganisations(
  signal?: AbortSignal
): Promise<OrganisationDto[]> {
  const res = await fetch(buildApiUrl("/api/v1/organisations"), {
    method: "GET",
    headers: {
      Accept: "application/json"
    },
    signal
  });

  if (!res.ok) {
    throw new Error(await responseErrorMessage(res, "fetch organisations"));
  }

  return (await res.json()) as OrganisationDto[];
}

export async function createOrganisation(
  payload: OrganisationCreateRequest,
  signal?: AbortSignal
): Promise<OrganisationDto> {
  const res = await fetch(buildApiUrl("/api/v1/organisations"), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload),
    signal
  });

  if (!res.ok) {
    throw new Error(await responseErrorMessage(res, "create organisation"));
  }

  return (await res.json()) as OrganisationDto;
}
