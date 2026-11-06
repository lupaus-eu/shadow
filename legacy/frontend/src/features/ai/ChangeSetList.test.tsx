import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAiChangeSets } from "../../api/ai";
import type { AiChangeSetListItemDto } from "../../api/ai";
import ChangeSetList from "./ChangeSetList";

vi.mock("../../api/ai", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/ai")>()),
  fetchAiChangeSets: vi.fn()
}));

const fetchChangeSetsMock = vi.mocked(fetchAiChangeSets);

function listItem(overrides: Partial<AiChangeSetListItemDto>): AiChangeSetListItemDto {
  return {
    id: "cs-1",
    scenarioKey: "future",
    title: "Revenue model",
    rationale: null,
    status: "submitted",
    operationCount: 3,
    clientId: "client-abc",
    clientName: "Claude",
    createdBy: 7,
    createdByName: "Ada Consultant",
    createdTime: "2026-10-27T09:00:00Z",
    modifiedTime: "2026-10-27T09:00:00Z",
    reviewedBy: null,
    reviewedByName: null,
    reviewedTime: null,
    reviewNote: null,
    reviewedVia: null,
    reviewClientId: null,
    reviewClientName: null,
    ...overrides
  };
}

const scoped = listItem({});
const unscoped = listItem({
  id: "cs-2",
  scenarioKey: null,
  title: "New scenario",
  status: "applied"
});
const otherScenario = listItem({
  id: "cs-3",
  scenarioKey: "reality",
  title: "Reality fix",
  status: "rejected"
});

beforeEach(() => {
  vi.resetAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ChangeSetList", () => {
  it("shows the selected scenario's and unscoped change sets by default, and all on toggle", async () => {
    fetchChangeSetsMock
      .mockResolvedValueOnce([scoped, unscoped])
      .mockResolvedValueOnce([scoped, unscoped, otherScenario]);

    render(
      <ChangeSetList
        orgId="acme"
        scenario={{ id: "future", name: "Future plan" }}
        onSelect={vi.fn()}
      />
    );

    const list = await screen.findByRole("list", { name: "AI change sets" });
    await within(list).findByText("Revenue model");
    expect(fetchChangeSetsMock).toHaveBeenCalledWith(
      "acme",
      { scenarioKey: "future", includeUnscoped: true },
      expect.any(AbortSignal)
    );
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("No single scenario")).toBeVisible();
    expect(within(list).getByText("Awaiting review")).toBeVisible();
    expect(within(list).getByText("Applied")).toBeVisible();
    expect(screen.getByText(/Showing change sets for/)).toHaveTextContent(
      "Showing change sets for Future plan and change sets without a single scenario."
    );

    fireEvent.click(screen.getByLabelText("Show all change sets of the organisation"));

    expect(await screen.findByText("Reality fix")).toBeVisible();
    expect(fetchChangeSetsMock).toHaveBeenLastCalledWith("acme", {}, expect.any(AbortSignal));
    expect(screen.getByText("Rejected")).toBeVisible();
    expect(screen.getByText("Showing every change set of the organisation.")).toBeVisible();
  });

  it("names the AI client of a change set reviewed through MCP", async () => {
    fetchChangeSetsMock.mockResolvedValue([
      listItem({
        status: "applied",
        reviewedBy: 8,
        reviewedByName: "Rita Reviewer",
        reviewedTime: "2026-10-28T08:00:00Z",
        reviewedVia: "mcp",
        reviewClientId: "client-review",
        reviewClientName: "Claude Code"
      }),
      listItem({
        id: "cs-web",
        title: "Web review",
        status: "rejected",
        reviewedBy: 8,
        reviewedByName: "Rita Reviewer",
        reviewedTime: "2026-10-28T08:00:00Z",
        reviewedVia: "web"
      })
    ]);

    render(<ChangeSetList orgId="acme" scenario={null} onSelect={vi.fn()} />);

    const list = await screen.findByRole("list", { name: "AI change sets" });
    const [mcpItem, webItem] = await within(list).findAllByRole("listitem");
    expect(mcpItem).toHaveTextContent("Reviewed through AI client Claude Code (MCP)");
    expect(within(mcpItem).getByText("Claude Code").tagName).toBe("BDI");
    expect(webItem).not.toHaveTextContent("Reviewed through");
  });

  it("lists every change set without a selected scenario and opens one", async () => {
    fetchChangeSetsMock.mockResolvedValue([otherScenario]);
    const onSelect = vi.fn();

    render(<ChangeSetList orgId="acme" scenario={null} onSelect={onSelect} />);

    fireEvent.click(await screen.findByRole("button", { name: /Reality fix/ }));

    expect(onSelect).toHaveBeenCalledWith("cs-3");
    expect(fetchChangeSetsMock).toHaveBeenCalledWith("acme", {}, expect.any(AbortSignal));
    expect(
      screen.queryByLabelText("Show all change sets of the organisation")
    ).not.toBeInTheDocument();
  });

  it("shows an empty list and a load error with retry", async () => {
    fetchChangeSetsMock
      .mockRejectedValueOnce(new Error("Failed to fetch AI change sets (503)."))
      .mockResolvedValueOnce([]);

    render(<ChangeSetList orgId="acme" scenario={null} onSelect={vi.fn()} />);

    expect(await screen.findByText("Failed to fetch AI change sets (503).")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("No change sets.")).toBeVisible();
    await waitFor(() => expect(fetchChangeSetsMock).toHaveBeenCalledTimes(2));
  });

  it("closes the load error", async () => {
    fetchChangeSetsMock.mockRejectedValue(new Error("Failed to fetch AI change sets (503)."));

    render(<ChangeSetList orgId="acme" scenario={null} onSelect={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("(503)");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss Change sets API error notice" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
