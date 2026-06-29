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

function mockSchattenApi(options?: { duplicateCreate?: boolean }) {
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
      url.endsWith(
        "/api/v1/organisations/acme/scenarios/future/org-states/synchronise-graph-dates"
      )
    ) {
      return Promise.resolve(
        jsonResponse([
          {
            org_state_id: "synced",
            org_state_name: "Synced state",
            org_state_description: "From graph changes",
            target_date: "2026-08-01"
          }
        ])
      );
    }

    if (
      url.endsWith("/api/v1/organisations/acme/scenarios/future/org-states") &&
      method === "GET"
    ) {
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
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([input]) =>
          String(input).endsWith("/api/v1/organisations/acme/scenarios")
        )
      ).toHaveLength(2);
    });
  });

  it("synchronises the selected scenario states from the refresh control", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Draft state/ });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await screen.findByRole("button", { name: /Synced state/ });
    expect(
      fetchMock.mock.calls.some(([input, init]) => {
        const url = String(input);
        return (
          url.endsWith(
            "/api/v1/organisations/acme/scenarios/future/org-states/synchronise-graph-dates"
          ) && (init?.method ?? "GET") === "POST"
        );
      })
    ).toBe(true);
    expect(
      screen.getByTitle("Org state: Synced state (2026-08-01)")
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

  it("shows protected scenarios and blocks protected edit and delete actions", async () => {
    mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Reality/ }));

    expect(screen.getAllByText("Protected")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Save scenario" })).toBeDisabled();
    expect(
      screen.getByText("Protected scenario cannot be deleted.")
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Delete scenario" })
    ).not.toBeInTheDocument();
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

  it("blocks duplicate org-state target dates before submitting", async () => {
    const fetchMock = mockSchattenApi();

    renderAt("/schatten/acme/org-states");

    fireEvent.click(await screen.findByRole("button", { name: /Future plan/ }));
    await screen.findByRole("button", { name: /Planned launch/ });
    fireEvent.click(screen.getByRole("button", { name: "State" }));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Duplicate date state" }
    });
    fireEvent.change(screen.getByLabelText("Target date"), {
      target: { value: "2026-07-01" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Create state" }));

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
});
