import {
  fireEvent,
  render,
  screen,
  waitFor,
  within
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

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
}) {
  let cleanedFutureStates = false;
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

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/events") &&
      method === "GET"
    ) {
      if (options?.eventsStatus) {
        return Promise.resolve(
          jsonResponse(
            { detail: "Events unavailable." },
            { status: options.eventsStatus }
          )
        );
      }
      return Promise.resolve(jsonResponse(futureEvents));
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/reality/events") &&
      method === "GET"
    ) {
      return Promise.resolve(jsonResponse([]));
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/events") &&
      method === "POST"
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
      const created = { id: "new-event", ...payload };
      futureEvents = [...futureEvents, created];
      return Promise.resolve(jsonResponse(created, { status: 201 }));
    }

    if (
      url.endsWith(
        "/api/v1/organisations/acme/scenarios/future/events/kickoff"
      ) &&
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
      futureEvents = futureEvents.map((event) =>
        event.id === "kickoff" ? updated : event
      );
      return Promise.resolve(jsonResponse(updated));
    }

    if (
      url.endsWith(
        "/api/v1/organisations/acme/scenarios/future/events/kickoff"
      ) &&
      method === "DELETE"
    ) {
      futureEvents = futureEvents.filter((event) => event.id !== "kickoff");
      return Promise.resolve(noContentResponse());
    }

    if (url.endsWith("/api/v1/organisations/acme/scenarios")) {
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

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future") &&
      method === "DELETE"
    ) {
      return Promise.resolve(noContentResponse());
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future") &&
      method === "PATCH"
    ) {
      return Promise.resolve(
        jsonResponse({
          scenario_id: "future",
          scenario_name: "Future plan updated",
          scenario_description: "Updated",
          is_protected: false
        })
      );
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/reality") &&
      method === "PATCH"
    ) {
      return Promise.resolve(
        jsonResponse({
          scenario_id: "reality",
          scenario_name: "Reality updated",
          scenario_description: "Updated current baseline",
          is_protected: true
        })
      );
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/reality") &&
      method === "GET"
    ) {
      return Promise.resolve(
        jsonResponse({
          scenario_id: "reality",
          scenario_name: "Reality",
          scenario_description: "Current baseline",
          is_protected: true
        })
      );
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future") &&
      method === "GET"
    ) {
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
      url.endsWith(
        "/api/v1/organisations/acme/scenarios/future/org-states/clean"
      ) &&
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
          jsonResponse(
            { detail: "Clean states failed." },
            { status: options.cleanStatus }
          )
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
      url.endsWith(
        "/api/v1/organisations/acme/scenarios/future/org-states/draft"
      ) &&
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
      url.endsWith(
        "/api/v1/organisations/acme/scenarios/future/org-states/draft"
      ) &&
      method === "DELETE"
    ) {
      return Promise.resolve(noContentResponse());
    }

    if (
      url.endsWith(
        "/api/v1/organisations/acme/scenarios/future/org-states/launch"
      ) &&
      method === "DELETE"
    ) {
      return Promise.resolve(noContentResponse());
    }

    if (
      url.endsWith(
        "/api/v1/organisations/acme/scenarios/reality/org-states"
      )
    ) {
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
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders organisation selection and creation controls on the home page", async () => {
    mockSchattenApi();

    renderAt("/");

    expect(
      screen.getByRole("heading", { name: "Select organisation" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Open organisation" })
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Create organisation" })
    ).toBeDisabled();

    expect(await screen.findByRole("option", { name: "Acme" })).toBeVisible();
    expect(screen.getByLabelText("Create new organisation")).toBeVisible();
  });

  it("creates an organisation through the backend API and selects it", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/");

    const nameInput = screen.getByLabelText("Create new organisation");
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

    fireEvent.change(screen.getByLabelText("Create new organisation"), {
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

    expect(
      await screen.findByRole("heading", { name: "Scenarios", level: 1 })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Scenarios" })).toHaveClass(
      "tab-link--active"
    );
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
          url.endsWith(
            "/api/v1/organisations/acme/scenarios/future/org-states"
          ) && (init?.method ?? "GET") === "GET"
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
    expect(
      screen.getByTitle("Scenario: Future refreshed")
    ).toBeInTheDocument();
    expect(
      screen.getByTitle("Org state: Draft state (2026-06-01)")
    ).toBeInTheDocument();
  });

  it("renders tab URLs and disables Structure and Events before selection", () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    const expectedLinks = [
      ["Scenarios", "/schatten/acme/org-states"],
      ["Metrics", "/schatten/acme/metrics"],
      ["Summary", "/schatten/acme/summary"],
      ["Analysis", "/schatten/acme/analysis"]
    ] as const;

    for (const [label, href] of expectedLinks) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute(
        "href",
        href
      );
    }
    expect(screen.queryByRole("link", { name: "Structure" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Events" })).not.toBeInTheDocument();
    expect(screen.getByText("Structure")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Events")).toHaveAttribute("aria-disabled", "true");
  });

  it("marks the active tab from the current URL", () => {
    renderAt("/schatten/acme/metrics");

    expect(screen.getByRole("link", { name: "Metrics" })).toHaveClass(
      "tab-link--active"
    );
    expect(screen.getByRole("link", { name: "Scenarios" })).not.toHaveClass(
      "tab-link--active"
    );
  });

  it("shows the organisation, scenario, and org state indicators", async () => {
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
    expect(
      screen.getByText("Protected scenario cannot be deleted.")
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Delete scenario" })
    ).not.toBeInTheDocument();

    const selectedScenarioPanel = screen.getByRole("region", {
      name: "Selected scenario"
    });
    const nameInput = within(selectedScenarioPanel).getByLabelText("Name");
    const descriptionInput =
      within(selectedScenarioPanel).getByLabelText("Description");
    const saveButton = within(selectedScenarioPanel).getByRole("button", {
      name: "Save scenario"
    });

    expect(nameInput).toHaveValue("Reality");
    expect(
      selectedScenarioPanel.querySelector("label[for='scenario-edit-name']")
    ).toHaveClass("form-label--required");
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
            url.endsWith("/api/v1/organisations/acme/scenarios/reality") &&
            init?.method === "PATCH"
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
    expect(
      screen.getByRole("button", { name: "Clean states" })
    ).not.toBeDisabled();
  });

  it("confirms before cleaning states and refreshes the selected scenario states", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });

    fireEvent.click(screen.getByRole("button", { name: "Clean states" }));
    expect(
      screen.getByRole("button", { name: "Confirm clean states" })
    ).toBeVisible();
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        return (
          String(input).endsWith(
            "/api/v1/organisations/acme/scenarios/future/org-states/clean"
          ) && init?.method === "POST"
        );
      })
    ).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Confirm clean states" }));

    expect(await screen.findByText("Cleaned 1 state(s).")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        return (
          String(input).endsWith(
            "/api/v1/organisations/acme/scenarios/future/org-states/clean"
          ) && init?.method === "POST"
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
    expect(
      screen.queryByRole("button", { name: /Draft state/ })
    ).not.toBeInTheDocument();
    expect(
      screen.getByTitle("Org state: Planned launch (2026-07-01)")
    ).toBeInTheDocument();
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
    const descriptionInput =
      within(selectedScenarioPanel).getByLabelText("Description");
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
    expect(
      screen.getByTitle("Org state: Today (2026-06-23)")
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Structure" })).toHaveAttribute(
      "href",
      "/schatten/acme/graph"
    );
    expect(screen.getByRole("link", { name: "Events" })).toHaveAttribute(
      "href",
      "/schatten/acme/events"
    );
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
    const selectedScenarioGroup = selectedScenarioButton.closest(
      ".scenario-list-item"
    );

    expect(selectedScenarioGroup).toHaveClass("scenario-list-item--selected");
    expect(selectedScenarioButton).toHaveClass("entity-row--selected");
    expect(within(scenarioList).getByText("STATES")).toBeInTheDocument();
    expect(within(scenarioList).queryByText("A possible future")).not.toBeInTheDocument();
    expect(within(scenarioList).queryByText("Draft")).not.toBeInTheDocument();
    expect(
      within(scenarioList).getByRole("button", { name: /Draft state/ })
    ).toHaveClass("entity-row--selected");
  });

  it("chooses a fork source state without changing the active org-state view", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });

    expect(
      screen.getByTitle("Org state: Draft state (2026-06-01)")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Selected scenario" })
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Source state"), {
      target: { value: "launch" }
    });
    const forkForm = screen.getByRole("form", { name: "Fork from existing" });
    fireEvent.change(within(forkForm).getByLabelText(/Name/), {
      target: { value: "" }
    });

    expect(
      screen.getByTitle("Org state: Draft state (2026-06-01)")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Selected scenario" })
    ).toBeInTheDocument();

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

  it("shows states under the selected scenario and auto-selects the first state", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });

    expect(screen.getByLabelText("Scenario list")).toContainElement(
      screen.getByLabelText("Org state list")
    );

    expect(screen.getByTitle("Scenario: Future plan")).toBeInTheDocument();
    expect(
      screen.getByTitle("Org state: Draft state (2026-06-01)")
    ).toBeInTheDocument();
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
    expect(
      within(stateList).getByRole("button", { name: /Today/ })
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Draft state/ })
    ).not.toBeInTheDocument();
  });

  it("preserves the selected org state when returning to Scenarios", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("button", { name: /Planned launch/ }));

    expect(
      screen.getByTitle("Org state: Planned launch (2026-07-01)")
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Events" }));
    expect(
      await screen.findByRole("heading", { name: "Events", level: 1 })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Scenarios" }));

    await waitFor(() => {
      expect(
        screen.getByTitle("Org state: Planned launch (2026-07-01)")
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Planned launch/ })
      ).toHaveClass("entity-row--selected");
    });
  });

  it("edits the selected org state immediately and saves only after changes", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("button", { name: "State" }));

    expect(
      screen.queryByRole("button", { name: "Edit state" })
    ).not.toBeInTheDocument();
    expect(screen.queryByText("State ID")).not.toBeInTheDocument();

    const selectedStatePanel = screen.getByRole("region", {
      name: "Draft state"
    });
    const nameInput = within(selectedStatePanel).getByLabelText("Name");
    const descriptionInput =
      within(selectedStatePanel).getByLabelText("Description");
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
            url.endsWith(
              "/api/v1/organisations/acme/scenarios/future/org-states/draft"
            ) &&
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
    const confirmInput =
      within(selectedStatePanel).getByPlaceholderText("Type DELETE to confirm");
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
            url.endsWith(
              "/api/v1/organisations/acme/scenarios/future/org-states/draft"
            ) && init?.method === "DELETE"
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
    expect(within(createStatePanel).getByLabelText("Target date")).toHaveValue(
      todayDateValue()
    );
    fireEvent.change(within(createStatePanel).getByLabelText("Name"), {
      target: { value: "Duplicate date state" }
    });
    fireEvent.change(within(createStatePanel).getByLabelText("Target date"), {
      target: { value: "2026-07-01" }
    });
    fireEvent.click(
      within(createStatePanel).getByRole("button", { name: "Create state" })
    );

    expect(
      await screen.findByText("Target date must be unique within the scenario.")
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        const url = String(input);
        return (
          url.endsWith(
            "/api/v1/organisations/acme/scenarios/future/org-states"
          ) && init?.method === "POST"
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
            url.endsWith("/api/v1/organisations/acme/scenarios/future") &&
            init?.method === "DELETE"
          );
        })
      ).toBe(true);
    });
  });

  it("keeps Events gated on direct route until scenario and state are selected", () => {
    mockSchattenApi();

    renderAt("/schatten/acme/events");

    expect(
      screen.getByText("Select a scenario and org state in Scenarios to activate this tab.")
    ).toBeInTheDocument();
  });

  it("loads events for the selected scenario and auto-selects the first event", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("link", { name: "Events" }));

    expect(
      await screen.findByRole("heading", { name: "Events", level: 1 })
    ).toBeInTheDocument();
    expect(await screen.findByText("2 event(s)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Kickoff/ })).toHaveClass(
      "entity-row--selected"
    );
    expect(screen.getByRole("button", { name: /Kickoff/ })).toHaveTextContent(
      /Past\s*2026-06-15\s*Kickoff\s*Internal kickoff/
    );
    expect(
      screen.getByRole("button", { name: /Launch event/ })
    ).toHaveTextContent("No details");
    expect(
      screen.getByRole("heading", { name: "Kickoff" })
    ).toBeInTheDocument();
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
    expect(
      screen.getByRole("heading", { name: "No event selected" })
    ).toBeInTheDocument();
  });

  it("creates an event and refreshes the event list selection", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("link", { name: "Events" }));
    await screen.findByRole("button", { name: /Kickoff/ });

    const createEventForm = screen.getByRole("form", { name: "Create event" });
    expect(
      createEventForm.querySelector("label[for='event-create-name']")
    ).toHaveClass("form-label--required");
    expect(within(createEventForm).getByLabelText("Target date")).toHaveValue(
      todayDateValue()
    );
    fireEvent.change(within(createEventForm).getByLabelText("Name"), {
      target: { value: "Board review" }
    });
    fireEvent.change(within(createEventForm).getByLabelText("Event details"), {
      target: { value: "Review growth plan" }
    });
    fireEvent.click(
      within(createEventForm).getByRole("button", { name: "Create event" })
    );

    const createdEventRow = await screen.findByRole("button", {
      name: /Board review/
    });
    expect(createdEventRow).toHaveClass("entity-row--selected");
    expect(createdEventRow).toHaveTextContent(
      new RegExp(
        `Upcoming\\s*${todayDateValue()}\\s*Board review\\s*Review growth plan`
      )
    );
    expect(
      screen.getByRole("heading", { name: "Board review" })
    ).toBeInTheDocument();
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
            url.endsWith(
              "/api/v1/organisations/acme/scenarios/future/events/kickoff"
            ) &&
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

    fireEvent.click(within(selectedEventPanel).getByRole("button", {
      name: "Delete event"
    }));
    expect(
      within(selectedEventPanel).getByText(
        "Are you sure you want to delete the selected event?"
      )
    ).toBeInTheDocument();

    fireEvent.click(within(selectedEventPanel).getByRole("button", { name: "No" }));
    expect(
      within(selectedEventPanel).queryByText(
        "Are you sure you want to delete the selected event?"
      )
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        const url = String(input);
        return (
          url.endsWith(
            "/api/v1/organisations/acme/scenarios/future/events/kickoff"
          ) && init?.method === "DELETE"
        );
      })
    ).toBe(false);

    fireEvent.click(within(selectedEventPanel).getByRole("button", {
      name: "Delete event"
    }));
    fireEvent.click(within(selectedEventPanel).getByRole("button", { name: "Yes" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input, init]) => {
          const url = String(input);
          return (
            url.endsWith(
              "/api/v1/organisations/acme/scenarios/future/events/kickoff"
            ) && init?.method === "DELETE"
          );
        })
      ).toBe(true);
    });
    expect(
      screen.queryByRole("button", { name: /Kickoff/ })
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Launch event/ })).toHaveClass(
      "entity-row--selected"
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
    fireEvent.click(
      within(createEventForm).getByRole("button", { name: "Create event" })
    );

    expect(await screen.findByText("Action error")).toBeInTheDocument();
    expect(screen.getByText(/API request failed \(500\)/)).toBeInTheDocument();
  });
});
