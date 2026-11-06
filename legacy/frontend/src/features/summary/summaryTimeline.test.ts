import { describe, expect, it } from "vitest";
import type { EventDto } from "../../api/events";
import type { GraphHistoryDto, GraphTypeCatalogDto } from "../../api/orgTwinStructure";
import type { TimeserieDto } from "../../api/timeseries";
import {
  MAX_PIXELS_PER_DAY,
  MIN_PIXELS_PER_DAY,
  buildTimelineRows,
  calculateChartScale,
  calculateTimelineBounds,
  clampZoom,
  filterTimelineRows,
  fitZoom,
  monthMarkers,
  numericTimeserieValues,
  parseTimelineDate,
  shouldShowYearAndMonthHeader,
  shouldUseYearOnlyHeader,
  yearMarkers
} from "./summaryTimeline";

const history: GraphHistoryDto = {
  nodes: [
    {
      id: "node-z",
      name: "Zulu",
      description: "",
      nodeTypeId: "type-z",
      createDate: "2026-04-01",
      deleteDate: null,
      position: null,
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    },
    {
      id: "node-a",
      name: "Alpha",
      description: "",
      nodeTypeId: "type-a",
      createDate: "2026-01-15",
      deleteDate: "2026-08-01",
      position: null,
      attributes: {},
      timeserieId: null,
      timeserieSecondaryId: null
    }
  ],
  edges: [
    {
      id: "edge-b",
      name: "Zulu link",
      description: "",
      edgeTypeId: "edge-type",
      sourceNodeId: "node-a",
      targetNodeId: "node-z",
      createDate: "2026-02-01",
      deleteDate: "2026-08-01",
      attributes: {}
    },
    {
      id: "edge-a",
      name: "Alpha link",
      description: "",
      edgeTypeId: "edge-type",
      sourceNodeId: "node-a",
      targetNodeId: "node-z",
      createDate: "bad-date",
      deleteDate: null,
      attributes: {}
    }
  ]
};

const catalog: GraphTypeCatalogDto = {
  nodeTypes: [
    {
      id: "type-z",
      name: "z",
      displayName: "Zulu type",
      color: "#000000",
      shape: null,
      timeserieId: null,
      timeserieSecondaryId: null,
      timeserieIdRule: null
    },
    {
      id: "type-a",
      name: "a",
      displayName: "Alpha type",
      color: "#ffffff",
      shape: null,
      timeserieId: null,
      timeserieSecondaryId: null,
      timeserieIdRule: null
    }
  ],
  edgeTypes: [],
  allowedConnections: []
};

const events: EventDto[] = [
  { id: "event-z", name: "Zulu event", targetDate: "2026-03-01", eventDetails: "" },
  { id: "event-a", name: "Alpha event", targetDate: "2026-03-01", eventDetails: "Details" }
];

const timeseries: TimeserieDto[] = [
  {
    id: "z-series",
    name: "Zulu series",
    description: "",
    unit: "EUR",
    timeUnit: "month",
    valueUnit: "number",
    values: [{ date: "2026-07-01", value: 1.25 }]
  },
  {
    id: "a-series",
    name: "Alpha series",
    description: "",
    unit: "",
    timeUnit: "month",
    valueUnit: "string",
    values: [{ date: "invalid", value: "ok" }]
  }
];

