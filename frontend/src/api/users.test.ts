import { afterEach, describe, expect, it, vi } from "vitest";
import { createUser, deleteUser, fetchUsers, updateUser } from "./users";

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

describe("users API", () => {
  it("loads application-wide users with the supplied abort signal", async () => {
    const users = [
      { id: 101, name: "Ada", email: "ada@example.local", role: "admin" }
    ];
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(users));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await expect(fetchUsers(controller.signal)).resolves.toEqual(users);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/users",
      expect.objectContaining({
        method: "GET",
        signal: controller.signal,
        headers: expect.objectContaining({ Accept: "application/json" })
      })
    );
  });

  it("uses the backend create, patch, and delete contracts", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            id: 102,
            name: "Grace",
            email: "grace@example.local",
            role: "consultant"
          },
          { status: 201 }
        )
      )
      .mockResolvedValueOnce(
        jsonResponse({
          id: 102,
          name: "Grace Hopper",
          email: "hopper@example.local",
          role: "admin"
        })
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await createUser({
      name: "Grace",
      email: "grace@example.local",
      role: "consultant"
    });
    await updateUser(102, {
      name: "Grace Hopper",
      email: "hopper@example.local",
      role: "admin"
    });
    await deleteUser(102);

    expect(fetchMock.mock.calls[0]).toEqual([
      "/api/v1/users",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          name: "Grace",
          email: "grace@example.local",
          role: "consultant"
        })
      })
    ]);
    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/v1/users/102",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          name: "Grace Hopper",
          email: "hopper@example.local",
          role: "admin"
        })
      })
    ]);
    expect(fetchMock.mock.calls[2]).toEqual([
      "/api/v1/users/102",
      expect.objectContaining({ method: "DELETE" })
    ]);
  });

  it("extracts FastAPI validation details into an actionable error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { detail: [{ msg: "Input should be 'consultant' or 'admin'" }] },
          { status: 422 }
        )
      )
    );

    await expect(
      createUser({ name: "Ada", email: "ada@example.local", role: "admin" })
    ).rejects.toThrow(
      "Failed to create user (422): Input should be 'consultant' or 'admin'"
    );
  });
});
