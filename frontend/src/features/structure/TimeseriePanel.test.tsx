import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { GraphNodeDto, NodeTypeMetadataDto } from "../../api/orgTwinStructure";
import * as timeseriesApi from "../../api/timeseries";
import type { TimeserieDto, TimeserieSummaryDto } from "../../api/timeseries";
import TimeseriePanel from "./TimeseriePanel";

vi.mock("../../api/timeseries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/timeseries")>();
  return {
    ...actual,
    createTimeserie: vi.fn(),
    deleteTimeserie: vi.fn(),
    fetchTimeserieExists: vi.fn(),
    fetchTimeserieSummaries: vi.fn(),
    fetchTimeseries: vi.fn()
  };
});

const PLACEHOLDER = "Select existing timeseries id";

const metricType: NodeTypeMetadataDto = {
  id: "nt_metric",
  name: "metric",
  displayName: "Metric",
  color: "#fbcfe8",
  shape: "rectangle",
  timeserieId: "id1",
  timeserieSecondaryId: "id2",
  timeserieIdRule: null
};

const revenueNode: GraphNodeDto = {
  id: "node_revenue",
  name: "Revenue",
  description: "",
  nodeTypeId: "nt_metric",
  createDate: null,
  deleteDate: null,
  position: { x: 0, y: 0 },
  attributes: {},
  timeserieId: null,
  timeserieSecondaryId: null
};

function summary(id: string, name: string): TimeserieSummaryDto {
  return {
    id,
    name,
    description: "",
    unit: "",
    timeUnit: "month",
    valueUnit: "number"
  };
}

function timeserie(id: string, name: string): TimeserieDto {
  return { ...summary(id, name), values: [] };
}

// Unsorted, to check that the options are sorted by id.
const scenarioTimeseries = [
  summary("ts_margin", "Margin"),
  summary("id1", "Revenue"),
  summary("ts_cost", "Cost")
];

type Slot = "Primary" | "Secondary";

function renderPanel(overrides: { node?: GraphNodeDto; nodeType?: NodeTypeMetadataDto } = {}) {
  const onUpdateLinks = vi.fn().mockResolvedValue(undefined);
  const onTimeserieDeleted = vi.fn();
  const node = overrides.node ?? revenueNode;
  const nodeType = overrides.nodeType ?? metricType;
  const result = render(
    <TimeseriePanel
      orgId="acme"
      scenarioId="future"
      node={node}
      nodeType={nodeType}
      nodes={[node]}
      edges={[]}
      nodeTypes={[nodeType]}
      edgeTypes={[]}
      saving={false}
      onUpdateLinks={onUpdateLinks}
      onTimeserieDeleted={onTimeserieDeleted}
    />
  );
  return { ...result, onUpdateLinks, onTimeserieDeleted };
}

const linkRegion = () => screen.getByRole("region", { name: "Link to existing timeserie(s)" });
const editRegion = () => screen.getByRole("region", { name: "Create/edit timeserie(s)" });
const card = (slot: Slot) =>
  within(editRegion()).getByRole("region", { name: `${slot} timeserie` });
const linkSelect = (slot: Slot) => within(linkRegion()).getByLabelText(`${slot} link`);
const saveLinksButton = () => within(linkRegion()).getByRole("button", { name: "Save link(s)" });

async function waitForOptions() {
  await waitFor(() => expect(linkSelect("Primary")).toBeEnabled());
}

function openOptions(slot: Slot): string[] {
  fireEvent.click(linkSelect(slot));
  return within(within(linkRegion()).getByRole("listbox"))
    .getAllByRole("option")
    .map((option) => option.textContent ?? "");
}

function chooseLink(slot: Slot, timeserieId: string) {
  fireEvent.click(linkSelect(slot));
  const listbox = within(linkRegion()).getByRole("listbox");
  fireEvent.click(within(listbox).getByRole("option", { name: new RegExp(`^${timeserieId} – `) }));
}

async function waitForStatus(slot: Slot, status: string) {
  await waitFor(() => expect(within(card(slot)).getByText(status)).toBeInTheDocument());
}

