import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as eventsApi from "../../api/events";
import * as structureApi from "../../api/orgTwinStructure";
import * as timeseriesApi from "../../api/timeseries";
import { WorkspaceSelectionContext } from "../../workspace/WorkspaceSelectionContext";
import type {
  WorkspaceOrgStateSummary,
  WorkspaceScenarioSummary
} from "../../workspace/WorkspaceSelectionContext";
import SummaryTab from "./SummaryTab";

vi.mock("../../api/events");
vi.mock("../../api/orgTwinStructure");
vi.mock("../../api/timeseries");

const scenario = { id: "future", name: "Future plan" };
const orgState = { id: "draft", name: "Draft", targetDate: "2026-09-01" };

const history: structureApi.GraphHistoryDto = {
  nodes: [
    {
      id: "node-a",
      name: "Alpha",
      description: "Primary node",
      nodeTypeId: "person",
      createDate: "2026-01-01",
      deleteDate: null,
      position: null,
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    },
    {
      id: "node-b",
      name: "Beta",
      description: "Target node",
      nodeTypeId: "team",
      createDate: "2026-02-01",
      deleteDate: "2026-10-01",
      position: null,
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    }
  ],
  edges: [
    {
      id: "edge-a",
      name: "Reports to",
      description: "",
      edgeTypeId: "reports",
      sourceNodeId: "node-a",
      targetNodeId: "node-b",
      createDate: "2026-03-01",
      deleteDate: "2026-10-01",
      attributes: {}
    }
  ]
};

const catalog: structureApi.GraphTypeCatalogDto = {
  nodeTypes: [
    {
      id: "person",
      name: "Person",
      displayName: "Person",
      color: "#fecdc2",
      shape: "rectangle",
      timeserieId: null,
      timeserieSecondaryId: null,
      timeserieIdRule: null
    },
    {
      id: "team",
      name: "Team",
      displayName: "Team",
      color: "#d9f99d",
      shape: "ellipse",
      timeserieId: null,
      timeserieSecondaryId: null,
      timeserieIdRule: null
    }
  ],
  edgeTypes: [],
  allowedConnections: []
};

const events: eventsApi.EventDto[] = [
  {
    id: "launch",
    name: "Launch",
    targetDate: "2026-05-01",
    eventDetails: "Northern region"
  }
];

const timeseries: timeseriesApi.TimeserieDto[] = [
  {
    id: "revenue",
    name: "Revenue",
    description: "Monthly revenue",
    unit: "EUR",
    timeUnit: "month",
    valueUnit: "number",
    values: [
      { date: "2026-01-01", value: -1.5 },
      { date: "2026-06-01", value: 3.25 }
    ]
  },
  {
    id: "status",
    name: "Status",
    description: "Status text",
    unit: "",
    timeUnit: "month",
    valueUnit: "string",
    values: [{ date: "2026-01-01", value: "On track" }]
  },
  {
    id: "enabled",
    name: "Enabled",
    description: "Flag",
    unit: "",
    timeUnit: "month",
    valueUnit: "boolean",
    values: [{ date: "2026-01-01", value: true }]
  },
  {
    id: "empty",
    name: "Empty numeric",
    description: "",
    unit: "",
    timeUnit: "month",
    valueUnit: "number",
    values: [{ date: "bad-date", value: 2 }]
  }
];

function renderSummary(
  selectedScenario: WorkspaceScenarioSummary | null = scenario,
  selectedOrgState: WorkspaceOrgStateSummary | null = orgState
) {
  return render(
    <WorkspaceSelectionContext.Provider
      value={{
        selectedScenario,
        setSelectedScenario: vi.fn(),
        selectedOrgState,
        setSelectedOrgState: vi.fn(),
        setWorkspaceSelection: vi.fn()
      }}
    >
      <SummaryTab orgId="acme" />
    </WorkspaceSelectionContext.Provider>
  );
}

