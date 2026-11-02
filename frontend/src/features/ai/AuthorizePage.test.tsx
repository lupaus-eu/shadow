import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AiApiError,
  approveConsentRequest,
  denyConsentRequest,
  fetchConsentRequest
} from "../../api/ai";
import type { ConsentDecisionDto, ConsentRequestDto } from "../../api/ai";
import { AuthContext } from "../../auth/AuthContext";
import type { AuthContextValue } from "../../auth/AuthContext";
import { navigateBrowser } from "../../auth/browserNavigation";
import AuthorizePage from "./AuthorizePage";

vi.mock("../../api/ai", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/ai")>()),
  fetchConsentRequest: vi.fn(),
  approveConsentRequest: vi.fn(),
  denyConsentRequest: vi.fn()
}));

vi.mock("../../auth/browserNavigation", () => ({
  navigateBrowser: vi.fn()
}));

const fetchConsentRequestMock = vi.mocked(fetchConsentRequest);
const approveConsentRequestMock = vi.mocked(approveConsentRequest);
const denyConsentRequestMock = vi.mocked(denyConsentRequest);
const navigateBrowserMock = vi.mocked(navigateBrowser);

const REQUEST_ID = "pending-request-id_1234567890";

const vendorConsent: ConsentRequestDto = {
  clientName: "Claude",
  clientNameSelfDeclared: true,
  redirectIsLoopback: false,
  redirectHost: "claude.ai",
  scope: "schatten.read",
  resource: "https://app.localhost/api/mcp/read",
  expiresTime: "2026-10-28T10:10:00Z"
};

