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
    const text = await res.text().catch(() => "");
    throw new Error(`Failed to fetch organisations (${res.status}). ${text}`);
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
    const text = await res.text().catch(() => "");
    throw new Error(`Failed to create organisation (${res.status}). ${text}`);
  }

  return (await res.json()) as OrganisationDto;
}
