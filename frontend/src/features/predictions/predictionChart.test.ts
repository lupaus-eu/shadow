import { describe, expect, it } from "vitest";
import { buildPredictionMetricCharts, formatModelKind, predictionChartAxisTicks, predictionVersionStatus } from "./predictionChart";
import type { PredictionVersionDetailDto } from "../../api/predictions";

const version = (id: string, name: string, value: number): PredictionVersionDetailDto => ({
  id, name, startDate: "2026-01-01", endDate: "2026-02-01", cutoffMode: "asOfStart",
  createdTime: "2026-01-01T00:00:00Z", modelConfiguration: {}, targets: [{
    scenarioId: "future", realityScenarioId: "reality", metricId: "revenue", metricName: "Revenue",
    timeUnit: "month", unit: "EUR", status: "eligible", reason: null, seasonalPeriod: null,
    seasonalPeriodSource: null, sourceSnapshot: {}, inputSnapshot: {}, results: [{
      kind: "naive", status: "available", reason: null, crossValidationStatus: "unavailable",
      crossValidationMae: null, configuration: {}, points: [{ date: "2026-01-01", value }, { date: "2026-02-01", value: value + 1 }]
    }]
  }]
});

describe("buildPredictionMetricCharts", () => {
  it("keeps overlapping saved versions and live Reality individually identifiable", () => {
    const charts = buildPredictionMetricCharts({
      versions: [version("one", "First version", 10), version("two", "Second version", 20)],
      selectedVersionIds: new Set(["one", "two"]), selectedScenarioIds: new Set(["future"]),
      selectedModelKinds: new Set(["naive"]), selectedMetricIds: new Set(["revenue"]),
      scenarioNames: new Map([["future", "Future plan"]]), startDate: "2026-01-01", endDate: "2026-02-01",
      includeReality: true,
      realityTimeseries: [{ id: "revenue", name: "Revenue", description: "", unit: "EUR", timeUnit: "month", valueUnit: "number", values: [{ date: "2026-01-01", value: 9 }] }]
    });

    expect(charts).toHaveLength(1);
    expect(charts[0].lines.map((line) => line.label)).toEqual([
      "Current Reality · manually entered realized data · Revenue",
      "First version · Future plan · naive",
      "Second version · Future plan · naive"
    ]);
    expect(charts[0].lines[0].provenance).toMatch(/manually entered realized data/i);
  });

  it("identifies selected models without points in the chosen date range", () => {
    const charts = buildPredictionMetricCharts({
      versions: [version("one", "First version", 10)],
      selectedVersionIds: new Set(["one"]), selectedScenarioIds: new Set(["future"]),
      selectedModelKinds: new Set(["naive", "seasonal_naive"]), selectedMetricIds: new Set(["revenue"]),
      scenarioNames: new Map([["future", "Future plan"]]), startDate: "2026-03-01", endDate: "2026-03-31",
      includeReality: false, realityTimeseries: []
    });

    expect(charts[0].lines).toEqual([]);
    expect(charts[0].missingModelKinds).toEqual(["naive", "seasonal_naive"]);
    expect(formatModelKind("seasonal_naive")).toBe("seasonal naive");
  });

  it("formats dates as MM-dd and marks later year boundaries", () => {
    expect(predictionChartAxisTicks(["2026-12-31", "2027-01-01", "2027-02-15"])).toEqual([
      { date: "2026-12-31", label: "12-31", isFirst: true, isYearBoundary: false, year: "2026" },
      { date: "2027-01-01", label: "01-01", isFirst: false, isYearBoundary: true, year: "2027" },
      { date: "2027-02-15", label: "02-15", isFirst: false, isYearBoundary: false, year: "2027" }
    ]);
  });

  it("recognises the backend's available result status as completed", () => {
    expect(predictionVersionStatus(version("one", "First version", 10))).toBe("Completed");
  });
});
