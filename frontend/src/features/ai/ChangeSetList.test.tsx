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
});
