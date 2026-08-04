import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deleteOrganisation,
  updateOrganisation
} from "./organisations";

function jsonResponse(payload: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("organisations API mutations", () => {
  it("uses the patch and delete contracts with URL-encoded stable keys", async () => {
    const updated = { id: "acme / north", name: "Acme North" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(updated))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      updateOrganisation("acme / north", { name: "Acme North" })
    ).resolves.toEqual(updated);
    await expect(deleteOrganisation("acme / north")).resolves.toBeUndefined();

    expect(fetchMock.mock.calls[0]).toEqual([
      "/api/v1/organisations/acme%20%2F%20north",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ name: "Acme North" }),
        headers: expect.objectContaining({
          Accept: "application/json",
          "Content-Type": "application/json"
        })
      })
    ]);
    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/v1/organisations/acme%20%2F%20north",
      expect.objectContaining({ method: "DELETE" })
    ]);
  });

  it("surfaces parsed backend errors for rename and delete failures", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          { detail: "An active organisation with this name already exists." },
          { status: 409 }
        )
      )
      .mockResolvedValueOnce(
        jsonResponse({ detail: "Organisation not found." }, { status: 404 })
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      updateOrganisation("acme", { name: "Beta" })
    ).rejects.toThrow(
      "Failed to update organisation (409): An active organisation with this name already exists."
    );
    await expect(deleteOrganisation("acme")).rejects.toThrow(
      "Failed to delete organisation (404): Organisation not found."
    );
  });
});
