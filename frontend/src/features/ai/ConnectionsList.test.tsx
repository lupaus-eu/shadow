import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AiApiError, fetchAiConnections, revokeAiConnection } from "../../api/ai";
import type { AiConnectionDto } from "../../api/ai";
import { AuthContext } from "../../auth/AuthContext";
import type { AuthContextValue } from "../../auth/AuthContext";
import ConnectionsList from "./ConnectionsList";
import { formatAiTimestamp } from "./aiPresentation";

vi.mock("../../api/ai", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/ai")>()),
  fetchAiConnections: vi.fn(),
  revokeAiConnection: vi.fn()
}));

const fetchAiConnectionsMock = vi.mocked(fetchAiConnections);
const revokeAiConnectionMock = vi.mocked(revokeAiConnection);

const readConnection: AiConnectionDto = {
  grantKey: "grant-read",
  clientId: "client-id-read",
  clientName: "Claude",
  scope: "schatten.read",
  resource: "https://app.localhost/api/mcp/read",
  createdTime: "2026-10-01T08:00:00Z",
  lastUsedTime: "2026-10-27T09:30:00Z",
  expiresTime: "2026-10-31T08:00:00Z"
};

const writeConnection: AiConnectionDto = {
  grantKey: "grant-write",
  clientId: "client-id-write",
  clientName: "my-client_2",
  scope: "schatten.write",
  resource: "https://app.localhost/api/mcp/write",
  createdTime: "2026-10-02T08:00:00Z",
  lastUsedTime: null,
  expiresTime: "2026-11-01T08:00:00Z"
};

function renderWithMcpDisabled() {
  const auth: AuthContextValue = {
    status: "authenticated",
    user: { id: 7, name: "Ada Admin", email: "ada@example.local", role: "consultant" },
    features: { mcp: false },
    authError: "",
    login: vi.fn(),
    logout: vi.fn(async () => undefined),
    invalidateSession: vi.fn()
  };
  return render(
    <AuthContext.Provider value={auth}>
      <ConnectionsList />
    </AuthContext.Provider>
  );
}