// The card's "Name" row value; the create form's "Name" label is not a row.
function cardName(slot: Slot): string | null {
  const term = [...card(slot).querySelectorAll("dt")].find((dt) => dt.textContent === "Name");
  return term?.nextElementSibling?.textContent ?? null;
}

describe("TimeseriePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const existingIds = new Set(["id1", "ts_cost", "ts_margin"]);
    vi.mocked(timeseriesApi.fetchTimeserieSummaries).mockResolvedValue(scenarioTimeseries);
    vi.mocked(timeseriesApi.fetchTimeserieExists).mockImplementation(async (_o, _s, id) => ({
      id,
      exists: existingIds.has(id),
      shortName: ""
    }));
    // Existence checks see the test's own creates and deletes, like the backend.
    vi.mocked(timeseriesApi.createTimeserie).mockImplementation(async (_o, _s, payload) => {
      existingIds.add(payload.id);
      return timeserie(payload.id, payload.name);
    });
    vi.mocked(timeseriesApi.deleteTimeserie).mockImplementation(async (_o, _s, id) => {
      existingIds.delete(id);
    });
  });

  it("shows the link region above the create/edit region without free-text links", async () => {
    renderPanel();

    expect(
      screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent)
    ).toEqual(["Link to existing timeserie(s)", "Create/edit timeserie(s)"]);
    expect(within(linkRegion()).queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText("Save links")).not.toBeInTheDocument();
    expect(linkSelect("Primary")).toHaveTextContent(PLACEHOLDER);
    expect(linkSelect("Secondary")).toHaveTextContent(PLACEHOLDER);
    await waitForOptions();
  });

  it("disables the dropdowns while loading and aborts the list request on unmount", () => {
    vi.mocked(timeseriesApi.fetchTimeserieSummaries).mockReturnValue(new Promise(() => {}));
    const { unmount } = renderPanel();

    expect(linkSelect("Primary")).toBeDisabled();
    expect(linkSelect("Secondary")).toBeDisabled();
    const signal = vi.mocked(timeseriesApi.fetchTimeserieSummaries).mock.calls[0][2];
    expect(timeseriesApi.fetchTimeserieSummaries).toHaveBeenCalledWith("acme", "future", signal);

    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("loads the options from the values-free list, not the list with values", async () => {
    renderPanel();
    await waitForOptions();

    expect(timeseriesApi.fetchTimeserieSummaries).toHaveBeenCalledTimes(1);
    expect(timeseriesApi.fetchTimeserieSummaries).toHaveBeenCalledWith(
      "acme",
      "future",
      expect.any(AbortSignal)
    );
    expect(timeseriesApi.fetchTimeseries).not.toHaveBeenCalled();
  });

  it("lists the scenario's timeseries sorted by id", async () => {
    renderPanel();
    await waitForOptions();

    expect(openOptions("Secondary")).toEqual([
      "id1 – Revenue",
      "ts_cost – Cost",
      "ts_margin – Margin"
    ]);
  });

  it("keeps the dropdowns disabled and shows one closable alert when the list fails", async () => {
    vi.mocked(timeseriesApi.fetchTimeserieSummaries).mockRejectedValue(new Error("List failed"));
    renderPanel();

    expect(await within(linkRegion()).findByRole("alert")).toHaveTextContent("List failed");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(linkSelect("Primary")).toBeDisabled();
    expect(linkSelect("Secondary")).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Dismiss Timeserie list error notice" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(linkSelect("Primary")).toBeDisabled();

    await waitForStatus("Secondary", "Missing");
    fireEvent.click(within(card("Secondary")).getByRole("button", { name: "Create timeserie" }));
    await waitForStatus("Secondary", "Exists");
    // Without the list there are no names to show.
    await waitForStatus("Primary", "Exists");
    expect(cardName("Primary")).toBeNull();
    expect(cardName("Secondary")).toBeNull();
  });

  it("shows the name of an existing timeserie on its card", async () => {
    renderPanel();
    await waitForOptions();
    await waitForStatus("Primary", "Exists");
    await waitForStatus("Secondary", "Missing");

    expect(cardName("Primary")).toBe("Revenue");
    expect(cardName("Secondary")).toBeNull();

    chooseLink("Primary", "ts_cost");
    await waitFor(() => expect(cardName("Primary")).toBe("Cost"));

    fireEvent.click(within(card("Secondary")).getByRole("button", { name: "Create timeserie" }));
    await waitForStatus("Secondary", "Exists");
    expect(cardName("Secondary")).toBe("Revenue Secondary");
  });

  it.each([
    ["primary only", { Primary: "ts_cost" }, { timeserieId: "ts_cost" }],
    ["secondary only", { Secondary: "ts_margin" }, { timeserieSecondaryId: "ts_margin" }],
    [
      "both",
      { Primary: "ts_cost", Secondary: "ts_margin" },
      { timeserieId: "ts_cost", timeserieSecondaryId: "ts_margin" }
    ]
  ])("saves the %s link selection and resets the dropdowns", async (_case, choices, payload) => {
    const { onUpdateLinks } = renderPanel();
    await waitForOptions();
    expect(saveLinksButton()).toBeDisabled();

    for (const [slot, timeserieId] of Object.entries(choices))
      chooseLink(slot as Slot, timeserieId);
    expect(saveLinksButton()).toBeEnabled();
    fireEvent.click(saveLinksButton());

    await waitFor(() => expect(linkSelect("Primary")).toHaveTextContent(PLACEHOLDER));
    expect(linkSelect("Secondary")).toHaveTextContent(PLACEHOLDER);
    expect(onUpdateLinks).toHaveBeenCalledTimes(1);
    expect(onUpdateLinks).toHaveBeenCalledWith(payload);
    expect(saveLinksButton()).toBeDisabled();
  });

  it("previews a dropdown selection in its status card before saving", async () => {
    renderPanel();
    await waitForOptions();
    await waitForStatus("Primary", "Exists");
    expect(within(card("Primary")).getByText("Type default")).toBeInTheDocument();

    chooseLink("Primary", "ts_cost");

    const primary = card("Primary");
    expect(within(primary).getByText("ts_cost")).toBeInTheDocument();
    expect(within(primary).getByText("Revenue (Metric)")).toBeInTheDocument();
    expect(within(primary).getByText("id1")).toBeInTheDocument();
    expect(timeseriesApi.fetchTimeserieExists).toHaveBeenCalledWith(
      "acme",
      "future",
      "ts_cost",
      expect.any(AbortSignal)
    );
    await waitForStatus("Primary", "Exists");
  });

  it("shows Unlink only for a saved link without a pending selection", async () => {
    const { onUpdateLinks } = renderPanel({ node: { ...revenueNode, timeserieId: "ts_cost" } });
    await waitForOptions();
    await waitForStatus("Primary", "Exists");

    expect(within(card("Secondary")).queryByRole("button", { name: "Unlink" })).toBeNull();
    fireEvent.click(within(card("Primary")).getByRole("button", { name: "Unlink" }));
    await waitFor(() => expect(onUpdateLinks).toHaveBeenCalledWith({ timeserieId: null }));
    expect(timeseriesApi.deleteTimeserie).not.toHaveBeenCalled();

    chooseLink("Primary", "ts_margin");
    expect(within(card("Primary")).queryByRole("button", { name: "Unlink" })).toBeNull();
  });

  it("clears a pending link selection with its Clear button", async () => {
    renderPanel({ node: { ...revenueNode, timeserieId: "ts_cost" } });
    await waitForOptions();
    await waitForStatus("Primary", "Exists");
    const clearPrimary = within(linkRegion()).getByRole("button", {
      name: "Clear primary link selection"
    });
    const clearSecondary = within(linkRegion()).getByRole("button", {
      name: "Clear secondary link selection"
    });
    expect(clearPrimary).toBeDisabled();
    expect(clearSecondary).toBeDisabled();

    chooseLink("Primary", "ts_margin");
    expect(clearPrimary).toBeEnabled();
    expect(clearSecondary).toBeDisabled();
    expect(within(card("Primary")).getByText("ts_margin")).toBeInTheDocument();
    expect(within(card("Primary")).queryByRole("button", { name: "Unlink" })).toBeNull();

    fireEvent.click(clearPrimary);

    expect(linkSelect("Primary")).toHaveTextContent(PLACEHOLDER);
    expect(linkSelect("Primary")).toHaveFocus();
    expect(clearPrimary).toBeDisabled();
    expect(saveLinksButton()).toBeDisabled();
    expect(within(card("Primary")).getByText("ts_cost")).toBeInTheDocument();
    expect(within(card("Primary")).getByRole("button", { name: "Unlink" })).toBeInTheDocument();
  });

  it("creates a timeserie with the type default id without linking it", async () => {
    const { onUpdateLinks } = renderPanel();
    await waitForOptions();
    await waitForStatus("Secondary", "Missing");

    const idInput = within(card("Secondary")).getByLabelText("Secondary timeserie id");
    const createButton = within(card("Secondary")).getByRole("button", {
      name: "Create timeserie"
    });
    expect(idInput).toHaveValue("id2");
    expect(idInput).toBeRequired();
    expect((idInput as HTMLInputElement).form).toBe(createButton.closest("form"));
    fireEvent.click(createButton);

    await waitForStatus("Secondary", "Exists");
    expect(timeseriesApi.createTimeserie).toHaveBeenCalledWith(
      "acme",
      "future",
      expect.objectContaining({ id: "id2", name: "Revenue Secondary" })
    );
    expect(onUpdateLinks).not.toHaveBeenCalled();
    expect(openOptions("Primary")).toContain("id2 – Revenue Secondary");
  });

  it("links a timeserie created with another id and retries only the failed link", async () => {
    const { onUpdateLinks } = renderPanel();
    onUpdateLinks.mockRejectedValueOnce(new Error("Link failed"));
    await waitForOptions();
    await waitForStatus("Secondary", "Missing");
    const secondary = card("Secondary");
    const idInput = within(secondary).getByLabelText("Secondary timeserie id");
    const createButton = within(secondary).getByRole("button", { name: "Create timeserie" });

    fireEvent.change(idInput, { target: { value: " ts_new " } });
    fireEvent.click(createButton);

    expect(await within(secondary).findByRole("alert")).toHaveTextContent(
      "Timeserie ts_new was created but could not be linked: Link failed"
    );
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(onUpdateLinks).toHaveBeenCalledWith({ timeserieSecondaryId: "ts_new" });

    fireEvent.click(createButton);
    await waitFor(() => expect(onUpdateLinks).toHaveBeenCalledTimes(2));
    expect(timeseriesApi.createTimeserie).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    fireEvent.change(idInput, { target: { value: "ts_other" } });
    fireEvent.click(createButton);
    await waitFor(() => expect(timeseriesApi.createTimeserie).toHaveBeenCalledTimes(2));
    expect(timeseriesApi.createTimeserie).toHaveBeenLastCalledWith(
      "acme",
      "future",
      expect.objectContaining({ id: "ts_other" })
    );
    await waitFor(() =>
      expect(onUpdateLinks).toHaveBeenLastCalledWith({ timeserieSecondaryId: "ts_other" })
    );
  });

  // Creates ts_new in the secondary slot with a failing link and returns the create button.
  async function createUnlinkedSecondary(onUpdateLinks: ReturnType<typeof vi.fn>) {
    onUpdateLinks.mockRejectedValueOnce(new Error("Link failed"));
    await waitForOptions();
    await waitForStatus("Secondary", "Missing");
    fireEvent.change(within(card("Secondary")).getByLabelText("Secondary timeserie id"), {
      target: { value: "ts_new" }
    });
    fireEvent.click(within(card("Secondary")).getByRole("button", { name: "Create timeserie" }));
    await within(card("Secondary")).findByRole("alert");
  }

  it("still retries only the link after a selection hides and Clear restores the form", async () => {
    const { onUpdateLinks } = renderPanel();
    await createUnlinkedSecondary(onUpdateLinks);

    chooseLink("Secondary", "ts_cost");
    expect(
      within(card("Secondary")).queryByRole("button", { name: "Create timeserie" })
    ).toBeNull();
    fireEvent.click(
      within(linkRegion()).getByRole("button", { name: "Clear secondary link selection" })
    );

    expect(within(card("Secondary")).getByLabelText("Secondary timeserie id")).toHaveValue(
      "ts_new"
    );
    fireEvent.click(within(card("Secondary")).getByRole("button", { name: "Create timeserie" }));

    await waitFor(() => expect(onUpdateLinks).toHaveBeenCalledTimes(2));
    expect(onUpdateLinks).toHaveBeenLastCalledWith({ timeserieSecondaryId: "ts_new" });
    expect(timeseriesApi.createTimeserie).toHaveBeenCalledTimes(1);
  });

  it("creates again after the created but unlinked timeserie is deleted", async () => {
    const { onUpdateLinks } = renderPanel();
    await createUnlinkedSecondary(onUpdateLinks);

    chooseLink("Secondary", "ts_new");
    await waitForStatus("Secondary", "Exists");
    fireEvent.click(within(card("Secondary")).getByRole("button", { name: "Delete timeserie" }));
    fireEvent.click(within(card("Secondary")).getByRole("button", { name: "Yes" }));
    await waitForStatus("Secondary", "Missing");

    fireEvent.click(within(card("Secondary")).getByRole("button", { name: "Create timeserie" }));

    await waitFor(() => expect(timeseriesApi.createTimeserie).toHaveBeenCalledTimes(2));
    expect(timeseriesApi.createTimeserie).toHaveBeenLastCalledWith(
      "acme",
      "future",
      expect.objectContaining({ id: "ts_new" })
    );
  });

  it("requires an id for a slot without a type default", async () => {
    const { onUpdateLinks } = renderPanel({
      nodeType: { ...metricType, timeserieSecondaryId: null }
    });
    await waitForOptions();
    const secondary = card("Secondary");
    const idInput = within(secondary).getByLabelText("Secondary timeserie id");
    const createButton = within(secondary).getByRole("button", { name: "Create timeserie" });

    expect(within(secondary).getByText("No id")).toBeInTheDocument();
    expect(within(secondary).queryByRole("button", { name: "Unlink" })).toBeNull();
    expect(idInput).toHaveValue("");
    expect(idInput).toBeRequired();
    expect(createButton).toBeDisabled();

    fireEvent.change(idInput, { target: { value: "ts_new" } });
    expect(createButton).toBeEnabled();
    fireEvent.change(within(secondary).getByLabelText("Name"), { target: { value: " " } });
    expect(createButton).toBeDisabled();
    fireEvent.change(within(secondary).getByLabelText("Name"), { target: { value: "New" } });
    fireEvent.click(createButton);

    await waitFor(() =>
      expect(onUpdateLinks).toHaveBeenCalledWith({ timeserieSecondaryId: "ts_new" })
    );
  });

  it("removes a deleted timeserie from the dropdown options", async () => {
    const { onTimeserieDeleted } = renderPanel();
    await waitForOptions();
    await waitForStatus("Primary", "Exists");

    fireEvent.click(within(card("Primary")).getByRole("button", { name: "Delete timeserie" }));
    fireEvent.click(within(card("Primary")).getByRole("button", { name: "Yes" }));

    await waitFor(() => expect(onTimeserieDeleted).toHaveBeenCalledWith("id1"));
    expect(openOptions("Primary")).toEqual(["ts_cost – Cost", "ts_margin – Margin"]);
  });

  // Holds the list request open; the returned function resolves it.
  function pendingList(): (items: TimeserieSummaryDto[]) => Promise<void> {
    let resolveList: (items: TimeserieSummaryDto[]) => void = () => {};
    vi.mocked(timeseriesApi.fetchTimeserieSummaries).mockReturnValue(
      new Promise((resolve) => {
        resolveList = resolve;
      })
    );
    return (items) => act(async () => resolveList(items));
  }

  async function deletePrimary() {
    fireEvent.click(within(card("Primary")).getByRole("button", { name: "Delete timeserie" }));
    fireEvent.click(within(card("Primary")).getByRole("button", { name: "Yes" }));
    await waitForStatus("Primary", "Missing");
  }

  it("applies creates and deletes made while the list loads to the loaded list", async () => {
    const resolveList = pendingList();
    renderPanel();
    await waitForStatus("Primary", "Exists");
    await waitForStatus("Secondary", "Missing");

    fireEvent.click(within(card("Secondary")).getByRole("button", { name: "Create timeserie" }));
    await waitForStatus("Secondary", "Exists");
    await deletePrimary();

    // A list read before both changes still has id1 and lacks id2.
    await resolveList(scenarioTimeseries);

    expect(openOptions("Primary")).toEqual([
      "id2 – Revenue Secondary",
      "ts_cost – Cost",
      "ts_margin – Margin"
    ]);
    expect(cardName("Secondary")).toBe("Revenue Secondary");
  });

  it("shows a timeserie re-created while the list loads instead of the deleted one", async () => {
    const resolveList = pendingList();
    renderPanel();
    await waitForStatus("Primary", "Exists");
    await deletePrimary();

    fireEvent.change(within(card("Primary")).getByLabelText("Name"), {
      target: { value: "New revenue" }
    });
    fireEvent.click(within(card("Primary")).getByRole("button", { name: "Create timeserie" }));
    await waitForStatus("Primary", "Exists");

    // A list read before the delete still has the old id1.
    await resolveList(scenarioTimeseries);

    expect(openOptions("Primary")).toEqual([
      "id1 – New revenue",
      "ts_cost – Cost",
      "ts_margin – Margin"
    ]);
    expect(cardName("Primary")).toBe("New revenue");
  });

  describe("shows exactly one alert", () => {
    it("below Save link(s) when saving links fails, again after closing", async () => {
      const { onUpdateLinks } = renderPanel();
      onUpdateLinks.mockRejectedValue(new Error("Timeserie not found."));
      await waitForOptions();
      chooseLink("Primary", "ts_cost");

      for (let attempt = 0; attempt < 2; attempt += 1) {
        fireEvent.click(saveLinksButton());
        const alert = await within(linkRegion()).findByRole("alert");
        expect(alert).toHaveTextContent("Timeserie not found.");
        expect(screen.getAllByRole("alert")).toHaveLength(1);
        expect(
          saveLinksButton().compareDocumentPosition(alert) & Node.DOCUMENT_POSITION_FOLLOWING
        ).toBeTruthy();
        fireEvent.click(within(alert).getByRole("button", { name: "Dismiss notice" }));
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      }
    });

    it("in the create/edit region when unlinking fails", async () => {
      const { onUpdateLinks } = renderPanel({ node: { ...revenueNode, timeserieId: "ts_cost" } });
      onUpdateLinks.mockRejectedValue(new Error("Unlink failed"));
      await waitForOptions();

      fireEvent.click(within(card("Primary")).getByRole("button", { name: "Unlink" }));

      expect(await within(editRegion()).findByRole("alert")).toHaveTextContent("Unlink failed");
      expect(screen.getAllByRole("alert")).toHaveLength(1);
    });

    it("in the create form when the id already exists", async () => {
      vi.mocked(timeseriesApi.createTimeserie).mockRejectedValue(
        new timeseriesApi.ApiError(
          409,
          '{"detail":"An active timeserie with this id already exists."}'
        )
      );
      const { onUpdateLinks } = renderPanel();
      await waitForOptions();
      await waitForStatus("Secondary", "Missing");

      fireEvent.click(within(card("Secondary")).getByRole("button", { name: "Create timeserie" }));

      const alert = await within(card("Secondary")).findByRole("alert");
      expect(alert).toHaveTextContent("An active timeserie with this id already exists.");
      expect(alert.closest("form")).toHaveClass("timeserie-create-form");
      expect(screen.getAllByRole("alert")).toHaveLength(1);
      await act(async () => {});
      expect(onUpdateLinks).not.toHaveBeenCalled();
    });
  });
});
