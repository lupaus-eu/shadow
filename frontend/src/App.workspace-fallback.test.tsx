import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigateBrowser } from "./auth/browserNavigation";
import App from "./App";

// The real Workspace chunk is cached after its first load, so the workspace
// route's loading and error fallbacks are exercised with a controllable stand-in.
const workspace = vi.hoisted(() => ({
  mode: "loading" as "loading" | "failed",
  pending: new Promise<never>(() => undefined)
}));

vi.mock("./pages/Workspace", async () => {
  const { use } = await import("react");
  return {
    default: function WorkspaceStandIn() {
      if (workspace.mode === "failed") throw new Error("private workspace failure details");
      return use(workspace.pending);
    }
  };
});

vi.mock("./auth/browserNavigation", () => ({
  navigateBrowser: vi.fn()
}));

function mockSessionApi() {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/api/v1/auth/session")) {
      return Promise.resolve(
        Response.json({
          user: { id: 101, name: "Development Admin", email: "admin@example.local", role: "admin" },
          csrfToken: "app-csrf-token"
        })
      );
    }
    if (url.endsWith("/api/v1/auth/logout")) {
      return Promise.resolve(Response.json({ logoutUrl: null }));
    }
    return Promise.resolve(Response.json({}, { status: 404 }));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );
}

describe("workspace route session bar fallback", () => {
  beforeEach(() => {
    vi.mocked(navigateBrowser).mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the session bar while the workspace is loading", async () => {
    workspace.mode = "loading";
    mockSessionApi();

    renderAt("/schatten/acme/org-states");

    expect(await screen.findByRole("status")).toHaveTextContent("Loading workspace...");
    const bar = screen.getByRole("complementary", { name: "Current user session" });
    expect(within(bar).getByRole("button", { name: "Sign out" })).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Sign out" })).toHaveLength(1);
  });

  it("shows the session bar and allows sign out when the workspace fails to load", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    workspace.mode = "failed";
    const fetchMock = mockSessionApi();

    renderAt("/schatten/acme/org-states");

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load workspace");
    const bar = screen.getByRole("complementary", { name: "Current user session" });
    expect(screen.getAllByRole("button", { name: "Sign out" })).toHaveLength(1);

    fireEvent.click(within(bar).getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(navigateBrowser).toHaveBeenCalledWith("/login"));
    expect(
      fetchMock.mock.calls.some(([input]) => String(input).endsWith("/api/v1/auth/logout"))
    ).toBe(true);
    consoleError.mockRestore();
  });
});
