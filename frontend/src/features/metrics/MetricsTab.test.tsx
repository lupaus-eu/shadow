import {
  fireEvent,
  render,
  screen,
  waitFor,
  within
} from "@testing-library/react";
import type { ContextType } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as timeseriesApi from "../../api/timeseries";
import type { TimeserieDto } from "../../api/timeseries";
import {
  WorkspaceSelectionContext
} from "../../workspace/WorkspaceSelectionContext";
import MetricsTab from "./MetricsTab";

vi.mock("../../api/timeseries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/timeseries")>();
  return {
    ...actual,
    fetchTimeseries: vi.fn(),
    updateTimeserieValues: vi.fn()
  };
});

const baseTimeseries: TimeserieDto[] = [
  {
    id: "revenue",
    name: "Revenue",
    description: "Monthly revenue",
    unit: "EUR",
    timeUnit: "month",
    valueUnit: "number",
    values: [
      { date: "2030-01-01", value: 1000 },
      { date: "2030-02-01", value: 2000 }
    ]
  },
  {
    id: "capacity",
    name: "Capacity",
    description: "",
    unit: "",
    timeUnit: "week",
    valueUnit: "boolean",
    values: [{ date: "2030-01-07", value: true }]
  },
  {
    id: "status",
    name: "Status",
    description: "",
    unit: "",
    timeUnit: "day",
    valueUnit: "string",
    values: [{ date: "2030-01-01", value: "ready" }]
  }
];

const sortableTimeseries: TimeserieDto[] = [
  {
    id: "col-c",
    name: "Alpha",
    description: "Gamma",
    unit: "USD",
    timeUnit: "year",
    valueUnit: "string",
    values: []
  },
  {
    id: "col-a",
    name: "Charlie",
    description: "Alpha",
    unit: "kg",
    timeUnit: "day",
    valueUnit: "boolean",
    values: []
  },
  {
    id: "col-b",
    name: "Bravo",
    description: "Beta",
    unit: "EUR",
    timeUnit: "month",
    valueUnit: "number",
    values: []
  }
];

function renderMetricsTab(options?: {
  scenario?: { id: string; name: string } | null;
}) {
  const context: ContextType<typeof WorkspaceSelectionContext> = {
    selectedScenario:
      options?.scenario === undefined
        ? { id: "future", name: "Future plan" }
        : options.scenario,
    setSelectedScenario: vi.fn(),
    selectedOrgState: null,
    setSelectedOrgState: vi.fn(),
    setWorkspaceSelection: vi.fn()
  };

  return render(
    <WorkspaceSelectionContext.Provider value={context}>
      <MetricsTab orgId="acme" />
    </WorkspaceSelectionContext.Provider>
  );
}

function mockUpdateWithPayloadValues(sourceRows = baseTimeseries) {
  vi.mocked(timeseriesApi.updateTimeserieValues).mockImplementation(
    async (_orgId, _scenarioId, timeserieId, payload) => {
      const source = sourceRows.find((row) => row.id === timeserieId);
      if (!source) throw new Error("Missing mock row.");
      return { ...source, values: payload.values };
    }
  );
}

function csvFile(contents: string, name = "values.csv"): File {
  const file = new File([contents], name, { type: "text/csv" });
  Object.defineProperty(file, "text", {
    value: vi.fn().mockResolvedValue(contents)
  });
  return file;
}

