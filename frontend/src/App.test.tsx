import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigateBrowser } from "./auth/browserNavigation";
import App from "./App";

vi.mock("./auth/browserNavigation", () => ({
  navigateBrowser: vi.fn()
}));

function jsonResponse(payload: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });
}

function noContentResponse() {
  return new Response(null, { status: 204 });
}

function deferredResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((resolver) => {
    resolve = resolver;
  });

  return { promise, resolve };
}

function mockSchattenApi(options?: {
  duplicateCreate?: boolean;
  cleanStatus?: number;
  cleanResponse?: Promise<Response>;
  eventsStatus?: number;
  eventMutationStatus?: number;
  omitFutureAfterFirstScenarioLoad?: boolean;
  authRole?: "admin" | "consultant";
  sessionStatus?: number;
  logoutUrl?: string | null;
  mcpEnabled?: boolean;
  mcpChangeSetReview?: boolean;
  consentScope?: string;
}) {
  let cleanedFutureStates = false;
  let scenarioListRequestCount = 0;
  let futureEvents = [
    {
      id: "kickoff",
      name: "Kickoff",
      targetDate: "2026-06-15",
      eventDetails: "Internal kickoff"
    },
    {
      id: "launch-event",
      name: "Launch event",
      targetDate: "2026-07-01",
      eventDetails: ""
    }
  ];

  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";

    if (url.endsWith("/api/v1/auth/session") && method === "GET") {
      if (options?.sessionStatus) {
        return Promise.resolve(
          jsonResponse(
            {
              error: {
                code: "AUTHENTICATION_REQUIRED",
                message: "Authentication required"
              }
            },
            { status: options.sessionStatus }
          )
        );
      }
      return Promise.resolve(
        jsonResponse({
          user: {
            id: 101,
            name: "Development Admin",
            email: "admin@example.local",
            role: options?.authRole ?? "admin"
          },
          csrfToken: "app-csrf-token",
          ...(options?.mcpEnabled
            ? {
                features: {
                  mcp: true,
                  mcpChangeSetReview: options.mcpChangeSetReview ?? false
                }
              }
            : {})
        })
      );
    }

    if (url.startsWith("/api/v1/ai/oauth/consent?") && method === "GET") {
      return Promise.resolve(
        jsonResponse({
          clientName: "Claude",
          clientNameSelfDeclared: true,
          redirectIsLoopback: false,
          redirectHost: "claude.ai",
          scope: options?.consentScope ?? "schatten.read",
          resource: "https://app.localhost/api/mcp/read",
          expiresTime: "2026-10-28T10:10:00Z"
        })
      );
    }

    if (url === "/api/v1/ai/oauth/consent/approve" && method === "POST") {
      return Promise.resolve(jsonResponse({ redirectUrl: consentRedirectUrl }));
    }

    if (url.endsWith("/connections/revoke") && method === "POST") {
      return Promise.resolve(jsonResponse({ revokedCount: 2 }));
    }

    if (url.endsWith("/api/v1/auth/logout") && method === "POST") {
      return Promise.resolve(jsonResponse({ logoutUrl: options?.logoutUrl ?? null }));
    }

    if (url.endsWith("/sessions/revoke") && method === "POST") {
      return Promise.resolve(noContentResponse());
    }

    if (url.endsWith("/api/v1/organisations") && method === "POST") {
      if (options?.duplicateCreate) {
        return Promise.resolve(
          jsonResponse(
            { detail: "An active organisation with this name already exists." },
            { status: 409 }
          )
        );
      }

      return Promise.resolve(jsonResponse({ id: "new-org", name: "New org" }));
    }

    if (url.endsWith("/api/v1/organisations")) {
      return Promise.resolve(
        jsonResponse([
          { id: "beta", name: "Beta" },
          { id: "acme", name: "Acme" }
        ])
      );
    }

    if (url.endsWith("/api/v1/users") && method === "GET") {
      return Promise.resolve(
        jsonResponse([
          {
            id: 101,
            name: "Development Admin",
            email: "admin@example.local",
            role: "admin"
          }
        ])
      );
    }

    if (url.endsWith("/api/v1/customers") && method === "GET") {
      return Promise.resolve(
        jsonResponse([
          {
            id: 201,
            name: "Acme Customer",
            email: null,
            status: "active",
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z"
          }
        ])
      );
    }

    if (url.endsWith("/api/v1/customers/201/contacts") && method === "GET") {
      return Promise.resolve(jsonResponse([]));
    }

    if (url.endsWith("/api/v1/customers/201/addresses") && method === "GET") {
      return Promise.resolve(jsonResponse([]));
    }

    if (url.endsWith("/api/v1/organisations/acme/predictions") && method === "GET") {
      return Promise.resolve(jsonResponse([]));
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios/copy")) {
      return Promise.resolve(
        jsonResponse({
          scenario_id: "copied",
          scenario_name: "Copied scenario",
          scenario_description: "Copied",
          is_protected: false
        })
      );
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios/future/events") && method === "GET") {
      if (options?.eventsStatus) {
        return Promise.resolve(
          jsonResponse({ detail: "Events unavailable." }, { status: options.eventsStatus })
        );
      }
      return Promise.resolve(jsonResponse(futureEvents));
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios/reality/events") && method === "GET") {
      return Promise.resolve(jsonResponse([]));
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios/future/events") && method === "POST") {
      if (options?.eventMutationStatus) {
        return Promise.resolve(
          jsonResponse(
            { detail: "Event mutation failed." },
            { status: options.eventMutationStatus }
          )
        );
      }
      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        name: string;
        targetDate: string;
        eventDetails: string;
      };
      const created = { id: "new-event", ...payload };
      futureEvents = [...futureEvents, created];
      return Promise.resolve(jsonResponse(created, { status: 201 }));
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/events/kickoff") &&
      method === "PATCH"
    ) {
      if (options?.eventMutationStatus) {
        return Promise.resolve(
          jsonResponse(
            { detail: "Event mutation failed." },
            { status: options.eventMutationStatus }
          )
        );
      }
      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        name: string;
        targetDate: string;
        eventDetails: string;
      };
      const updated = { id: "kickoff", ...payload };
      futureEvents = futureEvents.map((event) => (event.id === "kickoff" ? updated : event));
      return Promise.resolve(jsonResponse(updated));
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/events/kickoff") &&
      method === "DELETE"
    ) {
      futureEvents = futureEvents.filter((event) => event.id !== "kickoff");
      return Promise.resolve(noContentResponse());
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios")) {
      scenarioListRequestCount += 1;
      if (options?.omitFutureAfterFirstScenarioLoad && scenarioListRequestCount > 1) {
        return Promise.resolve(
          jsonResponse([
            {
              scenario_id: "reality",
              scenario_name: "Reality",
              scenario_description: "Current baseline"
            }
          ])
        );
      }

      return Promise.resolve(
        jsonResponse([
          {
            scenario_id: "reality",
            scenario_name: "Reality",
            scenario_description: "Current baseline"
          },
          {
            scenario_id: "future",
            metadata: {
              name: "Future plan",
              description: "A possible future"
            },
            is_protected: false
          }
        ])
      );
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios/future") && method === "DELETE") {
      return Promise.resolve(noContentResponse());
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios/future") && method === "PATCH") {
      return Promise.resolve(
        jsonResponse({
          scenario_id: "future",
          scenario_name: "Future plan updated",
          scenario_description: "Updated",
          is_protected: false
        })
      );
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios/reality") && method === "PATCH") {
      return Promise.resolve(
        jsonResponse({
          scenario_id: "reality",
          scenario_name: "Reality updated",
          scenario_description: "Updated current baseline",
          is_protected: true
        })
      );
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios/reality") && method === "GET") {
      return Promise.resolve(
        jsonResponse({
          scenario_id: "reality",
          scenario_name: "Reality",
          scenario_description: "Current baseline",
          is_protected: true
        })
      );
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios/future") && method === "GET") {
      return Promise.resolve(
        jsonResponse({
          scenario_id: "future",
          scenario_name: "Future refreshed",
          scenario_description: "Refreshed from API",
          is_protected: false
        })
      );
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states") &&
      method === "GET"
    ) {
      if (cleanedFutureStates) {
        return Promise.resolve(
          jsonResponse([
            {
              org_state_id: "launch",
              org_state: {
                name: "Planned launch",
                description: "Launch state",
                target_date: "2026-07-01"
              }
            }
          ])
        );
      }

      return Promise.resolve(
        jsonResponse([
          {
            org_state_id: "launch",
            org_state: {
              name: "Planned launch",
              description: "Launch state",
              target_date: "2026-07-01"
            }
          },
          {
            org_state_id: "draft",
            org_state_name: "Draft state",
            org_state_description: "Draft",
            target_date: "2026-06-01"
          }
        ])
      );
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states/clean") &&
      method === "POST"
    ) {
      if (options?.cleanResponse) {
        return options.cleanResponse.then((response) => {
          if (response.ok) cleanedFutureStates = true;
          return response;
        });
      }

      if (options?.cleanStatus) {
        return Promise.resolve(
          jsonResponse({ detail: "Clean states failed." }, { status: options.cleanStatus })
        );
      }

      cleanedFutureStates = true;
      return Promise.resolve(jsonResponse({ cleaned: 1 }));
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states") &&
      method === "POST"
    ) {
      return Promise.resolve(
        jsonResponse({
          org_state_id: "new-state",
          org_state_name: "New state",
          org_state_description: "",
          target_date: "2026-09-01"
        })
      );
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states/draft") &&
      method === "PATCH"
    ) {
      return Promise.resolve(
        jsonResponse({
          org_state_id: "draft",
          org_state_name: "Draft state updated",
          org_state_description: "Draft updated",
          target_date: "2026-06-01"
        })
      );
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states/draft") &&
      method === "DELETE"
    ) {
      return Promise.resolve(noContentResponse());
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states/launch") &&
      method === "DELETE"
    ) {
      return Promise.resolve(noContentResponse());
    }

    if (url === "/api/v1/organisations/acme/ai/change-sets/cs-1" && method === "GET") {
      return Promise.resolve(
        jsonResponse({
          id: "cs-1",
          scenarioKey: null,
          title: "Linked change set",
          rationale: null,
          status: "submitted",
          operationCount: 0,
          clientId: "client-abc",
          clientName: "Claude",
          createdBy: 101,
          createdByName: "Development Admin",
          createdTime: "2026-10-27T09:00:00Z",
          modifiedTime: "2026-10-27T09:00:00Z",
          reviewedBy: null,
          reviewedByName: null,
          reviewedTime: null,
          reviewNote: null,
          operations: [],
          reviewFingerprint: "a".repeat(64),
          validationResult: null,
          appliedResult: null
        })
      );
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios/reality/org-states")) {
      return Promise.resolve(
        jsonResponse([
          {
            org_state_id: "today",
            org_state_name: "Today",
            org_state_description: "Reality now",
            target_date: "2026-06-23"
          }
        ])
      );
    }

    return Promise.resolve(jsonResponse({}, { status: 404 }));
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const consentRedirectUrl =
  "https://claude.ai/api/mcp/auth_callback?code=app-code&state=s%2F1&iss=https%3A%2F%2Fapp.localhost";

