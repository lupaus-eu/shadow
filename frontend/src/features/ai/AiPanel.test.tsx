import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAiChangeSets, fetchAiConnections } from "../../api/ai";
import AiPanel from "./AiPanel";
import type { AiPanelOptions } from "./AiPanel";

vi.mock("../../api/ai", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/ai")>()),
  fetchAiChangeSets: vi.fn(),
  fetchAiConnections: vi.fn()
}));

const fetchChangeSetsMock = vi.mocked(fetchAiChangeSets);
const fetchConnectionsMock = vi.mocked(fetchAiConnections);

function renderPanel(options: Partial<AiPanelOptions> = {}) {
  const onClose = vi.fn();
  render(
    <AiPanel
      id="metrics-ai-panel"
      orgId="acme"
      scenario={{ id: "future", name: "Future plan" }}
      options={{
        mcpEnabled: true,
        changeSetKey: null,
        onChangeSetKeyChange: vi.fn(),
        ...options
      }}
      unsavedMetricRows={0}
      onApplied={vi.fn()}
      onClose={onClose}
    />
  );
  return { onClose };
}

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(window.navigator, "clipboard", {
    configurable: true,
    value: { writeText }
  });
}

beforeEach(() => {
  vi.resetAllMocks();
  fetchChangeSetsMock.mockResolvedValue([]);
  fetchConnectionsMock.mockResolvedValue([]);
});

afterEach(() => {
  vi.restoreAllMocks();
  Reflect.deleteProperty(window.navigator, "clipboard");
});

describe("AiPanel", () => {
  it("opens on the change sets and switches to connections and connect", async () => {
    const { onClose } = renderPanel();

    const panel = screen.getByRole("complementary", { name: "AI" });
    expect(await within(panel).findByText("No change sets.")).toBeVisible();
    const sections = within(panel).getByRole("group", { name: "AI panel section" });
    expect(within(sections).getByRole("button", { name: "Change sets" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );

    fireEvent.click(within(sections).getByRole("button", { name: "Connections" }));
    expect(await screen.findByText("No connected AI clients.")).toBeVisible();

    fireEvent.click(within(sections).getByRole("button", { name: "Connect" }));
    expect(screen.getByRole("heading", { name: "Connect an AI client" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Close AI panel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows the MCP URLs with copy buttons and the Claude Code commands", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard(writeText);
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    const readUrl = `${window.location.origin}/api/mcp/read`;
    const writeUrl = `${window.location.origin}/api/mcp/write`;
    expect(screen.getByText(readUrl, { selector: "code" })).toBeVisible();
    expect(screen.getByText(writeUrl, { selector: "code" })).toBeVisible();
    expect(screen.getByText(/claude mcp add --transport http schatten-read/)).toHaveTextContent(
      `claude mcp add --transport http schatten-read ${readUrl}`
    );
    expect(screen.getByText(/custom connector/)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Copy write URL" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(writeUrl));
    expect(await screen.findByRole("button", { name: "Copy write URL" })).toHaveTextContent(
      "Copied"
    );
    expect(screen.getByRole("button", { name: "Copy read URL" })).toHaveTextContent("Copy");
  });

  it("explains a failed copy", async () => {
    stubClipboard(vi.fn().mockRejectedValue(new Error("Denied")));
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    fireEvent.click(screen.getByRole("button", { name: "Copy read URL" }));

    expect(await screen.findByText("Copying failed; select the URL and copy it.")).toBeVisible();
  });

  it("hides the Connect section when features.mcp is false", async () => {
    renderPanel({ mcpEnabled: false });

    expect(await screen.findByText("No change sets.")).toBeVisible();
    const sections = screen.getByRole("group", { name: "AI panel section" });
    expect(within(sections).queryByRole("button", { name: "Connect" })).not.toBeInTheDocument();
    expect(within(sections).getByRole("button", { name: "Connections" })).toBeVisible();
    expect(screen.queryByText(/api\/mcp\/read/)).not.toBeInTheDocument();
  });
});
