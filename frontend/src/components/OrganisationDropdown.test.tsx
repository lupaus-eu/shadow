import { useState } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useParams } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OrganisationDropdown from "./OrganisationDropdown";
import { useWorkspaceSelection } from "../workspace/WorkspaceSelectionContext";
import WorkspaceSelectionProvider from "../workspace/WorkspaceSelectionProvider";

type ApiOptions = {
  organisations?: Array<{ id: string; name: string }>;
  renameStatus?: number;
  createStatus?: number;
  deleteStatus?: number;
  createResponse?: Promise<Response>;
  listResponse?: Promise<Response>;
  listStatus?: number;
};

function jsonResponse(payload: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init
  });
}

function deferredResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

function mockOrganisationApi(options: ApiOptions = {}) {
  let organisations = options.organisations ?? [
    { id: "beta", name: "Beta" },
    { id: "acme", name: "Acme" }
  ];

  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";

    if (url.endsWith("/api/v1/organisations") && method === "GET") {
      if (options.listResponse) return options.listResponse;
      if (options.listStatus) {
        return Promise.resolve(
          jsonResponse({ detail: "Organisations are unavailable." }, { status: options.listStatus })
        );
      }
      return Promise.resolve(jsonResponse(organisations));
    }

    if (url.endsWith("/api/v1/organisations/acme") && method === "PATCH") {
      if (options.renameStatus) {
        return Promise.resolve(
          jsonResponse(
            { detail: "An active organisation with this name already exists." },
            { status: options.renameStatus }
          )
        );
      }
      const name = JSON.parse(String(init?.body)).name as string;
      const updated = { id: "acme", name };
      organisations = organisations.map((item) => (item.id === "acme" ? updated : item));
      return Promise.resolve(jsonResponse(updated));
    }

    if (url.endsWith("/api/v1/organisations/acme") && method === "DELETE") {
      if (options.deleteStatus) {
        return Promise.resolve(
          jsonResponse(
            { detail: "Organisation could not be deleted." },
            { status: options.deleteStatus }
          )
        );
      }
      organisations = organisations.filter((item) => item.id !== "acme");
      return Promise.resolve(new Response(null, { status: 204 }));
    }

    if (url.endsWith("/api/v1/organisations") && method === "POST") {
      if (options.createResponse) return options.createResponse;
      if (options.createStatus) {
        return Promise.resolve(
          jsonResponse(
            { detail: "An active organisation with this name already exists." },
            { status: options.createStatus }
          )
        );
      }
      const name = JSON.parse(String(init?.body)).name as string;
      const created = { id: "new-org", name };
      organisations = [...organisations, created];
      return Promise.resolve(jsonResponse(created, { status: 201 }));
    }

    return Promise.resolve(jsonResponse({}, { status: 404 }));
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function ContextProbe() {
  const { selectedScenario, setSelectedScenario } = useWorkspaceSelection();
  return (
    <>
      <button type="button" onClick={() => setSelectedScenario({ id: "future", name: "Future" })}>
        Select scenario
      </button>
      <span data-testid="scenario-name">{selectedScenario?.name ?? "None"}</span>
    </>
  );
}

function RoutedDropdown() {
  const { orgId = "" } = useParams<{ orgId: string }>();
  const location = useLocation();
  const [name, setName] = useState(orgId);

  return (
    <WorkspaceSelectionProvider key={orgId}>
      <OrganisationDropdown
        orgId={orgId}
        organisationName={name}
        onOrganisationNameChange={setName}
      />
      <ContextProbe />
      <span data-testid="location">{location.pathname}</span>
    </WorkspaceSelectionProvider>
  );
}

function renderDropdown(path = "/schatten/acme/summary") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/schatten/:orgId/:tab" element={<RoutedDropdown />} />
        <Route path="/" element={<span>Home page</span>} />
      </Routes>
    </MemoryRouter>
  );
}

async function openDropdown(name = "Acme") {
  const trigger = await screen.findByRole("button", {
    name: `Organisation: ${name}`
  });
  fireEvent.click(trigger);
  return screen.getByRole("dialog", { name: "Organisation selector" });
}

