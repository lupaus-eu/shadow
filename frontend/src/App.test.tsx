import { render, screen, waitFor } from "@testing-library/react";
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

function mockOrganisationsApi() {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";

    if (url.endsWith("/api/v1/organisations") && method === "POST") {
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
    mockOrganisationsApi();

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

  it("redirects an organisation workspace URL to the default Scenarios tab", async () => {
    renderAt("/schatten/acme");

    expect(
      await screen.findByRole("heading", { name: "Scenarios" })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Scenarios" })).toHaveClass(
      "tab-link--active"
    );
  });

  it("renders all workspace tabs with the required tab signatures", () => {
    renderAt("/schatten/acme/org-states");

    const expectedLinks = [
      ["Scenarios", "/schatten/acme/org-states"],
      ["Structure", "/schatten/acme/graph"],
      ["Events", "/schatten/acme/events"],
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
});
