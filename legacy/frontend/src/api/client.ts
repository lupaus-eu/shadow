const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ?? "";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

type RequestAuthentication = {
  getCsrfToken: () => string | null;
  onUnauthorized: () => void;
};

let requestAuthentication: RequestAuthentication | null = null;

export function buildApiUrl(path: string): string {
  if (!API_BASE_URL) return path;
  return `${API_BASE_URL.replace(/\/+$/, "")}${path}`;
}

export function configureRequestAuthentication(authentication: RequestAuthentication): () => void {
  requestAuthentication = authentication;

  return () => {
    if (requestAuthentication === authentication) {
      requestAuthentication = null;
    }
  };
}

export async function authenticatedFetch(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal
): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {};
  new Headers(init.headers).forEach((value, name) => {
    const originalName = Object.keys(init.headers ?? {}).find(
      (candidate) => candidate.toLowerCase() === name
    );
    headers[originalName ?? name] = value;
  });

  if (UNSAFE_METHODS.has(method)) {
    const csrfToken = requestAuthentication?.getCsrfToken();
    if (!csrfToken) {
      throw new Error("An authenticated session is required for this request.");
    }
    Object.keys(headers).forEach((name) => {
      if (name.toLowerCase() === "x-csrf-token") delete headers[name];
    });
    headers["X-CSRF-Token"] = csrfToken;
  }

  const response = await fetch(buildApiUrl(path), {
    ...init,
    credentials: "same-origin",
    headers,
    signal: signal ?? init.signal
  });

  if (response.status === 401) {
    requestAuthentication?.onUnauthorized();
  }

  return response;
}
