import { afterEach, describe, expect, it, vi } from "vitest";
import { authenticatedFetch, configureRequestAuthentication } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("authenticated request transport", () => {
  it("uses same-origin credentials and adds CSRF to unsafe requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const remove = configureRequestAuthentication({
      getCsrfToken: () => "current-csrf",
      onUnauthorized: vi.fn()
    });
    const controller = new AbortController();

    await authenticatedFetch(
      "/api/v1/example",
      { method: "PATCH", headers: { Accept: "application/json" } },
      controller.signal
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/example",
      expect.objectContaining({
        credentials: "same-origin",
        method: "PATCH",
        signal: controller.signal,
        headers: expect.objectContaining({
          Accept: "application/json",
          "X-CSRF-Token": "current-csrf"
        })
      })
    );
    remove();
  });

  it("invalidates authentication on 401 but leaves 403 as a permission error", async () => {
    const onUnauthorized = vi.fn();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 403 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    const remove = configureRequestAuthentication({
      getCsrfToken: () => "current-csrf",
      onUnauthorized
    });

    await authenticatedFetch("/api/v1/forbidden");
    expect(onUnauthorized).not.toHaveBeenCalled();
    await authenticatedFetch("/api/v1/expired");
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    remove();
  });

  it("fails closed before an unsafe request when no CSRF token is available", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const remove = configureRequestAuthentication({
      getCsrfToken: () => null,
      onUnauthorized: vi.fn()
    });

    await expect(authenticatedFetch("/api/v1/example", { method: "DELETE" })).rejects.toThrow(
      "An authenticated session is required"
    );
    expect(fetchMock).not.toHaveBeenCalled();
    remove();
  });
});