function renderAt(initialEntry: string | { pathname: string; state?: unknown }) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <App />
    </MemoryRouter>
  );
}

function todayDateValue(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

describe("Schatten UI shell", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.mocked(navigateBrowser).mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders organisation selection and creation controls on the home page", async () => {
    mockSchattenApi();

    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Select organisation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open organisation" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create organisation" })).toBeDisabled();

    expect(await screen.findByRole("option", { name: "Acme" })).toBeVisible();
    expect(screen.getByLabelText("Create new organisation")).toBeVisible();
  });

  it("keeps protected content hidden until session restoration completes", async () => {
    const sessionResponse = deferredResponse();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/api/v1/auth/session")) {
        return sessionResponse.promise;
      }
      return Promise.resolve(jsonResponse([]));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAt("/");

    expect(screen.getByRole("heading", { name: "Loading session..." })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Select organisation" })).not.toBeInTheDocument();

    sessionResponse.resolve(
      jsonResponse({
        user: {
          id: 101,
          name: "Development Admin",
          email: "admin@example.local",
          role: "admin"
        },
        csrfToken: "restored-csrf"
      })
    );

    expect(await screen.findByRole("heading", { name: "Select organisation" })).toBeVisible();
  });

  it("shows login for an anonymous protected route and preserves that route", async () => {
    mockSchattenApi({ sessionStatus: 401 });

    renderAt("/schatten/acme/users?view=selected");

    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(navigateBrowser).toHaveBeenCalledWith(
      "/api/v1/auth/login?return_to=%2Fschatten%2Facme%2Fusers%3Fview%3Dselected"
    );
  });

  it("invalidates the UI on a business API 401 without repeating restoration", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/session")) {
        return Promise.resolve(
          jsonResponse({
            user: {
              id: 101,
              name: "Development Admin",
              email: "admin@example.local",
              role: "admin"
            },
            csrfToken: "restored-csrf"
          })
        );
      }
      return Promise.resolve(
        jsonResponse(
          { error: { code: "AUTHENTICATION_REQUIRED", message: "Authentication required" } },
          { status: 401 }
        )
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeVisible();
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/api/v1/auth/session"))
    ).toHaveLength(1);
  });

  it("keeps a 403 as a permission error without invalidating the session", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/api/v1/auth/session")) {
        return Promise.resolve(
          jsonResponse({
            user: {
              id: 101,
              name: "Development Admin",
              email: "admin@example.local",
              role: "admin"
            },
            csrfToken: "restored-csrf"
          })
        );
      }
      return Promise.resolve(jsonResponse({ detail: "Permission denied." }, { status: 403 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAt("/");

    expect(
      await screen.findByText("Failed to fetch organisations (403): Permission denied.")
    ).toBeVisible();
    expect(screen.getByText("Development Admin")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("hides Users and redirects its route for consultants", async () => {
    mockSchattenApi({ authRole: "consultant" });

    renderAt("/schatten/acme/users");

    expect(await screen.findByRole("heading", { name: "Scenarios", level: 1 })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Users" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Users" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke AI connections" })).not.toBeInTheDocument();
  });

  it("revokes a User's AI connections from Users administration", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/users");
    await screen.findByRole("button", { name: /Development Admin/ });
    fireEvent.click(await screen.findByRole("button", { name: "Revoke AI connections" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm revoke AI connections" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "2 AI connection(s) of Development Admin were revoked."
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/ai/users/101/connections/revoke",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "app-csrf-token" })
      })
    );
  });

  it("shows login for an anonymous consent request and returns to it after sign-in", async () => {
    const fetchMock = mockSchattenApi({ sessionStatus: 401 });

    renderAt("/ai/authorize?request=pending-id");

    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(navigateBrowser).toHaveBeenCalledWith(
      "/api/v1/auth/login?return_to=%2Fai%2Fauthorize%3Frequest%3Dpending-id"
    );
    expect(
      fetchMock.mock.calls.some(([input]) => String(input).startsWith("/api/v1/ai/oauth"))
    ).toBe(false);
  });

  it("approves a consent request with the session CSRF token", async () => {
    const fetchMock = mockSchattenApi({ mcpEnabled: true });

    renderAt("/ai/authorize?request=pending-id");

    expect(await screen.findByRole("heading", { name: "Connect an AI client" })).toBeVisible();
    expect(await screen.findByText("claude.ai")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => expect(navigateBrowser).toHaveBeenCalledWith(consentRedirectUrl));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/ai/oauth/consent?request=pending-id",
      expect.objectContaining({ method: "GET" })
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/ai/oauth/consent/approve",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ request: "pending-id" }),
        headers: expect.objectContaining({ "X-CSRF-Token": "app-csrf-token" })
      })
    );
  });

  it("explains write access from the session's MCP change-set review flag", async () => {
    mockSchattenApi({
      mcpEnabled: true,
      mcpChangeSetReview: true,
      consentScope: "schatten.write"
    });

    renderAt("/ai/authorize?request=pending-id");

    expect(
      await screen.findByRole("heading", {
        name: "Write access: propose, apply and reject changes"
      })
    ).toBeVisible();
  });

  it("shows the consent page as not available when the session has no MCP feature", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/ai/authorize?request=pending-id");

    expect(
      await screen.findByRole("heading", { name: "AI connections are not available" })
    ).toBeVisible();
    expect(
      fetchMock.mock.calls.some(([input]) => String(input).startsWith("/api/v1/ai/oauth"))
    ).toBe(false);
  });

  it("opens the Metrics AI panel on the change set of a review link", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/metrics?changeSet=cs-1");

    const panel = await screen.findByRole("complementary", { name: "AI" });
    expect(await within(panel).findByRole("heading", { name: "Linked change set" })).toBeVisible();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/organisations/acme/ai/change-sets/cs-1",
      expect.objectContaining({ method: "GET" })
    );

    fireEvent.click(within(panel).getByRole("button", { name: "Close AI panel" }));

    await waitFor(() =>
      expect(screen.queryByRole("complementary", { name: "AI" })).not.toBeInTheDocument()
    );
    expect(screen.getByRole("link", { name: "Metrics" })).toHaveClass("tab-link--active");
  });

  it("returns an admin to login after revoking their own sessions", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/users");
    await screen.findByRole("button", { name: /Development Admin/ });
    fireEvent.click(screen.getByRole("button", { name: "Revoke sessions" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm revoke sessions" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  it("logs out with CSRF and navigates to the local login page", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/");
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(navigateBrowser).toHaveBeenCalledWith("/login"));
    const logoutCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/v1/auth/logout")
    );
    expect(logoutCall?.[1]).toEqual(
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        headers: expect.objectContaining({ "X-CSRF-Token": "app-csrf-token" })
      })
    );
  });

  it("shows the session controls in the workspace header instead of the session bar", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    const banner = await screen.findByRole("banner");
    const session = within(banner).getByRole("group", { name: "Current user session" });
    expect(within(session).getByText("Development Admin")).toBeVisible();
    expect(within(session).getByText("Admin")).toBeVisible();
    expect(within(session).getByRole("button", { name: "Sign out" })).toBeVisible();
    expect(screen.getByLabelText("Current workspace context")).not.toContainElement(session);
    expect(screen.getAllByRole("button", { name: "Sign out" })).toHaveLength(1);
    expect(
      screen.queryByRole("complementary", { name: "Current user session" })
    ).not.toBeInTheDocument();
  });

  it.each(["/", "/404"])("shows the separate session bar on %s", async (path) => {
    mockSchattenApi();

    renderAt(path);

    const bar = await screen.findByRole("complementary", { name: "Current user session" });
    expect(within(bar).getByText("Development Admin")).toBeVisible();
    expect(within(bar).getByRole("button", { name: "Sign out" })).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Sign out" })).toHaveLength(1);
  });

  it("logs out with CSRF from the workspace header", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");
    const banner = await screen.findByRole("banner");
    fireEvent.click(within(banner).getByRole("button", { name: "Sign out" }));

    expect(within(banner).getByRole("button", { name: "Signing out..." })).toBeDisabled();
    await waitFor(() => expect(navigateBrowser).toHaveBeenCalledWith("/login"));
    const logoutCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/v1/auth/logout")
    );
    expect(logoutCall?.[1]).toEqual(
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        headers: expect.objectContaining({ "X-CSRF-Token": "app-csrf-token" })
      })
    );
  });

  it("navigates to the trusted provider logout URL", async () => {
    mockSchattenApi({ logoutUrl: "https://identity.example.test/logout" });

    renderAt("/");
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    await waitFor(() => {
      expect(navigateBrowser).toHaveBeenCalledWith("https://identity.example.test/logout");
    });
  });

  it("clears frontend auth after a successful logout with an invalid payload", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/session")) {
        return Promise.resolve(
          jsonResponse({
            user: {
              id: 101,
              name: "Development Admin",
              email: "admin@example.local",
              role: "admin"
            },
            csrfToken: "app-csrf-token"
          })
        );
      }
      if (url.endsWith("/api/v1/auth/logout")) {
        return Promise.resolve(jsonResponse({ unexpected: true }));
      }
      return Promise.resolve(jsonResponse([]));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAt("/");
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeVisible();
    expect(screen.getByText("Invalid logout response.")).toBeVisible();
    expect(navigateBrowser).not.toHaveBeenCalled();
  });

  it("creates an organisation through the backend API and selects it", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/");

    const nameInput = await screen.findByLabelText("Create new organisation");
    fireEvent.change(nameInput, { target: { value: "New org" } });
    fireEvent.click(screen.getByRole("button", { name: "Create organisation" }));

    expect(await screen.findByRole("option", { name: "New org" })).toBeVisible();
    expect(screen.getByLabelText("Organisation")).toHaveValue("new-org");
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        return (
          String(input).endsWith("/api/v1/organisations") &&
          init?.method === "POST" &&
          init.body === JSON.stringify({ name: "New org" })
        );
      })
    ).toBe(true);
  });

  it("shows duplicate organisation errors from the backend clearly", async () => {
    mockSchattenApi({ duplicateCreate: true });

    renderAt("/");

    fireEvent.change(await screen.findByLabelText("Create new organisation"), {
      target: { value: "Acme" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Create organisation" }));

    expect(
      await screen.findByText(
        "Failed to create organisation (409): An active organisation with this name already exists."
      )
    ).toBeInTheDocument();
  });

  it("redirects an organisation workspace URL to the default Scenarios tab", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme");

    expect(await screen.findByRole("heading", { name: "Scenarios", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Scenarios" })).toHaveClass("tab-link--active");
  });

  it("shows the scenario count and refresh control", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    expect(await screen.findByText("2 scenario(s)")).toBeInTheDocument();
    await screen.findByRole("button", { name: /Today/ });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          const url = String(input);
          return (
            url.endsWith("/api/v1/organisations/acme/scenarios/reality") &&
            (init?.method ?? "GET") === "GET"
          );
        })
      ).toBe(true);
    });
  });

  it("refreshes the selected scenario and states from read endpoints", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await screen.findByRole("button", { name: /Future refreshed/ });
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        const url = String(input);
        return (
          url.endsWith("/api/v1/organisations/acme/scenarios/future") &&
          (init?.method ?? "GET") === "GET"
        );
      })
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        const url = String(input);
        return (
          url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states") &&
          (init?.method ?? "GET") === "GET"
        );
      })
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith(
          "/api/v1/organisations/acme/scenarios/future/org-states/synchronise-graph-dates"
        )
      )
    ).toBe(false);
    expect(screen.getByTitle("Scenario: Future refreshed")).toBeInTheDocument();
    expect(screen.getByTitle("Org state: Draft state (2026-06-01)")).toBeInTheDocument();
  });

  it("renders tab URLs and disables Structure and Events before selection", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    const expectedLinks = [
      ["Scenarios", "/schatten/acme/org-states"],
      ["Metrics", "/schatten/acme/metrics"],
      ["Summary", "/schatten/acme/summary"],
      ["Analysis", "/schatten/acme/analysis"],
      ["Predictions", "/schatten/acme/predictions"],
      ["Customers", "/schatten/acme/customers"],
      ["Users", "/schatten/acme/users"]
    ] as const;

    await screen.findByRole("link", { name: "Scenarios" });
    for (const [label, href] of expectedLinks) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
    expect(screen.queryByRole("link", { name: "Structure" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Events" })).not.toBeInTheDocument();
    expect(screen.getByText("Structure")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Events")).toHaveAttribute("aria-disabled", "true");
  });

  it("marks the active tab from the current URL", async () => {
    mockSchattenApi();
    renderAt("/schatten/acme/metrics");

    expect(await screen.findByRole("link", { name: "Metrics" })).toHaveClass("tab-link--active");
    expect(screen.getByRole("link", { name: "Scenarios" })).not.toHaveClass("tab-link--active");
  });

  it("renders the application-wide Users route without workspace selections", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/users");

    expect(await screen.findByRole("link", { name: "Users" })).toHaveClass("tab-link--active");
    expect(await screen.findByRole("heading", { name: "Users" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Development Admin/ })).toBeVisible();
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) => String(input) === "/api/v1/users" && init?.method === "GET"
      )
    ).toBe(true);
  });

  it("renders the application-wide Customers route without workspace context in its API", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/customers");

    expect(await screen.findByRole("link", { name: "Customers" })).toHaveClass("tab-link--active");
    expect(await screen.findByRole("heading", { name: "Customers" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Acme Customer/ })).toBeVisible();
    const customerPaths = () =>
      fetchMock.mock.calls
        .map(([input]) => String(input))
        .filter((url) => url.includes("/api/v1/customers"));
    await waitFor(() =>
      expect(customerPaths()).toEqual(
        expect.arrayContaining([
          "/api/v1/customers",
          "/api/v1/customers/201/addresses",
          "/api/v1/customers/201/contacts"
        ])
      )
    );
    expect(await screen.findByText("No addresses available.")).toBeInTheDocument();
    expect(await screen.findByText("No contacts available.")).toBeInTheDocument();
    expect(customerPaths().every((url) => !url.includes("acme"))).toBe(true);
  });

  it("renders the Summary route without requiring an organisation state", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/summary");

    expect(await screen.findByRole("link", { name: "Summary" })).toHaveClass("tab-link--active");
    expect(await screen.findByRole("heading", { name: "Summary" })).toBeInTheDocument();
    expect(screen.getByText(/Select a scenario/)).toBeInTheDocument();
  });

  it("renders Predictions without a selected scenario or organisation state", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/predictions");

    expect(await screen.findByText(/selected scenario's own data/i)).toBeVisible();
    expect(screen.getByRole("link", { name: "Predictions" })).toHaveClass("tab-link--active");
    expect(screen.getByTitle("Scenario: None")).toBeInTheDocument();
    expect(screen.getByTitle("Org state: None")).toBeInTheDocument();
  });

  it("shows the organisation, scenario, and org state indicators", async () => {
    mockSchattenApi();
    renderAt({
      pathname: "/schatten/acme/analysis",
      state: { organisationName: "Acme" }
    });

    await waitFor(() => {
      expect(screen.getByTitle("Organisation: Acme")).toBeInTheDocument();
    });
    expect(screen.getByTitle("Scenario: None")).toBeInTheDocument();
    expect(screen.getByTitle("Org state: None")).toBeInTheDocument();
  });

  it("shows protected scenarios, allows Reality editing, and blocks deletion", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Reality/ }));

    expect(screen.getAllByText("Protected")).not.toHaveLength(0);
    expect(screen.getByText("Protected scenario cannot be deleted.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete scenario" })).not.toBeInTheDocument();

    const selectedScenarioPanel = screen.getByRole("region", {
      name: "Selected scenario"
    });
    const nameInput = within(selectedScenarioPanel).getByLabelText("Name");
    const descriptionInput = within(selectedScenarioPanel).getByLabelText("Description");
    const saveButton = within(selectedScenarioPanel).getByRole("button", {
      name: "Save scenario"
    });

    expect(nameInput).toHaveValue("Reality");
    expect(selectedScenarioPanel.querySelector("label[for='scenario-edit-name']")).toHaveClass(
      "form-label--required"
    );
    expect(descriptionInput).toHaveValue("Current baseline");
    expect(nameInput).not.toBeDisabled();
    expect(descriptionInput).not.toBeDisabled();
    expect(saveButton).toBeDisabled();

    fireEvent.change(descriptionInput, {
      target: { value: "Updated current baseline" }
    });
    expect(saveButton).not.toBeDisabled();
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          const url = String(input);
          return (
            url.endsWith("/api/v1/organisations/acme/scenarios/reality") && init?.method === "PATCH"
          );
        })
      ).toBe(true);
    });
  });

  it("disables clean states until an editable scenario is selected", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    expect(await screen.findByText("2 scenario(s)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clean states" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /Reality/ }));
    expect(screen.getByRole("button", { name: "Clean states" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    expect(screen.getByRole("button", { name: "Clean states" })).not.toBeDisabled();
  });

  it("confirms before cleaning states and refreshes the selected scenario states", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });

    fireEvent.click(screen.getByRole("button", { name: "Clean states" }));
    expect(screen.getByRole("button", { name: "Confirm clean states" })).toBeVisible();
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        return (
          String(input).endsWith("/api/v1/organisations/acme/scenarios/future/org-states/clean") &&
          init?.method === "POST"
        );
      })
    ).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Confirm clean states" }));

    expect(await screen.findByText("Cleaned 1 state(s).")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        return (
          String(input).endsWith("/api/v1/organisations/acme/scenarios/future/org-states/clean") &&
          init?.method === "POST"
        );
      })
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        const url = String(input);
        return (
          url.endsWith("/api/v1/organisations/acme/scenarios/future") &&
          (init?.method ?? "GET") === "GET"
        );
      })
    ).toBe(true);
    expect(screen.queryByRole("button", { name: /Draft state/ })).not.toBeInTheDocument();
    expect(screen.getByTitle("Org state: Planned launch (2026-07-01)")).toBeInTheDocument();
  });

  it("shows a busy clean states state while cleanup is in progress", async () => {
    const cleanDeferred = deferredResponse();
    mockSchattenApi({ cleanResponse: cleanDeferred.promise });

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("button", { name: "Clean states" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm clean states" }));

    const cleaningButtons = screen.getAllByRole("button", {
      name: "Cleaning..."
    });
    expect(cleaningButtons).toHaveLength(2);
    cleaningButtons.forEach((button) => expect(button).toBeDisabled());
    cleanDeferred.resolve(jsonResponse({ cleaned: 1 }));

    expect(await screen.findByText("Cleaned 1 state(s).")).toBeInTheDocument();
  });

  it.each([
    [404, "The selected scenario could not be found. Refresh scenarios and try again."],
    [409, "Protected scenarios cannot be cleaned."],
    [500, "The server could not clean states right now. Try again later."]
  ])("shows a friendly clean states error for %i responses", async (status, message) => {
    mockSchattenApi({ cleanStatus: status });

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("button", { name: "Clean states" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm clean states" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("disables scenario save until editable fields change", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));

    const selectedScenarioPanel = screen.getByRole("region", {
      name: "Selected scenario"
    });
    const nameInput = within(selectedScenarioPanel).getByLabelText("Name");
    const descriptionInput = within(selectedScenarioPanel).getByLabelText("Description");
    const saveButton = within(selectedScenarioPanel).getByRole("button", {
      name: "Save scenario"
    });

    expect(nameInput).toHaveValue("Future plan");
    expect(descriptionInput).toHaveValue("A possible future");
    expect(saveButton).toBeDisabled();

    fireEvent.change(nameInput, { target: { value: "" } });
    expect(saveButton).toBeDisabled();

    fireEvent.change(nameInput, { target: { value: "Future plan updated" } });
    expect(saveButton).not.toBeDisabled();
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          const url = String(input);
          return (
            url.endsWith("/api/v1/organisations/acme/scenarios/future") &&
            init?.method === "PATCH" &&
            init.body ===
              JSON.stringify({
                name: "Future plan updated",
                description: "A possible future"
              })
          );
        })
      ).toBe(true);
    });
  });

  it("auto-selects the first scenario and first state on initial load", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    await screen.findByRole("button", { name: /Reality/ });
    await screen.findByRole("button", { name: /Today/ });

    expect(screen.getByTitle("Scenario: Reality")).toBeInTheDocument();
    expect(screen.getByTitle("Org state: Today (2026-06-23)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Structure" })).toHaveAttribute(
      "href",
      "/schatten/acme/graph"
    );
    expect(screen.getByRole("link", { name: "Events" })).toHaveAttribute(
      "href",
      "/schatten/acme/events"
    );
  });

  it("switches header context in place and refetches the active Events tab", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");
    await screen.findByTitle("Org state: Today (2026-06-23)");
    fireEvent.click(screen.getByRole("link", { name: "Events" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).endsWith("/api/v1/organisations/acme/scenarios/reality/events")
        )
      ).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: "Change scenario" }));
    const scenarioDialog = await screen.findByRole("dialog", {
      name: "Scenario and org state selector"
    });
    const scenarioColumn = within(scenarioDialog).getByRole("region", {
      name: "Scenarios"
    });
    fireEvent.click(
      await within(scenarioColumn).findByRole("button", {
        name: /Future plan/
      })
    );
    const stateColumn = within(scenarioDialog).getByRole("region", {
      name: "Scenario org states"
    });
    await within(stateColumn).findByRole("button", { name: /Draft state/ });

    expect(screen.getByRole("link", { name: "Events" })).toHaveClass("tab-link--active");
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith("/api/v1/organisations/acme/scenarios/future/events")
      )
    ).toBe(false);

    fireEvent.click(within(scenarioDialog).getByRole("button", { name: "Select" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).endsWith("/api/v1/organisations/acme/scenarios/future/events")
        )
      ).toBe(true);
    });
    expect(screen.getByRole("link", { name: "Events" })).toHaveClass("tab-link--active");
    expect(screen.getByTitle("Scenario: Future plan")).toBeInTheDocument();
    expect(screen.getByTitle("Org state: Draft state (2026-06-01)")).toBeInTheDocument();

    const futureEventReadCount = fetchMock.mock.calls.filter(
      ([input, init]) =>
        String(input).endsWith("/api/v1/organisations/acme/scenarios/future/events") &&
        (init?.method ?? "GET") === "GET"
    ).length;
    fireEvent.click(screen.getByRole("button", { name: "Change org state" }));
    const orgStateDialog = await screen.findByRole("dialog", {
      name: "Org state selector"
    });
    fireEvent.click(
      await within(orgStateDialog).findByRole("button", {
        name: /Planned launch/
      })
    );

    expect(screen.getByRole("link", { name: "Events" })).toHaveClass("tab-link--active");
    expect(screen.getByTitle("Scenario: Future plan")).toBeInTheDocument();
    expect(screen.getByTitle("Org state: Planned launch (2026-07-01)")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(
        ([input, init]) =>
          String(input).endsWith("/api/v1/organisations/acme/scenarios/future/events") &&
          (init?.method ?? "GET") === "GET"
      )
    ).toHaveLength(futureEventReadCount);
  });

  it("reconciles Scenarios forms when header context changes in place", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");
    await screen.findByTitle("Org state: Today (2026-06-23)");

    fireEvent.click(screen.getByRole("button", { name: "Change scenario" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Scenario and org state selector"
    });
    fireEvent.click(
      await within(within(dialog).getByRole("region", { name: "Scenarios" })).findByRole("button", {
        name: /Future plan/
      })
    );
    await within(within(dialog).getByRole("region", { name: "Scenario org states" })).findByRole(
      "button",
      { name: /Draft state/ }
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Select" }));

    const selectedScenarioPanel = screen.getByRole("region", {
      name: "Selected scenario"
    });
    await waitFor(() => {
      expect(within(selectedScenarioPanel).getByLabelText("Name")).toHaveValue("Future plan");
      expect(within(selectedScenarioPanel).getByLabelText("Description")).toHaveValue(
        "A possible future"
      );
    });
    expect(screen.getByRole("link", { name: "Scenarios" })).toHaveClass("tab-link--active");
    expect(screen.getByTitle("Org state: Draft state (2026-06-01)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "State" }));
    const selectedStateHeading = await screen.findByRole("heading", {
      name: "Draft state"
    });
    const selectedStatePanel = selectedStateHeading.closest("section");
    expect(selectedStatePanel).not.toBeNull();
    expect(within(selectedStatePanel!).getByLabelText("Name")).toHaveValue("Draft state");
    expect(within(selectedStatePanel!).getByLabelText("Target date")).toHaveValue("2026-06-01");
  });

  it("renders the selected scenario group without sidebar descriptions", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });

    const scenarioList = screen.getByLabelText("Scenario list");
    const selectedScenarioButton = within(scenarioList).getByRole("button", {
      name: /Future plan/
    });
    const selectedScenarioGroup = selectedScenarioButton.closest(".scenario-list-item");

    expect(selectedScenarioGroup).toHaveClass("scenario-list-item--selected");
    expect(selectedScenarioButton).toHaveClass("entity-row--selected");
    expect(within(scenarioList).getByText("STATES")).toBeInTheDocument();
    expect(within(scenarioList).queryByText("A possible future")).not.toBeInTheDocument();
    expect(within(scenarioList).queryByText("Draft")).not.toBeInTheDocument();
    expect(within(scenarioList).getByRole("button", { name: /Draft state/ })).toHaveClass(
      "entity-row--selected"
    );
  });

  it("chooses a fork source state without changing the active org-state view", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });

    expect(screen.getByTitle("Org state: Draft state (2026-06-01)")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Selected scenario" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Source state"), {
      target: { value: "launch" }
    });
    const forkForm = screen.getByRole("form", { name: "Fork from existing" });
    fireEvent.change(within(forkForm).getByLabelText(/Name/), {
      target: { value: "" }
    });

    expect(screen.getByTitle("Org state: Draft state (2026-06-01)")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Selected scenario" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Fork scenario" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          const url = String(input);
          return (
            url.endsWith("/api/v1/organisations/acme/scenarios/copy") &&
            init?.method === "POST" &&
            init.body ===
              JSON.stringify({
                sourceScenarioId: "future",
                sourceOrgStateId: "launch",
                description: "A possible future"
              })
          );
        })
      ).toBe(true);
    });
  });

  it("chooses a fork source scenario without changing the active workspace scenario", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    await screen.findByRole("button", { name: /Today/ });
    const forkForm = screen.getByRole("form", { name: "Fork from existing" });

    fireEvent.change(within(forkForm).getByLabelText("Source scenario"), {
      target: { value: "future" }
    });

    await waitFor(() => {
      expect(within(forkForm).getByLabelText("Source state")).toHaveValue("draft");
    });

    expect(screen.getByTitle("Scenario: Reality")).toBeInTheDocument();
    expect(screen.getByTitle("Org state: Today (2026-06-23)")).toBeInTheDocument();
    expect(within(forkForm).getByLabelText(/Name/)).toHaveValue("Fork of Future plan");
    expect(within(forkForm).getByLabelText(/Description/)).toHaveValue("A possible future");

    fireEvent.click(within(forkForm).getByRole("button", { name: "Fork scenario" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          return (
            String(input).endsWith("/api/v1/organisations/acme/scenarios/copy") &&
            init?.method === "POST" &&
            init.body ===
              JSON.stringify({
                sourceScenarioId: "future",
                sourceOrgStateId: "draft",
                name: "Fork of Future plan",
                description: "A possible future"
              })
          );
        })
      ).toBe(true);
    });
  });

  it("shows states under the selected scenario and auto-selects the first state", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });

    expect(screen.getByLabelText("Scenario list")).toContainElement(
      screen.getByLabelText("Org state list")
    );

    expect(screen.getByTitle("Scenario: Future plan")).toBeInTheDocument();
    expect(screen.getByTitle("Org state: Draft state (2026-06-01)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Structure" })).toHaveAttribute(
      "href",
      "/schatten/acme/graph"
    );
    expect(screen.getByRole("link", { name: "Events" })).toHaveAttribute(
      "href",
      "/schatten/acme/events"
    );

    fireEvent.click(screen.getByRole("button", { name: /Reality/ }));
    await screen.findByRole("button", { name: /Today/ });
    const stateList = screen.getByLabelText("Org state list");
    expect(within(stateList).getByRole("button", { name: /Today/ })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Draft state/ })).not.toBeInTheDocument();
  });

  it("preserves the selected org state when returning to Scenarios", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("button", { name: /Planned launch/ }));

    expect(screen.getByTitle("Org state: Planned launch (2026-07-01)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Events" }));
    expect(await screen.findByRole("heading", { name: "Events", level: 1 })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Scenarios" }));

    await waitFor(() => {
      expect(screen.getByTitle("Org state: Planned launch (2026-07-01)")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Planned launch/ })).toHaveClass(
        "entity-row--selected"
      );
    });

    const selectedScenarioPanel = screen.getByRole("region", {
      name: "Selected scenario"
    });
    expect(within(selectedScenarioPanel).getByLabelText("Name")).toHaveValue("Future plan");
    expect(within(selectedScenarioPanel).getByLabelText("Description")).toHaveValue(
      "A possible future"
    );
    expect(
      within(selectedScenarioPanel).getByRole("button", {
        name: "Save scenario"
      })
    ).toBeDisabled();

    const forkForm = screen.getByRole("form", { name: "Fork from existing" });
    expect(within(forkForm).getByLabelText(/Name/)).toHaveValue("Fork of Future plan");
    expect(within(forkForm).getByLabelText(/Description/)).toHaveValue("A possible future");
  });

  it("falls back when the selected scenario is missing on return", async () => {
    mockSchattenApi({ omitFutureAfterFirstScenarioLoad: true });

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    expect(screen.getByTitle("Org state: Draft state (2026-06-01)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Events" }));
    expect(await screen.findByRole("heading", { name: "Events", level: 1 })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Scenarios" }));

    await waitFor(() => {
      expect(screen.getByTitle("Scenario: Reality")).toBeInTheDocument();
      expect(screen.getByTitle("Org state: Today (2026-06-23)")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /Draft state/ })).not.toBeInTheDocument();

    const selectedScenarioPanel = screen.getByRole("region", {
      name: "Selected scenario"
    });
    expect(within(selectedScenarioPanel).getByLabelText("Name")).toHaveValue("Reality");
    expect(within(selectedScenarioPanel).getByLabelText("Description")).toHaveValue(
      "Current baseline"
    );
  });

  it("edits the selected org state immediately and saves only after changes", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("button", { name: "State" }));

    expect(screen.queryByRole("button", { name: "Edit state" })).not.toBeInTheDocument();
    expect(screen.queryByText("State ID")).not.toBeInTheDocument();

    const selectedStatePanel = screen.getByRole("region", {
      name: "Draft state"
    });
    const nameInput = within(selectedStatePanel).getByLabelText("Name");
    const descriptionInput = within(selectedStatePanel).getByLabelText("Description");
    const saveButton = within(selectedStatePanel).getByRole("button", {
      name: "Save state"
    });

    expect(nameInput).toHaveValue("Draft state");
    expect(descriptionInput).toHaveValue("Draft");
    expect(saveButton).toBeDisabled();

    fireEvent.change(descriptionInput, { target: { value: "Draft updated" } });
    expect(saveButton).not.toBeDisabled();
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          const url = String(input);
          return (
            url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states/draft") &&
            init?.method === "PATCH" &&
            init.body ===
              JSON.stringify({
                name: "Draft state",
                description: "Draft updated",
                targetDate: "2026-06-01"
              })
          );
        })
      ).toBe(true);
    });
  });

  it("requires exact DELETE before org-state deletion can be submitted", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("button", { name: "State" }));

    const selectedStatePanel = screen.getByRole("region", {
      name: "Draft state"
    });
    const confirmInput = within(selectedStatePanel).getByPlaceholderText("Type DELETE to confirm");
    const deleteButton = within(selectedStatePanel).getByRole("button", {
      name: "Delete state"
    });

    expect(deleteButton).toBeDisabled();

    fireEvent.change(confirmInput, { target: { value: "delete" } });
    expect(deleteButton).toBeDisabled();

    fireEvent.change(confirmInput, { target: { value: "DELETE" } });
    expect(deleteButton).not.toBeDisabled();
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          const url = String(input);
          return (
            url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states/draft") &&
            init?.method === "DELETE"
          );
        })
      ).toBe(true);
    });
  });

  it("blocks duplicate org-state target dates before submitting", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Planned launch/ });
    fireEvent.click(screen.getByRole("button", { name: "State" }));
    const createStatePanel = screen.getByRole("form", {
      name: "Create state"
    });
    expect(within(createStatePanel).getByLabelText("Target date")).toHaveValue(todayDateValue());
    fireEvent.change(within(createStatePanel).getByLabelText("Name"), {
      target: { value: "Duplicate date state" }
    });
    fireEvent.change(within(createStatePanel).getByLabelText("Target date"), {
      target: { value: "2026-07-01" }
    });
    fireEvent.click(within(createStatePanel).getByRole("button", { name: "Create state" }));

    expect(
      await screen.findByText("Target date must be unique within the scenario.")
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        const url = String(input);
        return (
          url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states") &&
          init?.method === "POST"
        );
      })
    ).toBe(false);
  });

  it("requires DELETE before scenario deletion can be submitted", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    fireEvent.click(screen.getByRole("button", { name: "Delete scenario" }));

    const deleteButtons = screen.getAllByRole("button", {
      name: "Delete scenario"
    });
    const confirmDeleteButton = deleteButtons[deleteButtons.length - 1];
    expect(confirmDeleteButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Confirmation"), {
      target: { value: "DELETE" }
    });
    expect(confirmDeleteButton).not.toBeDisabled();
    fireEvent.click(confirmDeleteButton);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          const url = String(input);
          return (
            url.endsWith("/api/v1/organisations/acme/scenarios/future") && init?.method === "DELETE"
          );
        })
      ).toBe(true);
    });
  });

  it("keeps Events gated on direct route until scenario and state are selected", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/events");

    expect(
      await screen.findByText("Select a scenario and org state in Scenarios to activate this tab.")
    ).toBeInTheDocument();
  });

  it("loads events for the selected scenario and auto-selects the first event", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("link", { name: "Events" }));

    expect(await screen.findByRole("heading", { name: "Events", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("2 event(s)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Kickoff/ })).toHaveClass("entity-row--selected");
    expect(screen.getByRole("button", { name: /Kickoff/ })).toHaveTextContent(
      /Past\s*2026-06-15\s*Kickoff\s*Internal kickoff/
    );
    expect(screen.getByRole("button", { name: /Launch event/ })).toHaveTextContent("No details");
    expect(screen.getByRole("heading", { name: "Kickoff" })).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        const url = String(input);
        return (
          url.endsWith("/api/v1/organisations/acme/scenarios/future/events") &&
          (init?.method ?? "GET") === "GET"
        );
      })
    ).toBe(true);
  });

  it("shows an empty Events state for a selected scenario without events", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    await screen.findByRole("button", { name: /Today/ });
    fireEvent.click(screen.getByRole("link", { name: "Events" }));

    expect(await screen.findByText("No events available.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No event selected" })).toBeInTheDocument();
  });

  it("creates an event and refreshes the event list selection", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("link", { name: "Events" }));
    await screen.findByRole("button", { name: /Kickoff/ });

    const createEventForm = screen.getByRole("form", { name: "Create event" });
    expect(createEventForm.querySelector("label[for='event-create-name']")).toHaveClass(
      "form-label--required"
    );
    expect(within(createEventForm).getByLabelText("Target date")).toHaveValue(todayDateValue());
    fireEvent.change(within(createEventForm).getByLabelText("Name"), {
      target: { value: "Board review" }
    });
    fireEvent.change(within(createEventForm).getByLabelText("Event details"), {
      target: { value: "Review growth plan" }
    });
    fireEvent.click(within(createEventForm).getByRole("button", { name: "Create event" }));

    const createdEventRow = await screen.findByRole("button", {
      name: /Board review/
    });
    expect(createdEventRow).toHaveClass("entity-row--selected");
    expect(createdEventRow).toHaveTextContent(
      new RegExp(`Upcoming\\s*${todayDateValue()}\\s*Board review\\s*Review growth plan`)
    );
    expect(screen.getByRole("heading", { name: "Board review" })).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        const url = String(input);
        return (
          url.endsWith("/api/v1/organisations/acme/scenarios/future/events") &&
          init?.method === "POST" &&
          init.body ===
            JSON.stringify({
              name: "Board review",
              targetDate: todayDateValue(),
              eventDetails: "Review growth plan"
            })
        );
      })
    ).toBe(true);
  });

  it("edits the selected event and refreshes the selected detail", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("link", { name: "Events" }));

    await screen.findByRole("button", { name: /Kickoff/ });
    const selectedEventPanel = screen.getByRole("region", { name: "Kickoff" });
    const detailsInput = within(selectedEventPanel).getByLabelText("Event details");
    const saveButton = within(selectedEventPanel).getByRole("button", {
      name: "Save event"
    });

    expect(detailsInput).toHaveValue("Internal kickoff");
    expect(saveButton).toBeDisabled();

    fireEvent.change(detailsInput, { target: { value: "Updated kickoff" } });
    expect(saveButton).not.toBeDisabled();
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          const url = String(input);
          return (
            url.endsWith("/api/v1/organisations/acme/scenarios/future/events/kickoff") &&
            init?.method === "PATCH" &&
            init.body ===
              JSON.stringify({
                name: "Kickoff",
                targetDate: "2026-06-15",
                eventDetails: "Updated kickoff"
              })
          );
        })
      ).toBe(true);
    });
    expect(await screen.findByDisplayValue("Updated kickoff")).toBeInTheDocument();
  });

  it("confirms event deletion with yes and no buttons", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("link", { name: "Events" }));

    await screen.findByRole("button", { name: /Kickoff/ });
    const selectedEventPanel = screen.getByRole("region", { name: "Kickoff" });

    fireEvent.click(
      within(selectedEventPanel).getByRole("button", {
        name: "Delete event"
      })
    );
    expect(
      within(selectedEventPanel).getByText("Are you sure you want to delete the selected event?")
    ).toBeInTheDocument();

    fireEvent.click(within(selectedEventPanel).getByRole("button", { name: "No" }));
    expect(
      within(selectedEventPanel).queryByText("Are you sure you want to delete the selected event?")
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        const url = String(input);
        return (
          url.endsWith("/api/v1/organisations/acme/scenarios/future/events/kickoff") &&
          init?.method === "DELETE"
        );
      })
    ).toBe(false);

    fireEvent.click(
      within(selectedEventPanel).getByRole("button", {
        name: "Delete event"
      })
    );
    fireEvent.click(within(selectedEventPanel).getByRole("button", { name: "Yes" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          const url = String(input);
          return (
            url.endsWith("/api/v1/organisations/acme/scenarios/future/events/kickoff") &&
            init?.method === "DELETE"
          );
        })
      ).toBe(true);
    });
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /Kickoff/ })).not.toBeInTheDocument()
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Launch event/ })).toHaveClass(
        "entity-row--selected"
      )
    );
  });

  it("shows event load and mutation errors", async () => {
    mockSchattenApi({ eventsStatus: 500 });

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("link", { name: "Events" }));

    expect(await screen.findByText("Event API error")).toBeInTheDocument();
    expect(screen.getByText(/API request failed \(500\)/)).toBeInTheDocument();
  });

  it("shows event mutation errors", async () => {
    mockSchattenApi({ eventMutationStatus: 500 });

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("link", { name: "Events" }));
    await screen.findByRole("button", { name: /Kickoff/ });

    const createEventForm = screen.getByRole("form", { name: "Create event" });
    fireEvent.change(within(createEventForm).getByLabelText("Name"), {
      target: { value: "Blocked event" }
    });
    fireEvent.change(within(createEventForm).getByLabelText("Target date"), {
      target: { value: "2026-08-01" }
    });
    fireEvent.click(within(createEventForm).getByRole("button", { name: "Create event" }));

    expect(await screen.findByText("Action error")).toBeInTheDocument();
    expect(screen.getByText(/API request failed \(500\)/)).toBeInTheDocument();
  });
});