describe("OrganisationDropdown", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sorts organisations, marks the current item, switches route, and resets context", async () => {
    mockOrganisationApi();
    renderDropdown();

    fireEvent.click(screen.getByRole("button", { name: "Select scenario" }));
    expect(screen.getByTestId("scenario-name")).toHaveTextContent("Future");

    const dropdown = await openDropdown();
    const options = within(dropdown).getAllByRole("button", {
      name: /^(Acme|Beta)/
    });
    expect(options.map((option) => option.textContent)).toEqual(["AcmeCurrent", "Beta"]);
    expect(options[0]).toHaveAttribute("aria-current", "true");

    fireEvent.click(within(dropdown).getByRole("button", { name: "Beta" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/schatten/beta/summary");
    expect(screen.getByTestId("scenario-name")).toHaveTextContent("None");
    expect(await screen.findByRole("button", { name: "Organisation: Beta" })).toBeInTheDocument();
  });

  it("shows loading, empty-list, and list-error states without hiding creation", async () => {
    const pending = deferredResponse();
    mockOrganisationApi({ listResponse: pending.promise });
    renderDropdown();
    const dropdown = await openDropdown("acme");
    expect(within(dropdown).getByText("Loading organisations...")).toBeVisible();

    pending.resolve(jsonResponse([]));
    expect(await within(dropdown).findByText("No organisations available.")).toBeVisible();
    expect(within(dropdown).getByRole("button", { name: "Add organisation" })).toBeEnabled();
  });

  it("reports organisation list failures while retaining the route fallback", async () => {
    mockOrganisationApi({ listStatus: 503 });
    renderDropdown();
    const dropdown = await openDropdown("acme");

    expect(await within(dropdown).findByText(/Organisations are unavailable/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Organisation: acme" })).toBeInTheDocument();
  });

  it("closes on Escape and outside interaction", async () => {
    mockOrganisationApi();
    renderDropdown();

    await openDropdown();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Organisation selector" })).not.toBeInTheDocument();

    const trigger = screen.getByRole("button", { name: "Organisation: Acme" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    expect(screen.getByRole("button", { name: "Acme Current" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });

    await openDropdown();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("dialog", { name: "Organisation selector" })).not.toBeInTheDocument();
  });

  it("renames the current organisation and synchronises display state", async () => {
    const fetchMock = mockOrganisationApi();
    renderDropdown();
    const dropdown = await openDropdown();

    fireEvent.click(within(dropdown).getByRole("button", { name: "Rename organisation" }));
    const input = within(dropdown).getByLabelText("Organisation name");
    const saveButton = within(dropdown).getByRole("button", {
      name: "Save name"
    });
    expect(input).toHaveFocus();
    expect(saveButton).toBeDisabled();

    fireEvent.change(input, { target: { value: "   " } });
    expect(saveButton).toBeDisabled();
    fireEvent.change(input, { target: { value: "Acme Updated" } });
    fireEvent.click(saveButton);

    expect(
      await screen.findByRole("button", {
        name: "Organisation: Acme Updated"
      })
    ).toBeInTheDocument();
    expect(sessionStorage.getItem("schatten:organisationName:acme")).toBe("Acme Updated");
    expect(
      fetchMock.mock.calls.some(
        ([inputValue, init]) =>
          String(inputValue).endsWith("/api/v1/organisations/acme") &&
          init?.method === "PATCH" &&
          init.body === JSON.stringify({ name: "Acme Updated" })
      )
    ).toBe(true);
  });

  it("keeps rename input open and reports duplicate-name errors", async () => {
    mockOrganisationApi({ renameStatus: 409 });
    renderDropdown();
    const dropdown = await openDropdown();
    fireEvent.click(within(dropdown).getByRole("button", { name: "Rename organisation" }));
    const input = within(dropdown).getByLabelText("Organisation name");
    fireEvent.change(input, { target: { value: "Beta" } });
    fireEvent.click(within(dropdown).getByRole("button", { name: "Save name" }));

    expect(
      await within(dropdown).findByText(/An active organisation with this name already exists/)
    ).toBeVisible();
    expect(input).toHaveValue("Beta");
  });

  it("requires exact DELETE and selects the first remaining organisation", async () => {
    mockOrganisationApi();
    sessionStorage.setItem("schatten:organisationName:acme", "Acme");
    renderDropdown();
    const dropdown = await openDropdown();
    fireEvent.click(within(dropdown).getByRole("button", { name: "Delete organisation" }));

    const input = within(dropdown).getByPlaceholderText("Type DELETE to confirm");
    const confirmation = within(dropdown).getByRole("alertdialog");
    const deleteButton = within(confirmation).getByRole("button", {
      name: "Delete organisation"
    });
    expect(input).toHaveFocus();
    expect(deleteButton).toBeDisabled();
    fireEvent.change(input, { target: { value: "delete" } });
    expect(deleteButton).toBeDisabled();
    fireEvent.change(input, { target: { value: "DELETE" } });
    expect(deleteButton).toBeEnabled();
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/schatten/beta/summary");
    });
    expect(sessionStorage.getItem("schatten:organisationName:acme")).toBeNull();
  });

  it("keeps failed deletion available with an error", async () => {
    mockOrganisationApi({ deleteStatus: 500 });
    renderDropdown();
    const dropdown = await openDropdown();
    fireEvent.click(within(dropdown).getByRole("button", { name: "Delete organisation" }));
    fireEvent.change(within(dropdown).getByPlaceholderText("Type DELETE to confirm"), {
      target: { value: "DELETE" }
    });
    fireEvent.click(
      within(within(dropdown).getByRole("alertdialog")).getByRole("button", {
        name: "Delete organisation"
      })
    );

    expect(await within(dropdown).findByText(/Organisation could not be deleted/)).toBeVisible();
    expect(within(dropdown).getByPlaceholderText("Type DELETE to confirm")).toHaveValue("DELETE");
  });

  it("returns home after deleting the final organisation", async () => {
    mockOrganisationApi({ organisations: [{ id: "acme", name: "Acme" }] });
    renderDropdown();
    const dropdown = await openDropdown();
    fireEvent.click(within(dropdown).getByRole("button", { name: "Delete organisation" }));
    fireEvent.change(within(dropdown).getByPlaceholderText("Type DELETE to confirm"), {
      target: { value: "DELETE" }
    });
    fireEvent.click(
      within(within(dropdown).getByRole("alertdialog")).getByRole("button", {
        name: "Delete organisation"
      })
    );

    expect(await screen.findByText("Home page")).toBeVisible();
  });

  it("creates, selects, and opens an organisation from the dropdown footer", async () => {
    const fetchMock = mockOrganisationApi();
    renderDropdown("/schatten/acme/users");
    const dropdown = await openDropdown();
    fireEvent.click(within(dropdown).getByRole("button", { name: "Add organisation" }));

    const input = within(dropdown).getByPlaceholderText("Organisation name");
    const createButton = within(dropdown).getByRole("button", {
      name: "Create organisation"
    });
    expect(input).toHaveFocus();
    expect(createButton).toBeDisabled();
    fireEvent.change(input, { target: { value: "New organisation" } });
    fireEvent.click(createButton);

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/schatten/new-org/users");
    });
    expect(
      fetchMock.mock.calls.some(
        ([inputValue, init]) =>
          String(inputValue).endsWith("/api/v1/organisations") &&
          init?.method === "POST" &&
          init.body === JSON.stringify({ name: "New organisation" })
      )
    ).toBe(true);
  });

  it("keeps failed creation input open and reports the backend error", async () => {
    mockOrganisationApi({ createStatus: 409 });
    renderDropdown();
    const dropdown = await openDropdown();
    fireEvent.click(within(dropdown).getByRole("button", { name: "Add organisation" }));
    const input = within(dropdown).getByPlaceholderText("Organisation name");
    fireEvent.change(input, { target: { value: "Beta" } });
    fireEvent.click(within(dropdown).getByRole("button", { name: "Create organisation" }));

    expect(
      await within(dropdown).findByText(/An active organisation with this name already exists/)
    ).toBeVisible();
    expect(input).toHaveValue("Beta");
  });

  it("locks controls and prevents repeat create submissions while pending", async () => {
    const pending = deferredResponse();
    const fetchMock = mockOrganisationApi({ createResponse: pending.promise });
    renderDropdown();
    const dropdown = await openDropdown();
    fireEvent.click(within(dropdown).getByRole("button", { name: "Add organisation" }));
    const input = within(dropdown).getByPlaceholderText("Organisation name");
    fireEvent.change(input, { target: { value: "Pending organisation" } });
    fireEvent.click(within(dropdown).getByRole("button", { name: "Create organisation" }));

    const pendingButton = within(dropdown).getByRole("button", {
      name: "Creating..."
    });
    expect(pendingButton).toBeDisabled();
    expect(input).toBeDisabled();
    expect(within(dropdown).getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Organisation: Acme" })).toBeDisabled();
    fireEvent.click(pendingButton);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);

    pending.resolve(jsonResponse({ id: "new-org", name: "Pending organisation" }, { status: 201 }));
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/schatten/new-org/summary");
    });
  });
});
