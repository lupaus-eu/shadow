import { authenticatedFetch } from "./client";

export type OrganisationDto = {
  id: string;
  name: string;
};

export type OrganisationCreateRequest = {
  name: string;
};

export type OrganisationPatchRequest = {
  name: string;
};

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
  const res = await authenticatedFetch("/api/v1/organisations", {
    method: "GET",
    headers: {
      Accept: "application/json"
    }
  }, signal);

  if (!res.ok) {
    throw new Error(await responseErrorMessage(res, "fetch organisations"));
  }

  return (await res.json()) as OrganisationDto[];
}

export async function createOrganisation(
  payload: OrganisationCreateRequest,
  signal?: AbortSignal
): Promise<OrganisationDto> {
  const res = await authenticatedFetch("/api/v1/organisations", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  }, signal);

  if (!res.ok) {
    throw new Error(await responseErrorMessage(res, "create organisation"));
  }

  return (await res.json()) as OrganisationDto;
}

export async function updateOrganisation(
  organisationId: string,
  payload: OrganisationPatchRequest,
  signal?: AbortSignal
): Promise<OrganisationDto> {
  const res = await authenticatedFetch(
    `/api/v1/organisations/${encodeURIComponent(organisationId)}`,
    {
      method: "PATCH",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    },
    signal
  );

  if (!res.ok) {
    throw new Error(await responseErrorMessage(res, "update organisation"));
  }

  return (await res.json()) as OrganisationDto;
}

export async function deleteOrganisation(
  organisationId: string,
  signal?: AbortSignal
): Promise<void> {
  const res = await authenticatedFetch(
    `/api/v1/organisations/${encodeURIComponent(organisationId)}`,
    {
      method: "DELETE",
      headers: {
        Accept: "application/json"
      }
    },
    signal
  );

  if (!res.ok) {
    throw new Error(await responseErrorMessage(res, "delete organisation"));
  }
}