describe("summary timeline helpers", () => {
  it("orders nodes, outgoing edges, events and timeseries deterministically", () => {
    const rows = buildTimelineRows(history, catalog, events, timeseries);
    expect(rows.map((row) => row.id)).toEqual([
      "node:node-a",
      "edge:edge-a",
      "edge:edge-b",
      "node:node-z",
      "event:event-a",
      "event:event-z",
      "timeserie:a-series",
      "timeserie:z-series"
    ]);
    expect(rows.map((row) => row.label)).toEqual([
      "Alpha (Alpha type)",
      "Alpha link (Edge)",
      "Zulu link (Edge)",
      "Zulu (Zulu type)",
      "Event: Alpha event",
      "Event: Zulu event",
      "Timeserie: Alpha series",
      "Timeserie: Zulu series"
    ]);
    expect(rows.find((row) => row.id === "node:node-a")?.details).toBe(
      "Alpha · Alpha type · 2026-01-15 – 2026-08-01"
    );
    expect(rows.find((row) => row.id === "edge:edge-b")?.details).toBe(
      "Zulu link · node-a → node-z · 2026-02-01 – 2026-08-01"
    );
    expect(rows.find((row) => row.id === "event:event-a")?.details).toBe(
      "Alpha event · 2026-03-01 · Details"
    );
  });

  it("filters categories and endpoint node types", () => {
    const rows = buildTimelineRows(history, catalog, events, timeseries);
    const filtered = filterTimelineRows(rows, {
      nodes: true,
      edges: true,
      events: false,
      timeseries: true,
      nodeTypeIds: new Set(["type-a"])
    });
    expect(filtered.map((row) => row.id)).toEqual([
      "node:node-a",
      "timeserie:a-series",
      "timeserie:z-series"
    ]);
  });

  it("builds date bounds from valid data and expands through the following month", () => {
    const rows = buildTimelineRows(history, catalog, events, timeseries);
    const bounds = calculateTimelineBounds(rows, "2026-10-20");
    expect(bounds.start.toISOString().slice(0, 10)).toBe("2026-01-15");
    expect(bounds.end.toISOString().slice(0, 10)).toBe("2026-11-30");
    expect(parseTimelineDate("2026-02-30")).toBeNull();
    expect(parseTimelineDate("garbage")).toBeNull();
  });

  it("uses a current-month fallback when represented dates are malformed", () => {
    const bounds = calculateTimelineBounds([], null, new Date("2026-08-03T12:00:00Z"));
    expect(bounds.start.toISOString().slice(0, 10)).toBe("2026-08-01");
    expect(bounds.end.toISOString().slice(0, 10)).toBe("2026-09-30");
  });

  it("uses the year for January and abbreviated names for other months", () => {
    const bounds = {
      start: new Date("2025-12-15T00:00:00Z"),
      end: new Date("2026-02-28T00:00:00Z"),
      dayCount: 76
    };
    expect(monthMarkers(bounds).map((marker) => marker.label)).toEqual(["Dec", "2026", "Feb"]);
    expect(monthMarkers(bounds, true).map((marker) => marker.label)).toEqual([
      "2025 Dec",
      "2026 Jan",
      "2026 Feb"
    ]);
  });

  it("switches to year columns when month labels no longer fit", () => {
    const bounds = {
      start: new Date("2025-01-01T00:00:00Z"),
      end: new Date("2026-02-28T00:00:00Z"),
      dayCount: 424
    };
    expect(shouldUseYearOnlyHeader(bounds, 2)).toBe(false);
    expect(shouldUseYearOnlyHeader(bounds, 0.5)).toBe(true);
    expect(shouldShowYearAndMonthHeader(bounds, 2)).toBe(false);
    expect(shouldShowYearAndMonthHeader(bounds, 3)).toBe(true);
    expect(yearMarkers(bounds).map((marker) => marker.label)).toEqual(["2025", "2026"]);
  });

  it("rounds chart scales for positive, negative, mixed, zero and fractional values", () => {
    expect(calculateChartScale([2, 8])).toMatchObject({ min: 0, max: 8 });
    expect(calculateChartScale([-8, -2])).toMatchObject({ min: -8, max: 0 });
    expect(calculateChartScale([-2, 3])).toMatchObject({ min: -2, max: 4 });
    expect(calculateChartScale([0])).toEqual({ min: -1, max: 1, ticks: [-1, 0, 1] });
    expect(calculateChartScale([0.05, 0.12])).toMatchObject({ min: 0, max: 0.15 });
  });

  it("extracts only valid numeric points and constrains fitting and manual zoom", () => {
    const series: TimeserieDto = {
      ...timeseries[1],
      valueUnit: "number",
      values: [
        { date: "2026-01-01", value: 1 },
        { date: "bad", value: 2 },
        { date: "2026-03-01", value: "not a number" }
      ]
    };
    expect(numericTimeserieValues(series)).toHaveLength(1);
    expect(clampZoom(0)).toBe(MIN_PIXELS_PER_DAY);
    expect(clampZoom(100)).toBe(MAX_PIXELS_PER_DAY);
    expect(fitZoom(700, 100)).toBe(7);
  });
});
