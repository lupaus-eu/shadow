import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchGraphHistory,
  fetchGraphTypeCatalog
} from "./orgTwinStructure";

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("organisation twin structure API", () => {
  it("loads scenario graph history with the supplied abort signal", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ nodes: [], edges: [] })
    );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await expect(
      fetchGraphHistory("acme / north", "future", controller.signal)
    ).resolves.toEqual({ nodes: [], edges: [] });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/organisations/acme%20%2F%20north/scenarios/future/graph/history",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
  });

  it("supports both scenario-level and organisation-state type catalogs", async () => {
    const catalog = { nodeTypes: [], edgeTypes: [], allowedConnections: [] };
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse(catalog))
    );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await fetchGraphTypeCatalog("acme", "future", controller.signal);
    await fetchGraphTypeCatalog("acme", "future", "draft", controller.signal);

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/organisations/acme/scenarios/future/graph/types"
    );
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({ signal: controller.signal })
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/api/v1/organisations/acme/scenarios/future/org-states/draft/graph/types"
    );
    expect(fetchMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({ signal: controller.signal })
    );
  });
});