function withSelection(child: ReactElement, selectedScenario: WorkspaceScenarioSummary | null) {
  return (
    <WorkspaceSelectionContext.Provider
      value={{
        selectedScenario,
        setSelectedScenario: vi.fn(),
        selectedOrgState: null,
        setSelectedOrgState: vi.fn(),
        setWorkspaceSelection: vi.fn()
      }}
    >
      {child}
    </WorkspaceSelectionContext.Provider>
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

describe("SummaryTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(structureApi.fetchGraphHistory).mockResolvedValue(history);
    vi.mocked(structureApi.fetchGraphTypeCatalog).mockResolvedValue(catalog);
    vi.mocked(eventsApi.fetchEvents).mockResolvedValue(events);
    vi.mocked(timeseriesApi.fetchTimeseries).mockResolvedValue(timeseries);
  });

  it("shows a no-scenario state without requiring an organisation state", () => {
    renderSummary(null, null);
    expect(screen.getByRole("heading", { name: "Summary" })).toBeInTheDocument();
    expect(screen.getByText(/Select a scenario/)).toBeInTheDocument();
    expect(structureApi.fetchGraphHistory).not.toHaveBeenCalled();
  });

  it("starts all scenario requests concurrently and renders the shared timeline", async () => {
    const historyRequest = deferred<structureApi.GraphHistoryDto>();
    const catalogRequest = deferred<structureApi.GraphTypeCatalogDto>();
    const eventsRequest = deferred<eventsApi.EventDto[]>();
    const timeseriesRequest = deferred<timeseriesApi.TimeserieDto[]>();
    vi.mocked(structureApi.fetchGraphHistory).mockReturnValue(historyRequest.promise);
    vi.mocked(structureApi.fetchGraphTypeCatalog).mockReturnValue(catalogRequest.promise);
    vi.mocked(eventsApi.fetchEvents).mockReturnValue(eventsRequest.promise);
    vi.mocked(timeseriesApi.fetchTimeseries).mockReturnValue(timeseriesRequest.promise);

    renderSummary(scenario, null);
    expect(screen.getByText("Loading summary timeline…")).toBeInTheDocument();
    expect(structureApi.fetchGraphHistory).toHaveBeenCalledTimes(1);
    expect(structureApi.fetchGraphTypeCatalog).toHaveBeenCalledTimes(1);
    expect(eventsApi.fetchEvents).toHaveBeenCalledTimes(1);
    expect(timeseriesApi.fetchTimeseries).toHaveBeenCalledTimes(1);

    historyRequest.resolve(history);
    catalogRequest.resolve(catalog);
    eventsRequest.resolve(events);
    timeseriesRequest.resolve(timeseries);

    expect(await screen.findByRole("heading", { name: "Future plan" })).toBeInTheDocument();
    expect(
      await screen.findByText("Timeline: 2026-01-01 ... 2026-11-30 | rows: 8")
    ).toBeInTheDocument();
    expect(screen.getAllByTitle(/Alpha · Person · 2026-01-01/)).toHaveLength(2);
    expect(screen.getAllByTitle(/Reports to · node-a → node-b/)).toHaveLength(2);
    expect(screen.getAllByTitle(/Launch · 2026-05-01/)).toHaveLength(2);
    expect(
      screen.getByRole("img", { name: /Revenue numeric timeseries chart/ })
    ).toBeInTheDocument();
    expect(screen.getByText("Y min = -1.5 max = 3.25")).toBeInTheDocument();
    expect(document.querySelectorAll(".summary-timeline-row--numeric-timeserie")).toHaveLength(1);
    expect(screen.getByText("string timeseries are not plotted.")).toBeInTheDocument();
    expect(screen.getByText("boolean timeseries are not plotted.")).toBeInTheDocument();
    expect(screen.getByText("No numeric values to plot.")).toBeInTheDocument();
  });

  it("fits the initial zoom to the mounted timeline viewport", async () => {
    const clientWidth = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(420);

    try {
      renderSummary();
      await screen.findByText("Alpha (Person)");

      expect(
        Number((screen.getByLabelText("Timeline zoom level") as HTMLInputElement).value)
      ).toBeCloseTo(420 / 334, 5);
    } finally {
      clientWidth.mockRestore();
    }
  });

  it("aborts old requests and prevents stale scenario responses", async () => {
    const firstHistory = deferred<structureApi.GraphHistoryDto>();
    vi.mocked(structureApi.fetchGraphHistory)
      .mockReturnValueOnce(firstHistory.promise)
      .mockResolvedValueOnce({ nodes: [], edges: [] });
    const view = render(withSelection(<SummaryTab orgId="acme" />, scenario));
    const firstSignal = vi.mocked(structureApi.fetchGraphHistory).mock.calls[0][2];

    view.rerender(withSelection(<SummaryTab orgId="acme" />, { id: "second", name: "Second" }));
    expect(firstSignal?.aborted).toBe(true);
    expect(await screen.findByRole("heading", { name: "Second" })).toBeInTheDocument();

    firstHistory.resolve(history);
    await Promise.resolve();
    expect(screen.queryAllByTitle(/Alpha · Person · 2026-01-01/)).toHaveLength(0);
  });

  it("shows load errors and retries with Refresh behavior", async () => {
    vi.mocked(structureApi.fetchGraphHistory)
      .mockRejectedValueOnce(new Error("History unavailable"))
      .mockResolvedValueOnce(history);
    renderSummary();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load summary. History unavailable"
    );
    fireEvent.click(within(screen.getByRole("alert")).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Alpha (Person)")).toBeInTheDocument();
    expect(structureApi.fetchGraphHistory).toHaveBeenCalledTimes(2);
  });

  it("applies filters, row visibility, collapsing, popovers, zoom, scrolling and resizing", async () => {
    const { container } = renderSummary();
    await screen.findByText("Alpha (Person)");

    const filtersButton = screen.getByRole("button", { name: "Filters" });
    expect(filtersButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(filtersButton);
    expect(filtersButton).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByLabelText("Nodes and their edges"));
    expect(screen.queryByText("Alpha (Person)")).not.toBeInTheDocument();
    expect(screen.queryByText("Reports to (Edge)")).not.toBeInTheDocument();
    expect(screen.getByText("Event: Launch")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Nodes and their edges"));

    const rowsButton = screen.getByRole("button", { name: "Rows" });
    fireEvent.click(rowsButton);
    expect(filtersButton).toHaveAttribute("aria-expanded", "false");
    expect(rowsButton).toHaveAttribute("aria-expanded", "true");
    const rowsMenu = screen.getByLabelText("Row visibility");
    fireEvent.click(within(rowsMenu).getByRole("button", { name: "None" }));
    expect(screen.getByText("No timeline rows match the current filters.")).toBeInTheDocument();
    expect(screen.queryAllByTitle(/Alpha · Person · 2026-01-01/)).toHaveLength(0);
    fireEvent.click(within(rowsMenu).getByRole("button", { name: "All" }));
    expect(screen.getAllByTitle(/Alpha · Person · 2026-01-01/)).toHaveLength(2);

    fireEvent.click(screen.getByLabelText("Alpha (Person)"));
    expect(screen.queryAllByTitle(/Alpha · Person · 2026-01-01/)).toHaveLength(0);
    fireEvent.click(screen.getByLabelText("Alpha (Person)"));
    expect(screen.getAllByTitle(/Alpha · Person · 2026-01-01/)).toHaveLength(2);

    fireEvent.click(filtersButton);
    expect(filtersButton).toHaveAttribute("aria-expanded", "true");
    expect(rowsButton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("Row visibility")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Collapse Alpha (Person) row" }));
    expect(screen.getByRole("button", { name: "Expand Alpha (Person) row" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
    expect(screen.getAllByTitle(/Alpha · Person · 2026-01-01/)).toHaveLength(1);

    fireEvent.click(rowsButton);
    const reopenedRowsMenu = screen.getByLabelText("Row visibility");
    fireEvent.click(within(reopenedRowsMenu).getByLabelText("Alpha (Person)"));
    expect(screen.queryAllByTitle(/Alpha · Person · 2026-01-01/)).toHaveLength(0);
    fireEvent.click(within(reopenedRowsMenu).getByLabelText("Alpha (Person)"));
    expect(screen.getByRole("button", { name: "Collapse Alpha (Person) row" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
    expect(screen.getAllByTitle(/Alpha · Person · 2026-01-01/)).toHaveLength(2);

    const rows = container.querySelector(".summary-timeline-rows") as HTMLDivElement;
    const zoom = screen.getByLabelText("Timeline zoom level");
    const oldZoom = Number((zoom as HTMLInputElement).value);
    const zoomIn = screen.getByRole("button", { name: "Zoom in timeline" });
    expect(zoomIn.nextElementSibling).toBe(zoom);
    fireEvent.click(zoomIn);
    expect(Number((zoom as HTMLInputElement).value)).toBeGreaterThan(oldZoom);
    expect(container.querySelectorAll(".summary-grid-line")).toHaveLength(0);
    fireEvent.change(zoom, { target: { value: "0.3" } });
    expect(screen.getByLabelText("Timeline zoom scale")).toHaveTextContent("1 pixel / 3.3 days");
    expect(screen.getByText("2026")).toBeInTheDocument();
    expect(screen.queryByText("Feb")).not.toBeInTheDocument();
    expect(container.querySelectorAll(".summary-grid-line").length).toBeGreaterThan(0);
    expect(container.querySelector(".summary-month-marker--year")).toBeInTheDocument();
    expect(container.querySelector(".summary-grid-line--year")).toBeInTheDocument();
    fireEvent.change(zoom, { target: { value: "3" } });
    expect(screen.getByText("2026 Feb")).toBeInTheDocument();
    expect(container.querySelectorAll(".summary-grid-line")).toHaveLength(0);
    fireEvent.change(zoom, { target: { value: "80" } });
    rows.scrollLeft = 80;
    fireEvent.click(screen.getByRole("button", { name: "Zoom to fit" }));
    expect(Number((zoom as HTMLInputElement).value)).toBeLessThan(80);
    expect(rows.scrollLeft).toBe(0);

    fireEvent.change(screen.getByLabelText("Resize all timeseries rows"), {
      target: { value: "140" }
    });
    expect(screen.getByTitle(/Revenue · revenue/)).toHaveStyle({ height: "140px" });

    const labels = container.querySelector(".summary-labels") as HTMLDivElement;
    const header = container.querySelector(".summary-timeline-header-scroll") as HTMLDivElement;
    const bottom = container.querySelector(".summary-bottom-scrollbar") as HTMLDivElement;
    rows.scrollLeft = 80;
    rows.scrollTop = 60;
    fireEvent.scroll(rows);
    expect(header.scrollLeft).toBe(80);
    expect(bottom.scrollLeft).toBe(80);
    expect(labels.scrollTop).toBe(60);
  });

  it("scrolls the timeline horizontally by primary-pointer dragging", async () => {
    class PointerEventMock extends MouseEvent {
      pointerId: number;

      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init);
        this.pointerId = init.pointerId ?? 0;
      }
    }
    vi.stubGlobal("PointerEvent", PointerEventMock);

    const { container } = renderSummary();
    await screen.findByText("Alpha (Person)");

    const rows = container.querySelector(".summary-timeline-rows") as HTMLDivElement;
    const header = container.querySelector(".summary-timeline-header-scroll") as HTMLDivElement;
    const bottom = container.querySelector(".summary-bottom-scrollbar") as HTMLDivElement;
    rows.scrollLeft = 80;

    fireEvent.pointerDown(rows, { button: 0, pointerId: 7, clientX: 200 });
    expect(rows).toHaveClass("summary-timeline-rows--dragging");
    fireEvent.pointerMove(rows, { pointerId: 7, clientX: 150 });
    expect(rows.scrollLeft).toBe(130);
    expect(header.scrollLeft).toBe(130);
    expect(bottom.scrollLeft).toBe(130);

    fireEvent.pointerUp(rows, { pointerId: 7, clientX: 150 });
    expect(rows).not.toHaveClass("summary-timeline-rows--dragging");
    fireEvent.pointerMove(rows, { pointerId: 7, clientX: 100 });
    expect(rows.scrollLeft).toBe(130);

    fireEvent.pointerDown(rows, { button: 1, pointerId: 8, clientX: 100 });
    fireEvent.pointerMove(rows, { pointerId: 8, clientX: 50 });
    expect(rows.scrollLeft).toBe(130);

    fireEvent.pointerDown(rows, { button: 0, pointerId: 9, clientX: 100 });
    fireEvent.pointerCancel(rows, { pointerId: 9 });
    fireEvent.pointerMove(rows, { pointerId: 9, clientX: 50 });
    expect(rows.scrollLeft).toBe(130);
    vi.unstubAllGlobals();
  });

  it("exposes nearest numeric point details on hover", async () => {
    renderSummary();
    const chart = await screen.findByRole("img", {
      name: /Revenue numeric timeseries chart/
    });
    const firstPoint = chart.querySelector(".summary-chart__point") as SVGCircleElement;
    const pointX = Number(firstPoint.getAttribute("cx"));
    const pointY = Number(firstPoint.getAttribute("cy"));
    fireEvent.mouseMove(chart, { clientX: pointX, clientY: pointY });
    const firstTooltip = screen.getByText("2026-01-01: -1.5 EUR");
    expect(firstTooltip).toBeInTheDocument();
    expect(chart.querySelector("title")).not.toBeInTheDocument();
    const chartContainer = chart.closest(".summary-chart") as HTMLDivElement;
    fireEvent.mouseMove(firstTooltip, {
      clientX: pointX,
      clientY: pointY
    });
    expect(screen.getByText("2026-01-01: -1.5 EUR")).toBeInTheDocument();
    fireEvent.mouseMove(chart, { clientX: pointX, clientY: pointY + 41 });
    expect(screen.queryByText("2026-01-01: -1.5 EUR")).not.toBeInTheDocument();
    const secondPoint = chart.querySelectorAll(".summary-chart__point")[1] as SVGCircleElement;
    const secondPointX = Number(secondPoint.getAttribute("cx"));
    const secondPointY = Number(secondPoint.getAttribute("cy"));
    const timelineViewport = chart.closest(".summary-timeline-rows") as HTMLDivElement;
    Object.defineProperty(timelineViewport, "clientWidth", {
      configurable: true,
      value: 100
    });
    timelineViewport.scrollLeft = Math.max(0, secondPointX - 90);
    fireEvent.mouseMove(chart, { clientX: secondPointX, clientY: secondPointY });
    expect(screen.getByText("2026-06-01: 3.25 EUR")).toHaveClass("summary-chart__tooltip--right");
    fireEvent.mouseLeave(chartContainer);
    expect(screen.queryByText("2026-06-01: 3.25 EUR")).not.toBeInTheDocument();
  });
});
