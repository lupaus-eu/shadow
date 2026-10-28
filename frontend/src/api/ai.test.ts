import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AiApiError,
  approveConsentRequest,
  denyConsentRequest,
  fetchAiConnections,
  fetchConsentRequest,
  revokeAiConnection,
  revokeUserAiConnections
} from "./ai";

function jsonResponse(payload: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init
  });
}

const requestId = "pending-Id_with+chars/=";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AI API", () => {
  it("loads a consent request with the id only in the request query parameter", async () => {
    const consent = {
      clientName: "Claude",
      clientNameSelfDeclared: true,
      redirectIsLoopback: false,
      redirectHost: "claude.ai",
      scope: "schatten.read",
      resource: "https://app.localhost/api/mcp/read",
      expiresTime: "2026-10-28T10:10:00Z"
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(consent));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await expect(fetchConsentRequest(requestId, controller.signal)).resolves.toEqual(consent);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/ai/oauth/consent?request=pending-Id_with%2Bchars%2F%3D",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(new URL(url, "https://app.localhost").pathname).toBe("/api/v1/ai/oauth/consent");
  });

  it("approves and denies with the id in the CSRF-protected JSON body", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ redirectUrl: "https://claude.ai/cb?code=c&iss=i" }))
      .mockResolvedValueOnce(
        jsonResponse({ redirectUrl: "https://claude.ai/cb?error=access_denied&iss=i" })
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(approveConsentRequest(requestId)).resolves.toEqual({
      redirectUrl: "https://claude.ai/cb?code=c&iss=i"
    });
    await expect(denyConsentRequest(requestId)).resolves.toEqual({
      redirectUrl: "https://claude.ai/cb?error=access_denied&iss=i"
    });

    for (const [index, decision] of ["approve", "deny"].entries()) {
      expect(fetchMock.mock.calls[index]).toEqual([
        `/api/v1/ai/oauth/consent/${decision}`,
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ request: requestId }),
          headers: expect.objectContaining({
            "Content-Type": "application/json",
            "X-CSRF-Token": "test-csrf-token"
          })
        })
      ]);
    }
  });

  it("rejects a decision response without a redirect URL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({})));

    await expect(approveConsentRequest(requestId)).rejects.toThrow("Invalid approve response.");
  });

  it("keeps the HTTP status and error code of consent failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "AUTHORIZATION_REQUEST_EXPIRED",
              message: "Authorization request expired"
            }
          },
          { status: 410 }
        )
      )
    );

    const error = await fetchConsentRequest(requestId).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(AiApiError);
    expect(error).toMatchObject({
      status: 410,
      code: "AUTHORIZATION_REQUEST_EXPIRED",
      message: "Failed to load authorization request (410): Authorization request expired"
    });
  });

  it("lists connections and revokes one by its encoded grant key", async () => {
    const connections = [
      {
        grantKey: "grant/1",
        clientId: "client-1",
        clientName: "Claude",
        scope: "schatten.read",
        resource: "https://app.localhost/api/mcp/read",
        createdTime: "2026-10-01T10:00:00Z",
        lastUsedTime: null,
        expiresTime: "2026-10-31T10:00:00Z"
      }
    ];
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(connections))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await expect(fetchAiConnections(controller.signal)).resolves.toEqual(connections);
    await expect(revokeAiConnection("grant/1")).resolves.toBeUndefined();

    expect(fetchMock.mock.calls[0]).toEqual([
      "/api/v1/ai/connections",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    ]);
    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/v1/ai/connections/grant%2F1",
      expect.objectContaining({
        method: "DELETE",
        headers: expect.objectContaining({ "X-CSRF-Token": "test-csrf-token" })
      })
    ]);
  });

  it("revokes every AI connection of a User through the admin endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ revokedCount: 3 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(revokeUserAiConnections(102)).resolves.toEqual({ revokedCount: 3 });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/ai/users/102/connections/revoke",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "test-csrf-token" })
      })
    );
  });

  it("reports a connection API failure with its message", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse({ error: { code: "FORBIDDEN", message: "Forbidden" } }, { status: 403 })
        )
    );

    await expect(revokeUserAiConnections(102)).rejects.toThrow(
      "Failed to revoke AI connections (403): Forbidden"
    );
  });
});
