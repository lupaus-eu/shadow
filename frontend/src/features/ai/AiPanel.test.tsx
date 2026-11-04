import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
        mcpChangeSetReview: false,
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

  it("describes the one connection by whether MCP change-set review is on", () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(
      screen.getByText(/It reads Schatten and proposes changes through one connection/)
    ).toBeVisible();
    expect(
      screen.getByText(/nothing changes until a person applies the change set here/)
    ).toBeVisible();
    expect(screen.queryByText(/apply or reject a change set/)).not.toBeInTheDocument();
    cleanup();

    renderPanel({ mcpChangeSetReview: true });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(
      screen.getByText(/It reads Schatten and proposes changes through one connection/)
    ).toBeVisible();
    expect(
      screen.getByText(/the client can apply or reject a change set awaiting review/)
    ).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Copy URL" })).toHaveLength(1);
  });

  it("shows the one MCP URL with a copy button and the Claude Code command", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard(writeText);
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    const url = `${window.location.origin}/api/mcp`;
    expect(screen.getByText(url, { selector: "code" })).toBeVisible();
    expect(screen.getByText("MCP server URL")).toBeVisible();
    expect(screen.queryByText(/api\/mcp\/(read|write)/)).not.toBeInTheDocument();
    expect(screen.getByText(/claude mcp add --transport http/)).toHaveTextContent(
      `claude mcp add --transport http schatten ${url}`
    );
    expect(screen.getByText(/custom connector/)).toBeVisible();
    expect(screen.getByText("Paste the URL and connect.")).toBeVisible();
    expect(screen.getAllByRole("button", { name: /URL$/ })).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Copy URL" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(url));
    expect(await screen.findByRole("button", { name: "Copy URL" })).toHaveTextContent("Copied");
  });

  it("explains a failed copy", async () => {
    stubClipboard(vi.fn().mockRejectedValue(new Error("Denied")));
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    fireEvent.click(screen.getByRole("button", { name: "Copy URL" }));

    expect(await screen.findByText("Copying failed; select the URL and copy it.")).toBeVisible();
  });

  it("shows the Claude Code plugin install commands with copy buttons", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard(writeText);
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(screen.getByText("/plugin marketplace add reflector-oy/schatten")).toBeVisible();
    expect(screen.getByText("/plugin install schatten@schatten")).toBeVisible();
    expect(
      screen.getByText(/The Schatten plugin adds the Schatten server and skills\./)
    ).toBeVisible();
    // The plugin's server is the production one; this origin is not.
    expect(
      screen.getByText(/The plugin connects to https:\/\/schatten\.lupaus\.eu/)
    ).toHaveTextContent("also add the server below; the plugin's skills apply to it too.");
    expect(screen.getByText("Or add only the server:")).toBeVisible();
    expect(
      screen.getByText(/Whether you installed the plugin or added the server,/)
    ).toHaveTextContent("select the Schatten server and authenticate");

    fireEvent.click(screen.getByRole("button", { name: "Copy install command" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith("/plugin install schatten@schatten")
    );
    expect(await screen.findByRole("button", { name: "Copy install command" })).toHaveTextContent(
      "Copied"
    );
    expect(screen.getByRole("button", { name: "Copy marketplace command" })).toHaveTextContent(
      "Copy"
    );

    fireEvent.click(screen.getByRole("button", { name: "Copy marketplace command" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith("/plugin marketplace add reflector-oy/schatten")
    );
  });

  it("omits the plugin origin hint on the production origin", () => {
    vi.spyOn(window, "location", "get").mockReturnValue(
      new URL("https://schatten.lupaus.eu/schatten/acme/metrics") as unknown as Location
    );
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(screen.getByText("/plugin install schatten@schatten")).toBeVisible();
    expect(
      screen.getByText("https://schatten.lupaus.eu/api/mcp", { selector: "code" })
    ).toBeVisible();
    expect(screen.queryByText(/The plugin connects to/)).not.toBeInTheDocument();
  });

  it("explains a failed command copy", async () => {
    stubClipboard(vi.fn().mockRejectedValue(new Error("Denied")));
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    fireEvent.click(screen.getByRole("button", { name: "Copy marketplace command" }));

    expect(
      await screen.findByText("Copying failed; select the command and copy it.")
    ).toBeVisible();
  });

  it("links the skill zips with upload steps for claude.ai and Claude Desktop", () => {
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(
      screen.getByRole("heading", { name: "Skills for claude.ai and Claude Desktop" })
    ).toBeVisible();
    for (const [label, name] of [
      ["Model building", "schatten-model-building"],
      ["Timeseries generation", "schatten-timeseries-generation"]
    ]) {
      const link = screen.getByRole("link", { name: `${label} (${name}.zip)` });
      expect(link).toHaveAttribute("href", `/api/v1/ai/skills/${name}.zip`);
      expect(link).toHaveAttribute("download");
    }
    expect(screen.getByText(/turn on code execution/)).toBeVisible();
    expect(screen.getByText(/Open Customize, then Skills/)).toBeVisible();
  });

  it("hides the Connect section when features.mcp is false", async () => {
    renderPanel({ mcpEnabled: false });

    expect(await screen.findByText("No change sets.")).toBeVisible();
    const sections = screen.getByRole("group", { name: "AI panel section" });
    expect(within(sections).queryByRole("button", { name: "Connect" })).not.toBeInTheDocument();
    expect(within(sections).getByRole("button", { name: "Connections" })).toBeVisible();
    expect(screen.queryByText(/api\/mcp/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/plugin (marketplace add|install)/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /\.zip/ })).not.toBeInTheDocument();
  });
});
