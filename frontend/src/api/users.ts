export type UserRole = "consultant" | "admin";

export type UserDto = {
  id: number;
  name: string;
  role: UserRole;
};

export type UserCreateRequest = {
  name: string;
  role: UserRole;
};

export type UserUpdateRequest = UserCreateRequest;

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
        const message = (item as { msg?: unknown }).msg;
        return typeof message === "string" ? message : "";
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
  response: Response,
  action: string
): Promise<string> {
  const text = await response.text().catch(() => "");
  let detail = text;

  if (text) {
    try {
      detail = messageFromPayload(JSON.parse(text)) || text;
    } catch {
      detail = text;
    }
  }

  return detail
    ? `Failed to ${action} (${response.status}): ${detail}`
    : `Failed to ${action} (${response.status}).`;
}

async function requestJson<T>(
  path: string,
  action: string,
  init: RequestInit,
  signal?: AbortSignal
): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers
    },
    signal
  });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, action));
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const usersPath = "/api/v1/users";

function userPath(userId: number): string {
  return `${usersPath}/${encodeURIComponent(String(userId))}`;
}

export async function fetchUsers(signal?: AbortSignal): Promise<UserDto[]> {
  return requestJson<UserDto[]>(
    usersPath,
    "fetch users",
    { method: "GET" },
    signal
  );
}

export async function createUser(
  payload: UserCreateRequest,
  signal?: AbortSignal
): Promise<UserDto> {
  return requestJson<UserDto>(
    usersPath,
    "create user",
    { method: "POST", body: JSON.stringify(payload) },
    signal
  );
}

export async function updateUser(
  userId: number,
  payload: UserUpdateRequest,
  signal?: AbortSignal
): Promise<UserDto> {
  return requestJson<UserDto>(
    userPath(userId),
    "update user",
    { method: "PATCH", body: JSON.stringify(payload) },
    signal
  );
}

export async function deleteUser(
  userId: number,
  signal?: AbortSignal
): Promise<void> {
  return requestJson<void>(
    userPath(userId),
    "delete user",
    { method: "DELETE" },
    signal
  );
}