beforeEach(() => {
  vi.resetAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ConnectionsList", () => {
  it("lists each grant with its client id, scope and times", async () => {
    fetchAiConnectionsMock.mockResolvedValue([readConnection, writeConnection]);

    render(<ConnectionsList />);

    expect(screen.getByText("Loading connections...")).toBeVisible();
    const readRow = await screen.findByRole("listitem", { name: /^Claude/ });
    expect(within(readRow).getByText("client-id-read")).toBeVisible();
    expect(within(readRow).getByText("schatten.read")).toBeVisible();
    expect(within(readRow).getByText("Read")).toBeVisible();
    expect(within(readRow).getByText(formatAiTimestamp(readConnection.createdTime))).toBeVisible();
    expect(
      within(readRow).getByText(formatAiTimestamp(readConnection.lastUsedTime ?? ""))
    ).toBeVisible();
    expect(within(readRow).getByText(formatAiTimestamp(readConnection.expiresTime))).toBeVisible();

    const writeRow = await screen.findByRole("listitem", { name: /^my-client_2/ });
    expect(within(writeRow).getByText("client-id-write")).toBeVisible();
    expect(within(writeRow).getByText("schatten.write")).toBeVisible();
    expect(within(writeRow).getByText("Never")).toBeVisible();
  });

  it("renders the client name isolated and labelled as self-declared", async () => {
    fetchAiConnectionsMock.mockResolvedValue([readConnection]);

    render(<ConnectionsList />);

    const clientName = await screen.findByText("Claude");
    expect(clientName.tagName).toBe("BDI");
    expect(clientName.parentElement).toHaveTextContent("Claude(self-declared by the client)");
  });

  it("confirms before revoking a connection by its grant key", async () => {
    fetchAiConnectionsMock.mockResolvedValue([readConnection, writeConnection]);
    revokeAiConnectionMock.mockResolvedValue();

    render(<ConnectionsList />);
    const writeRow = await screen.findByRole("listitem", { name: /^my-client_2/ });
    fireEvent.click(within(writeRow).getByRole("button", { name: "Revoke" }));

    expect(within(writeRow).getByRole("alertdialog")).toHaveTextContent(
      "Revoke this connection? The AI client loses access immediately"
    );
    fireEvent.click(within(writeRow).getByRole("button", { name: "Cancel" }));
    expect(revokeAiConnectionMock).not.toHaveBeenCalled();
    expect(within(writeRow).queryByRole("alertdialog")).not.toBeInTheDocument();

    fireEvent.click(within(writeRow).getByRole("button", { name: "Revoke" }));
    fireEvent.click(within(writeRow).getByRole("button", { name: "Confirm revoke" }));

    await waitFor(() => expect(revokeAiConnectionMock).toHaveBeenCalledWith("grant-write"));
    await waitFor(() =>
      expect(screen.queryByRole("listitem", { name: /^my-client_2/ })).not.toBeInTheDocument()
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "The connection was revoked. The AI client can no longer use it."
    );
    expect(screen.getByRole("listitem", { name: /^Claude/ })).toBeVisible();
    expect(revokeAiConnectionMock).toHaveBeenCalledTimes(1);
  });

  it("removes a connection that was already revoked or expired", async () => {
    fetchAiConnectionsMock.mockResolvedValue([readConnection]);
    revokeAiConnectionMock.mockRejectedValue(
      new AiApiError(404, "CONNECTION_NOT_FOUND", "Connection not found")
    );

    render(<ConnectionsList />);
    const row = await screen.findByRole("listitem", { name: /^Claude/ });
    fireEvent.click(within(row).getByRole("button", { name: "Revoke" }));
    fireEvent.click(within(row).getByRole("button", { name: "Confirm revoke" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "The connection had already been revoked or had expired."
    );
    expect(await screen.findByText("No connected AI clients.")).toBeVisible();
  });

  it("keeps the connection and reports a revocation failure", async () => {
    fetchAiConnectionsMock.mockResolvedValue([readConnection]);
    revokeAiConnectionMock.mockRejectedValue(new Error("Revocation failed (500)."));

    render(<ConnectionsList />);
    const row = await screen.findByRole("listitem", { name: /^Claude/ });
    fireEvent.click(within(row).getByRole("button", { name: "Revoke" }));
    fireEvent.click(within(row).getByRole("button", { name: "Confirm revoke" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Revocation failed (500).");
    expect(await within(row).findByRole("button", { name: "Confirm revoke" })).toBeEnabled();
    expect(screen.getByRole("listitem", { name: /^Claude/ })).toBeVisible();
  });

  it("shows load failure, empty and retry states", async () => {
    fetchAiConnectionsMock
      .mockRejectedValueOnce(new Error("Connections unavailable."))
      .mockResolvedValueOnce([]);

    render(<ConnectionsList />);

    expect(await screen.findByText("Connections unavailable.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("No connected AI clients.")).toBeVisible();
    expect(fetchAiConnectionsMock).toHaveBeenCalledTimes(2);
  });

  it("keeps listing and revoking connections when MCP is disabled", async () => {
    fetchAiConnectionsMock.mockResolvedValue([readConnection]);
    revokeAiConnectionMock.mockResolvedValue();

    renderWithMcpDisabled();
    const row = await screen.findByRole("listitem", { name: /^Claude/ });
    fireEvent.click(within(row).getByRole("button", { name: "Revoke" }));
    fireEvent.click(within(row).getByRole("button", { name: "Confirm revoke" }));

    await waitFor(() => expect(revokeAiConnectionMock).toHaveBeenCalledWith("grant-read"));
    expect(await screen.findByText("No connected AI clients.")).toBeVisible();
  });

  it("aborts the active list request when unmounted", () => {
    let capturedSignal: AbortSignal | undefined;
    fetchAiConnectionsMock.mockImplementation((signal) => {
      capturedSignal = signal;
      return new Promise<AiConnectionDto[]>(() => undefined);
    });

    const view = render(<ConnectionsList />);
    expect(capturedSignal?.aborted).toBe(false);
    view.unmount();
    expect(capturedSignal?.aborted).toBe(true);
  });
});
