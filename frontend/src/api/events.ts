export type EventDto = {
  id: string;
  name: string;
  targetDate: string;
  eventDetails: string;
};

export type EventCreateRequest = {
  name: string;
  targetDate: string;
  eventDetails: string;
};

export type EventUpdateRequest = EventCreateRequest;

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

function pickArray(payload: unknown, keys: string[]): unknown[] {
  if (Array.isArray(payload)) return payload;

  const item = asRecord(payload);
  for (const key of keys) {
    const value = item[key];
    if (Array.isArray(value)) return value;
  }

  return [];
}

function normalizeEvent(payload: unknown, index = 0): EventDto {
  const item = asRecord(payload);
  const candidates = nestedRecords(item, [
    "event",
    "eventSummary",
    "event_summary",
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
    "eventId",
    "event_id",
    "eventKey",
    "event_key"
  ]);
  const targetDate = pickString(candidates, [
    "targetDate",
    "target_date",
    "date",
    "effectiveDate",
    "effective_date"
  ]);
  const name = pickString(
    candidates,
    [
      "name",
      "eventName",
      "event_name",
      "title",
      "label",
      "displayName",
      "display_name"
    ],
    id || targetDate || `Event ${index + 1}`
  );

  return {
    id: id || name,
    name,
    targetDate,
    eventDetails: pickString(candidates, [
      "eventDetails",
      "event_details",
      "details",
      "description",
      "desc",
      "summaryText",
      "summary_text"
    ])
  };
}

function normalizeEvents(payload: unknown): EventDto[] {
  return pickArray(payload, ["events", "items", "data"]).map((item, index) =>
    normalizeEvent(item, index)
  );
}

function eventsPath(orgId: string, scenarioId: string) {
  return `/api/v1/organisations/${encodeURIComponent(orgId)}/scenarios/${encodeURIComponent(
    scenarioId
  )}/events`;
}

function eventPath(orgId: string, scenarioId: string, eventId: string) {
  return `${eventsPath(orgId, scenarioId)}/${encodeURIComponent(eventId)}`;
}

export async function fetchEvents(
  orgId: string,
  scenarioId: string,
  signal?: AbortSignal
): Promise<EventDto[]> {
  return normalizeEvents(
    await requestJson<unknown>(
      eventsPath(orgId, scenarioId),
      { method: "GET" },
      signal
    )
  );
}

export async function fetchEvent(
  orgId: string,
  scenarioId: string,
  eventId: string,
  signal?: AbortSignal
): Promise<EventDto> {
  return normalizeEvent(
    await requestJson<unknown>(
      eventPath(orgId, scenarioId, eventId),
      { method: "GET" },
      signal
    )
  );
}

export async function createEvent(
  orgId: string,
  scenarioId: string,
  payload: EventCreateRequest,
  signal?: AbortSignal
): Promise<EventDto> {
  return normalizeEvent(
    await requestJson<unknown>(
      eventsPath(orgId, scenarioId),
      {
        method: "POST",
        body: JSON.stringify(payload)
      },
      signal
    )
  );
}

export async function updateEvent(
  orgId: string,
  scenarioId: string,
  eventId: string,
  payload: EventUpdateRequest,
  signal?: AbortSignal
): Promise<EventDto> {
  return normalizeEvent(
    await requestJson<unknown>(
      eventPath(orgId, scenarioId, eventId),
      {
        method: "PATCH",
        body: JSON.stringify(payload)
      },
      signal
    )
  );
}

export async function deleteEvent(
  orgId: string,
  scenarioId: string,
  eventId: string,
  signal?: AbortSignal
): Promise<void> {
  return requestJson<void>(
    eventPath(orgId, scenarioId, eventId),
    { method: "DELETE" },
    signal
  );
}