const loopbackConsent: ConsentRequestDto = {
  ...vendorConsent,
  clientName: "Claude Code (CLI)",
  redirectIsLoopback: true,
  redirectHost: "127.0.0.1",
  scope: "schatten.write",
  resource: "https://app.localhost/api/mcp/write"
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

function renderPage(
  path = `/ai/authorize?request=${REQUEST_ID}`,
  options: { mcp: boolean; mcpChangeSetReview?: boolean } = { mcp: true }
) {
  const auth: AuthContextValue = {
    status: "authenticated",
    user: { id: 7, name: "Ada Admin", email: "ada@example.local", role: "admin" },
    features: { mcp: options.mcp, mcpChangeSetReview: options.mcpChangeSetReview ?? false },
    authError: "",
    login: vi.fn(),
    logout: vi.fn(async () => undefined),
    invalidateSession: vi.fn()
  };

  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={[path]}>
        <AuthorizePage />
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

beforeEach(() => {
  vi.resetAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AuthorizePage", () => {
  it("loads the pending request by the id in its own query string", async () => {
    fetchConsentRequestMock.mockResolvedValue(vendorConsent);

    renderPage();

    expect(screen.getByRole("heading", { name: "Loading authorization request..." })).toBeVisible();
    expect(await screen.findByRole("heading", { name: "Connect an AI client" })).toBeVisible();
    expect(fetchConsentRequestMock).toHaveBeenCalledWith(REQUEST_ID, expect.any(AbortSignal));
    expect(await screen.findByRole("button", { name: "Approve" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Deny" })).toBeEnabled();
    expect(screen.getByText("Ada Admin")).toBeVisible();
    expect(document.body).not.toHaveTextContent(REQUEST_ID);
  });

  it("renders the client name isolated and labelled as self-declared", async () => {
    fetchConsentRequestMock.mockResolvedValue(vendorConsent);

    renderPage();

    const clientName = await screen.findByText("Claude");
    expect(clientName.tagName).toBe("BDI");
    expect(clientName.parentElement).toHaveTextContent("Claude(self-declared by the client)");
  });

  it("shows the vendor host for an exact redirect and explains read access", async () => {
    fetchConsentRequestMock.mockResolvedValue(vendorConsent);

    renderPage();

    expect(await screen.findByText("claude.ai")).toBeVisible();
    expect(screen.queryByRole("note", { name: "Local program" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Read access" })).toBeVisible();
    expect(screen.getByText(/It cannot change anything\./)).toBeVisible();
    expect(
      screen.getByText(/Data that the AI client reads from Schatten is sent to your AI vendor\./)
    ).toBeVisible();
    expect(
      screen.getByText(/The connection lasts for a limited time \(30 days by default\)/)
    ).toBeVisible();
    expect(screen.queryByRole("heading", { name: /Write access/ })).not.toBeInTheDocument();
  });

  it("shows the loopback notice instead of the host and explains write access", async () => {
    fetchConsentRequestMock.mockResolvedValue(loopbackConsent);

    renderPage();

    const notice = await screen.findByRole("note", { name: "Local program" });
    expect(notice).toHaveTextContent("goes to a program on this computer");
    expect(within(notice).queryByRole("button")).not.toBeInTheDocument();
    expect(notice).toHaveTextContent("Local programs cannot be verified by name");
    expect(screen.getByText("A program on this computer")).toBeVisible();
    expect(document.body).not.toHaveTextContent("127.0.0.1");
    expect(screen.getByRole("heading", { name: "Write access: proposals only" })).toBeVisible();
    expect(
      screen.getByText(/nothing in Schatten changes until a person reviews and applies/)
    ).toBeVisible();
    expect(
      screen.getByText(/Data that the AI client reads from Schatten is sent to your AI vendor\./)
    ).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Read access" })).not.toBeInTheDocument();
  });

  it("explains that write access can apply and reject when MCP review is on", async () => {
    fetchConsentRequestMock.mockResolvedValue(loopbackConsent);

    renderPage(`/ai/authorize?request=${REQUEST_ID}`, { mcp: true, mcpChangeSetReview: true });

    expect(
      await screen.findByRole("heading", {
        name: "Write access: propose, apply and reject changes"
      })
    ).toBeVisible();
    expect(
      screen.getByText(/it can also apply or reject change sets awaiting review/)
    ).toBeVisible();
    expect(screen.getByText(/including change sets that other people proposed/)).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Write access: proposals only" })
    ).not.toBeInTheDocument();
  });

  it("approves and navigates to exactly the server-returned redirect URL", async () => {
    const redirectUrl =
      "http://127.0.0.1:33418/callback?code=Abc-_123&state=s%2F1&iss=https%3A%2F%2Fapp.localhost";
    const decision = deferred<ConsentDecisionDto>();
    fetchConsentRequestMock.mockResolvedValue(loopbackConsent);
    approveConsentRequestMock.mockReturnValue(decision.promise);

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(await screen.findByRole("button", { name: "Approving..." })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Deny" })).toBeDisabled();
    expect(approveConsentRequestMock).toHaveBeenCalledWith(REQUEST_ID);
    expect(denyConsentRequestMock).not.toHaveBeenCalled();

    await act(async () => decision.resolve({ redirectUrl }));

    await waitFor(() => expect(navigateBrowserMock).toHaveBeenCalledWith(redirectUrl));
    expect(navigateBrowserMock).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("heading", { name: "Access approved" })).toBeVisible();
  });

  it("denies and navigates to the server-returned access_denied redirect URL", async () => {
    const redirectUrl = "https://claude.ai/api/mcp/auth_callback?error=access_denied&iss=x";
    fetchConsentRequestMock.mockResolvedValue(vendorConsent);
    denyConsentRequestMock.mockResolvedValue({ redirectUrl });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Deny" }));

    await waitFor(() => expect(navigateBrowserMock).toHaveBeenCalledWith(redirectUrl));
    expect(denyConsentRequestMock).toHaveBeenCalledWith(REQUEST_ID);
    expect(approveConsentRequestMock).not.toHaveBeenCalled();
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeVisible();
  });

  it("shows the expired state for an expired request", async () => {
    fetchConsentRequestMock.mockRejectedValue(
      new AiApiError(410, "AUTHORIZATION_REQUEST_EXPIRED", "Authorization request expired")
    );

    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Authorization request expired" })
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("shows the decided state when the request was decided elsewhere", async () => {
    fetchConsentRequestMock.mockResolvedValue(vendorConsent);
    approveConsentRequestMock.mockRejectedValue(
      new AiApiError(409, "AUTHORIZATION_REQUEST_DECIDED", "Authorization request already decided")
    );

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(
      await screen.findByRole("heading", { name: "Authorization request already decided" })
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(navigateBrowserMock).not.toHaveBeenCalled();
  });

  it("shows the decided state for an already decided request on load", async () => {
    fetchConsentRequestMock.mockRejectedValue(
      new AiApiError(409, "AUTHORIZATION_REQUEST_DECIDED", "Authorization request already decided")
    );

    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Authorization request already decided" })
    ).toBeVisible();
  });

  it("shows the invalid state for an unknown request", async () => {
    fetchConsentRequestMock.mockRejectedValue(
      new AiApiError(404, "AUTHORIZATION_REQUEST_NOT_FOUND", "Authorization request not found")
    );

    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Authorization request not found" })
    ).toBeVisible();
  });

  it("shows the invalid state without calling the API when the request id is missing", async () => {
    renderPage("/ai/authorize");

    expect(
      await screen.findByRole("heading", { name: "Authorization request not found" })
    ).toBeVisible();
    expect(fetchConsentRequestMock).not.toHaveBeenCalled();
  });

  it("shows the not available state when MCP is disabled", async () => {
    renderPage(`/ai/authorize?request=${REQUEST_ID}`, { mcp: false });

    expect(
      await screen.findByRole("heading", { name: "AI connections are not available" })
    ).toBeVisible();
    expect(fetchConsentRequestMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("retries a failed load", async () => {
    fetchConsentRequestMock
      .mockRejectedValueOnce(new AiApiError(503, "", "Service unavailable."))
      .mockResolvedValueOnce(vendorConsent);

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("button", { name: "Approve" })).toBeEnabled();
    expect(fetchConsentRequestMock).toHaveBeenCalledTimes(2);
  });

  it("keeps the request decidable after a failed decision", async () => {
    fetchConsentRequestMock.mockResolvedValue(vendorConsent);
    approveConsentRequestMock.mockRejectedValue(new Error("Network unavailable."));

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Network unavailable.");
    expect(await screen.findByRole("button", { name: "Approve" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Deny" })).toBeEnabled();
    expect(navigateBrowserMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Dismiss Decision failed notice" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Network unavailable.");
  });

  it("aborts the consent request when unmounted", () => {
    let capturedSignal: AbortSignal | undefined;
    fetchConsentRequestMock.mockImplementation((_requestId, signal) => {
      capturedSignal = signal;
      return new Promise<ConsentRequestDto>(() => undefined);
    });

    const view = renderPage();
    expect(capturedSignal?.aborted).toBe(false);
    view.unmount();
    expect(capturedSignal?.aborted).toBe(true);
  });
});