describe("MetricsTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(timeseriesApi.fetchTimeseries).mockResolvedValue(baseTimeseries);
    mockUpdateWithPayloadValues();
  });

  it("shows an empty state and does not fetch without a selected scenario", () => {
    renderMetricsTab({ scenario: null });

    expect(
      screen.getByText("Select a scenario in Scenarios to activate this tab.")
    ).toBeInTheDocument();
    expect(timeseriesApi.fetchTimeseries).not.toHaveBeenCalled();
  });

  it("shows loading, empty and error states", async () => {
    let resolveLoad!: (rows: TimeserieDto[]) => void;
    vi.mocked(timeseriesApi.fetchTimeseries).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveLoad = resolve;
      })
    );

    renderMetricsTab();

    expect(screen.getByText("Loading metrics...")).toBeInTheDocument();
    resolveLoad([]);
    expect(await screen.findByText("No metrics available.")).toBeInTheDocument();

    vi.mocked(timeseriesApi.fetchTimeseries).mockRejectedValueOnce(
      new Error("Metrics unavailable")
    );
    renderMetricsTab();

    expect(await screen.findByText("Metrics API error")).toBeInTheDocument();
    expect(
      screen.getByText("Could not load metrics. Metrics unavailable")
    ).toBeInTheDocument();
  });

  it("fetches timeseries for the selected scenario and renders typed cells", async () => {
    renderMetricsTab();

    expect(
      await screen.findByRole("heading", { name: "Metrics", level: 1 })
    ).toBeInTheDocument();
    expect(timeseriesApi.fetchTimeseries).toHaveBeenCalledWith(
      "acme",
      "future",
      expect.any(AbortSignal)
    );
    expect(screen.getByText("3 timeserie(s)")).toBeInTheDocument();
    expect(screen.getByLabelText("Revenue 2030-01-01")).toHaveValue(1000);
    expect(screen.getByLabelText("Status 2030-01-01")).toHaveValue("ready");
    expect(screen.getByLabelText("Capacity 2030-01-07")).toHaveValue("true");
    expect(
      screen.getByLabelText("Revenue 2030-01-07 read-only")
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Capacity 2030-01-01 read-only")
    ).toBeInTheDocument();
  });

  it("filters manual and derived metrics by kind and time unit", async () => {
    vi.mocked(timeseriesApi.fetchTimeseries).mockResolvedValueOnce([
      ...baseTimeseries,
      {
        ...baseTimeseries[0],
        id: "average-revenue",
        name: "Average revenue",
        isDerived: true,
        derivedFormula: "revenue / 2"
      }
    ]);
    renderMetricsTab();

    const filters = await screen.findByRole("group", { name: "Filter by" });
    const derived = within(filters).getByRole("checkbox", { name: "Derived metrics" });
    const month = within(filters).getByRole("checkbox", { name: "Month" });
    expect(derived).toBeChecked();
    expect(month).toBeChecked();
    expect(screen.getByText("Average revenue")).toBeInTheDocument();

    fireEvent.click(derived);

    expect(derived).not.toBeChecked();
    expect(screen.queryByText("Average revenue")).not.toBeInTheDocument();
    expect(screen.getByText("Revenue")).toBeInTheDocument();

    fireEvent.click(month);

    expect(screen.queryByText("Revenue")).not.toBeInTheDocument();
  });

  it("keeps a derived-value date visible only while derived metrics are shown", async () => {
    const derivedOnly: TimeserieDto = {
      ...baseTimeseries[0],
      id: "derived-only",
      name: "Derived only",
      isDerived: true,
      derivedFormula: "revenue * 2",
      values: [{ date: "2030-03-01", value: 6000 }]
    };
    vi.mocked(timeseriesApi.fetchTimeseries).mockResolvedValueOnce([derivedOnly]);
    renderMetricsTab();

    const derivedCell = await screen.findByLabelText("Derived only 2030-03-01");
    expect(derivedCell).toBeDisabled();
    expect(
      screen.getByRole("columnheader", { name: "2030-03-01" })
    ).toBeInTheDocument();

    const filters = screen.getByRole("group", { name: "Filter by" });
    const derived = within(filters).getByRole("checkbox", { name: "Derived metrics" });
    fireEvent.click(derived);

    expect(
      screen.queryByRole("columnheader", { name: "2030-03-01" })
    ).not.toBeInTheDocument();

    fireEvent.click(derived);
    expect(
      screen.getByRole("columnheader", { name: "2030-03-01" })
    ).toBeInTheDocument();
  });

  it("hides manually added dates that every visible timeserie treats as read-only", async () => {
    vi.mocked(timeseriesApi.fetchTimeseries).mockResolvedValueOnce([
      {
        ...baseTimeseries[0],
        id: "annual-revenue",
        timeUnit: "year",
        values: [{ date: "2030-01-01", value: 1000 }]
      },
      {
        ...baseTimeseries[1],
        id: "weekly-capacity",
        values: [{ date: "2030-01-07", value: true }]
      }
    ]);
    renderMetricsTab();

    await screen.findByLabelText("Revenue 2030-01-01");
    fireEvent.change(screen.getByLabelText("Date column"), {
      target: { value: "2030-01-02" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Add date" }));

    expect(
      screen.queryByRole("columnheader", { name: "2030-01-02" })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "2030-01-01" })
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Revenue 2030-01-01")).toBeEnabled();
  });

  it("filters displayed dates without omitting hidden values from a row save", async () => {
    renderMetricsTab();

    await screen.findByLabelText("Revenue 2030-01-01");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2030-02-01" } });
    expect(screen.queryByLabelText("Revenue 2030-01-01")).not.toBeInTheDocument();
    const revenue = screen.getByLabelText("Revenue 2030-02-01");
    fireEvent.change(revenue, { target: { value: "2500" } });
    const row = screen.getByText("Revenue").closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: "Save row" }));

    await waitFor(() => expect(timeseriesApi.updateTimeserieValues).toHaveBeenCalledWith(
      "acme",
      "future",
      "revenue",
      { values: [{ date: "2030-01-01", value: 1000 }, { date: "2030-02-01", value: 2500 }] }
    ));
  });

  it("adjusts date-cell width with the slider and buttons", async () => {
    renderMetricsTab();

    await screen.findByLabelText("Revenue 2030-01-01");
    const width = screen.getByRole("slider", { name: "Timeserie value cell width" });
    expect(width).toHaveValue("150");
    fireEvent.click(screen.getByRole("button", { name: "Increase timeserie value cell width" }));
    expect(width).toHaveValue("160");
    fireEvent.change(width, { target: { value: "90" } });
    expect(screen.getByRole("button", { name: "Decrease timeserie value cell width" })).toBeDisabled();
    expect(screen.getByLabelText("Metrics grid")).toHaveStyle("--metrics-date-cell-width: 90px");
  });

  it("refreshes derived values after saving a referenced manual metric", async () => {
    const derivedMetric: TimeserieDto = {
      ...baseTimeseries[0],
      id: "double-revenue",
      name: "Double revenue",
      isDerived: true,
      derivedFormula: "revenue * 2",
      values: [
        { date: "2030-01-01", value: 2000 },
        { date: "2030-02-01", value: 4000 }
      ]
    };
    const refreshedMetrics: TimeserieDto[] = [
      {
        ...baseTimeseries[0],
        values: [
          { date: "2030-01-01", value: 1500 },
          { date: "2030-02-01", value: 2000 }
        ]
      },
      baseTimeseries[1],
      baseTimeseries[2],
      {
        ...derivedMetric,
        values: [
          { date: "2030-01-01", value: 3000 },
          { date: "2030-02-01", value: 4000 }
        ]
      }
    ];
    vi.mocked(timeseriesApi.fetchTimeseries)
      .mockResolvedValueOnce([...baseTimeseries, derivedMetric])
      .mockResolvedValueOnce(refreshedMetrics);
    vi.mocked(timeseriesApi.updateTimeserieValues).mockResolvedValue(
      refreshedMetrics[0]
    );
    renderMetricsTab();

    const revenueInput = await screen.findByLabelText("Revenue 2030-01-01");
    fireEvent.change(revenueInput, { target: { value: "1500" } });
    fireEvent.click(
      within(revenueInput.closest("tr") as HTMLElement).getByRole("button", {
        name: "Save row"
      })
    );

    await waitFor(() => {
      expect(
        screen.getByLabelText("Double revenue 2030-01-01")
      ).toHaveValue(3000);
    });
  });

  it("shows and hides the derived-metric editor on demand", async () => {
    renderMetricsTab();

    expect(
      screen.queryByRole("heading", { name: "Create derived metric" })
    ).not.toBeInTheDocument();

    fireEvent.click(
      await screen.findByRole("button", { name: "Create derived metric" })
    );
    expect(
      screen.getByRole("heading", { name: "Create derived metric" })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      screen.queryByRole("heading", { name: "Create derived metric" })
    ).not.toBeInTheDocument();
  });

  it("closes a derived-metric editor when the scenario changes", async () => {
    const derivedMetric: TimeserieDto = {
      ...baseTimeseries[0],
      id: "double-revenue",
      name: "Double revenue",
      isDerived: true,
      derivedFormula: "revenue * 2"
    };
    vi.mocked(timeseriesApi.fetchTimeseries)
      .mockResolvedValueOnce([...baseTimeseries, derivedMetric])
      .mockResolvedValueOnce(baseTimeseries);
    const view = renderMetricsTab();

    fireEvent.click(
      await screen.findByRole("button", { name: "Edit derived metric" })
    );
    expect(
      screen.getByRole("heading", { name: "Edit derived metric" })
    ).toBeInTheDocument();

    view.rerender(
      <WorkspaceSelectionContext.Provider
        value={{
          selectedScenario: { id: "alternate", name: "Alternate" },
          setSelectedScenario: vi.fn(),
          selectedOrgState: null,
          setSelectedOrgState: vi.fn(),
          setWorkspaceSelection: vi.fn()
        }}
      >
        <MetricsTab orgId="acme" />
      </WorkspaceSelectionContext.Provider>
    );

    await waitFor(() => {
      expect(timeseriesApi.fetchTimeseries).toHaveBeenCalledWith(
        "acme",
        "alternate",
        expect.any(AbortSignal)
      );
    });
    expect(
      screen.queryByRole("heading", { name: "Edit derived metric" })
    ).not.toBeInTheDocument();
  });

  it("refetches metrics when workspace scenario changes in place", async () => {
    const view = renderMetricsTab();
    await screen.findByText("3 timeserie(s)");
    vi.mocked(timeseriesApi.fetchTimeseries).mockClear();

    view.rerender(
      <WorkspaceSelectionContext.Provider
        value={{
          selectedScenario: { id: "alternate", name: "Alternate" },
          setSelectedScenario: vi.fn(),
          selectedOrgState: null,
          setSelectedOrgState: vi.fn(),
          setWorkspaceSelection: vi.fn()
        }}
      >
        <MetricsTab orgId="acme" />
      </WorkspaceSelectionContext.Provider>
    );

    await waitFor(() => {
      expect(timeseriesApi.fetchTimeseries).toHaveBeenCalledWith(
        "acme",
        "alternate",
        expect.any(AbortSignal)
      );
    });
  });

  it("discards an import that finishes after the workspace scenario changes", async () => {
    const view = renderMetricsTab();
    const revenueRow = (await screen.findByText("Revenue")).closest("tr");
    expect(revenueRow).not.toBeNull();
    const csvPicker = within(revenueRow as HTMLElement).getByLabelText(
      "CSV file for Revenue"
    );
    let resolveFileText!: (text: string) => void;
    const pendingFile = new File([""], "values.csv", { type: "text/csv" });
    Object.defineProperty(pendingFile, "text", {
      value: vi.fn(
        () => new Promise<string>((resolve) => {
          resolveFileText = resolve;
        })
      )
    });

    fireEvent.change(csvPicker, { target: { files: [pendingFile] } });
    await waitFor(() => expect(pendingFile.text).toHaveBeenCalledOnce());

    let resolveAlternateMetrics!: (rows: TimeserieDto[]) => void;
    vi.mocked(timeseriesApi.fetchTimeseries).mockImplementationOnce(
      () =>
        new Promise<TimeserieDto[]>((resolve) => {
          resolveAlternateMetrics = resolve;
        })
    );
    view.rerender(
      <WorkspaceSelectionContext.Provider
        value={{
          selectedScenario: { id: "alternate", name: "Alternate" },
          setSelectedScenario: vi.fn(),
          selectedOrgState: null,
          setSelectedOrgState: vi.fn(),
          setWorkspaceSelection: vi.fn()
        }}
      >
        <MetricsTab orgId="acme" />
      </WorkspaceSelectionContext.Provider>
    );
    expect(await screen.findByText("Loading metrics...")).toBeInTheDocument();

    resolveFileText("2030-03-01,3000");
    resolveAlternateMetrics(baseTimeseries);

    expect(await screen.findByText("3 timeserie(s)")).toBeInTheDocument();
    expect(screen.queryByLabelText("Revenue 2030-03-01")).not.toBeInTheDocument();
    expect(screen.queryByText("Imported 1 value(s) for Revenue.")).not.toBeInTheDocument();
  });

  it("sorts metric rows by every toolbar option", async () => {
    vi.mocked(timeseriesApi.fetchTimeseries).mockResolvedValueOnce(
      sortableTimeseries
    );
    renderMetricsTab();

    const sortSelect = await screen.findByRole("combobox", {
      name: "Sort metrics"
    });
    expect(
      within(sortSelect).getAllByRole("option").map((option) => option.textContent)
    ).toEqual([
      "Sort by:",
      "Timeserie name, asc.",
      "Timeserie name, desc.",
      "Col name, asc.",
      "Col name, desc.",
      "Description, asc.",
      "Description, desc.",
      "Unit, asc.",
      "Unit, desc.",
      "Time unit, asc.",
      "Time unit, desc.",
      "Value unit, asc.",
      "Value unit, desc."
    ]);

    const rowNames = () =>
      screen
        .getAllByRole("rowheader")
        .map((cell) => cell.querySelector("strong")?.textContent);
    const expectations: Array<[string, string[]]> = [
      ["name-asc", ["Alpha", "Bravo", "Charlie"]],
      ["name-desc", ["Charlie", "Bravo", "Alpha"]],
      ["id-asc", ["Charlie", "Bravo", "Alpha"]],
      ["id-desc", ["Alpha", "Bravo", "Charlie"]],
      ["description-asc", ["Charlie", "Bravo", "Alpha"]],
      ["description-desc", ["Alpha", "Bravo", "Charlie"]],
      ["unit-asc", ["Bravo", "Charlie", "Alpha"]],
      ["unit-desc", ["Alpha", "Charlie", "Bravo"]],
      ["time-unit-asc", ["Charlie", "Bravo", "Alpha"]],
      ["time-unit-desc", ["Alpha", "Bravo", "Charlie"]],
      ["value-unit-asc", ["Charlie", "Bravo", "Alpha"]],
      ["value-unit-desc", ["Alpha", "Bravo", "Charlie"]]
    ];

    for (const [value, expectedNames] of expectations) {
      fireEvent.change(sortSelect, { target: { value } });
      expect(rowNames()).toEqual(expectedNames);
    }
  });

  it("sorts time units in day, week, month, year order", async () => {
    renderMetricsTab();

    const sortSelect = await screen.findByRole("combobox", {
      name: "Sort metrics"
    });
    const rowNames = () =>
      screen
        .getAllByRole("rowheader")
        .map((cell) => cell.querySelector("strong")?.textContent);

    fireEvent.change(sortSelect, { target: { value: "time-unit-asc" } });
    expect(rowNames()).toEqual(["Status", "Capacity", "Revenue"]);

    fireEvent.change(sortSelect, { target: { value: "time-unit-desc" } });
    expect(rowNames()).toEqual(["Revenue", "Capacity", "Status"]);
  });

  it("adds manual columns and the next valid date for one row", async () => {
    renderMetricsTab();

    await screen.findByLabelText("Revenue 2030-01-01");
    fireEvent.change(screen.getByLabelText("Date column"), {
      target: { value: "2030-03-01" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Add date" }));

    expect(screen.getByLabelText("Revenue 2030-03-01")).toBeInTheDocument();

    const revenueRow = screen.getByText("Revenue").closest("tr");
    expect(revenueRow).not.toBeNull();
    fireEvent.click(
      within(revenueRow as HTMLElement).getByRole("button", {
        name: "Add next date"
      })
    );

    expect(screen.getByLabelText("Revenue 2030-04-01")).toBeInTheDocument();
  });

  it("saves one dirty row and omits blank cells from the payload", async () => {
    renderMetricsTab();

    const revenueRow = (await screen.findByText("Revenue")).closest("tr");
    expect(revenueRow).not.toBeNull();
    fireEvent.change(screen.getByLabelText("Revenue 2030-01-01"), {
      target: { value: "1250" }
    });
    fireEvent.change(screen.getByLabelText("Revenue 2030-02-01"), {
      target: { value: "" }
    });

    expect(within(revenueRow as HTMLElement).getByText("Changed")).toBeInTheDocument();
    fireEvent.click(
      within(revenueRow as HTMLElement).getByRole("button", { name: "Save row" })
    );

    await waitFor(() => {
      expect(timeseriesApi.updateTimeserieValues).toHaveBeenCalledWith(
        "acme",
        "future",
        "revenue",
        { values: [{ date: "2030-01-01", value: 1250 }] }
      );
    });
    expect(await screen.findByText("Saved Revenue.")).toBeInTheDocument();
    const savedNotice = screen.getByRole("status");
    fireEvent.click(
      within(savedNotice).getByRole("button", {
        name: "Dismiss Metrics saved notice"
      })
    );
    expect(screen.queryByText("Saved Revenue.")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText("Changed")).not.toBeInTheDocument();
    });
  });

  it("locks editing controls and shows a spinner while a row save is pending", async () => {
    let resolveSave!: () => void;
    vi.mocked(timeseriesApi.updateTimeserieValues).mockImplementationOnce(
      async (_orgId, _scenarioId, _timeserieId, payload) =>
        new Promise<void>((resolve) => {
          resolveSave = resolve;
        }).then(() => ({ ...baseTimeseries[0], values: payload.values }))
    );
    renderMetricsTab();

    const revenueInput = await screen.findByLabelText("Revenue 2030-01-01");
    fireEvent.change(revenueInput, { target: { value: "1250" } });
    const revenueRow = screen.getByText("Revenue").closest("tr");
    expect(revenueRow).not.toBeNull();
    fireEvent.click(
      within(revenueRow as HTMLElement).getByRole("button", { name: "Save row" })
    );

    const savingButton = within(revenueRow as HTMLElement).getByRole("button", {
      name: "Saving..."
    });
    expect(savingButton).toHaveAttribute("aria-busy", "true");
    expect(savingButton.querySelector(".metrics-saving-spinner")).toBeInTheDocument();
    expect(revenueInput).toBeDisabled();
    expect(screen.getByLabelText("Status 2030-01-01")).toBeDisabled();
    expect(screen.getByLabelText("Date column")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
    expect(
      within(revenueRow as HTMLElement).getByLabelText("CSV file for Revenue")
    ).toBeDisabled();
    expect(
      within(revenueRow as HTMLElement).getByRole("button", {
        name: "Import CSV"
      })
    ).toBeDisabled();
    expect(
      within(revenueRow as HTMLElement).getByRole("button", {
        name: "Add next date"
      })
    ).toBeDisabled();

    resolveSave();
    expect(await screen.findByText("Saved Revenue.")).toBeInTheDocument();
    expect(revenueInput).toBeEnabled();
  });

  it("shows a save error, keeps the row dirty and unlocks editing", async () => {
    vi.mocked(timeseriesApi.updateTimeserieValues).mockRejectedValueOnce(
      new Error("Write unavailable")
    );
    renderMetricsTab();

    const revenueInput = await screen.findByLabelText("Revenue 2030-01-01");
    fireEvent.change(revenueInput, { target: { value: "1250" } });
    const revenueRow = screen.getByText("Revenue").closest("tr");
    expect(revenueRow).not.toBeNull();
    fireEvent.click(
      within(revenueRow as HTMLElement).getByRole("button", { name: "Save row" })
    );

    expect(
      await screen.findByText("Could not save metrics. Write unavailable")
    ).toBeInTheDocument();
    expect(within(revenueRow as HTMLElement).getByText("Changed")).toBeInTheDocument();
    expect(revenueInput).toBeEnabled();
  });

  it("saves all dirty number, string and boolean rows", async () => {
    renderMetricsTab();

    await screen.findByLabelText("Revenue 2030-01-01");
    fireEvent.change(screen.getByLabelText("Revenue 2030-01-01"), {
      target: { value: "1500" }
    });
    fireEvent.change(screen.getByLabelText("Status 2030-01-01"), {
      target: { value: "blocked" }
    });
    fireEvent.change(screen.getByLabelText("Capacity 2030-01-07"), {
      target: { value: "false" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(timeseriesApi.updateTimeserieValues).toHaveBeenCalledTimes(3);
    });
    expect(timeseriesApi.updateTimeserieValues).toHaveBeenCalledWith(
      "acme",
      "future",
      "revenue",
      expect.objectContaining({
        values: expect.arrayContaining([
          { date: "2030-01-01", value: 1500 }
        ])
      })
    );
    expect(timeseriesApi.updateTimeserieValues).toHaveBeenCalledWith(
      "acme",
      "future",
      "status",
      expect.objectContaining({
        values: [{ date: "2030-01-01", value: "blocked" }]
      })
    );
    expect(timeseriesApi.updateTimeserieValues).toHaveBeenCalledWith(
      "acme",
      "future",
      "capacity",
      expect.objectContaining({
        values: [{ date: "2030-01-07", value: false }]
      })
    );
  });

  it("applies successful rows and leaves failed rows dirty after a partial bulk save", async () => {
    vi.mocked(timeseriesApi.updateTimeserieValues).mockImplementation(
      async (_orgId, _scenarioId, timeserieId, payload) => {
        if (timeserieId === "status") throw new Error("Status write unavailable");
        const source = baseTimeseries.find((row) => row.id === timeserieId);
        if (!source) throw new Error("Missing mock row.");
        return { ...source, values: payload.values };
      }
    );
    renderMetricsTab();

    fireEvent.change(await screen.findByLabelText("Revenue 2030-01-01"), {
      target: { value: "1500" }
    });
    fireEvent.change(screen.getByLabelText("Status 2030-01-01"), {
      target: { value: "blocked" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(
      await screen.findByText(
        "Could not save 1 of 2 row(s). Saved 1 row(s). Status write unavailable"
      )
    ).toBeInTheDocument();
    const revenueRow = screen.getByText("Revenue").closest("tr");
    const statusRow = screen.getByText("Status").closest("tr");
    expect(revenueRow).not.toBeNull();
    expect(statusRow).not.toBeNull();
    expect(
      within(revenueRow as HTMLElement).queryByText("Changed")
    ).not.toBeInTheDocument();
    expect(within(statusRow as HTMLElement).getByText("Changed")).toBeInTheDocument();
    expect(screen.getByLabelText("Status 2030-01-01")).toBeEnabled();
  });

  it("imports a selected CSV file into one row and validates its contents", async () => {
    renderMetricsTab();

    const revenueRow = (await screen.findByText("Revenue")).closest("tr");
    expect(revenueRow).not.toBeNull();
    const row = revenueRow as HTMLElement;
    const csvPicker = within(row).getByLabelText("CSV file for Revenue");
    const importButton = within(row).getByRole("button", { name: "Import CSV" });

    expect(within(row).queryByLabelText("CSV import for Revenue")).toBeNull();
    expect(csvPicker).toHaveAttribute("type", "file");
    expect(csvPicker).toHaveAttribute("accept", ".csv,text/csv");

    const openPicker = vi.spyOn(csvPicker, "click");
    fireEvent.click(importButton);
    expect(openPicker).toHaveBeenCalledOnce();
    openPicker.mockRestore();

    fireEvent.change(csvPicker, { target: { files: [] } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    const validFile = csvFile("2030-03-01,3000\n2030-04-01;4000");
    fireEvent.change(csvPicker, { target: { files: [validFile] } });

    expect(await screen.findByLabelText("Revenue 2030-03-01")).toHaveValue(3000);
    expect(screen.getByLabelText("Revenue 2030-04-01")).toHaveValue(4000);
    expect(csvPicker).toHaveValue("");
    expect(validFile.text).toHaveBeenCalledOnce();

    fireEvent.change(csvPicker, { target: { files: [validFile] } });
    await waitFor(() => expect(validFile.text).toHaveBeenCalledTimes(2));
    expect(csvPicker).toHaveValue("");

    fireEvent.change(csvPicker, {
      target: { files: [csvFile("2030-02-30,5000")] }
    });
    expect(
      await screen.findByText("2030-02-30 is not a valid date.")
    ).toBeInTheDocument();

    fireEvent.change(csvPicker, {
      target: { files: [csvFile("2030-04-02,5000")] }
    });
    expect(
      await screen.findByText("2030-04-02 is not valid for Revenue month values.")
    ).toBeInTheDocument();

    fireEvent.change(csvPicker, {
      target: { files: [csvFile("2030-04-01,not-a-number")] }
    });
    expect(
      await screen.findByText(
        "Revenue has an invalid number CSV value for 2030-04-01."
      )
    ).toBeInTheDocument();

    fireEvent.change(csvPicker, {
      target: { files: [csvFile("2030-04-01,4000,unexpected")] }
    });
    expect(
      await screen.findByText("CSV rows must contain date and value.")
    ).toBeInTheDocument();
  });
});
