import { describe, expect, it } from "vitest";
import { buildPredictionMetricCharts, formatModelKind, predictionChartAxisTicks, predictionIntervalBandPath, predictionVersionStatus } from "./predictionChart";
import type { PredictionVersionDetailDto } from "../../api/predictions";

const version = (
  id: string,
  name: string,
  value: number,
  scenarioId = "future"
): PredictionVersionDetailDto => ({
  id, name, startDate: "2026-01-01", endDate: "2026-02-01", cutoffMode: "asOfStart", confidenceLevel: 80,
  createdTime: "2026-01-01T00:00:00Z", modelConfiguration: {}, targets: [{
    scenarioId, metricId: "revenue", metricName: "Revenue",
    timeUnit: "month", unit: "EUR", status: "eligible", reason: null, seasonalPeriod: null,
    seasonalPeriodSource: null, sourceSnapshot: {}, inputSnapshot: {}, results: [{
      kind: "naive", status: "available", reason: null, predictionIntervalStatus: "not_applicable", predictionIntervalReason: null, crossValidationStatus: "unavailable",
      crossValidationMae: null, configuration: {}, points: [{ date: "2026-01-01", value, lowerBound: null, upperBound: null }, { date: "2026-02-01", value: value + 1, lowerBound: null, upperBound: null }]
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

  it("keeps a Reality-targeted saved prediction distinct from live Reality", () => {
    const charts = buildPredictionMetricCharts({
      versions: [version("reality-version", "Reality forecast", 10, "reality")],
      selectedVersionIds: new Set(["reality-version"]), selectedScenarioIds: new Set(["reality"]),
      selectedModelKinds: new Set(["naive"]), selectedMetricIds: new Set(["revenue"]),
      scenarioNames: new Map([["reality", "Reality"]]), startDate: "2026-01-01", endDate: "2026-02-01",
      includeReality: true,
      realityTimeseries: [{ id: "revenue", name: "Revenue", description: "", unit: "EUR", timeUnit: "month", valueUnit: "number", values: [{ date: "2026-01-01", value: 9 }] }]
    });

    expect(charts[0].lines.map((line) => [line.id, line.label])).toEqual([
      ["reality:revenue", "Current Reality · manually entered realized data · Revenue"],
      ["reality-version:reality:revenue:naive", "Reality forecast · Reality · naive"]
    ]);
    expect(charts[0].lines[0].provenance).toMatch(/not part of the saved prediction/i);
    expect(charts[0].lines[1].provenance).toMatch(/saved prediction/i);
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

  it("preserves complete bounds through filtering and builds a closed upper-then-lower band", () => {
    const withInterval = version("one", "First version", 10);
    withInterval.confidenceLevel = 90;
    withInterval.targets[0].results[0] = {
      ...withInterval.targets[0].results[0],
      kind: "mlforecast",
      predictionIntervalStatus: "available",
      points: [
        { date: "2026-01-01", value: 10, lowerBound: 8, upperBound: 12 },
        { date: "2026-02-01", value: 11, lowerBound: 9, upperBound: 13 }
      ]
    };
    const charts = buildPredictionMetricCharts({
      versions: [withInterval], selectedVersionIds: new Set(["one"]), selectedScenarioIds: new Set(["future"]),
      selectedModelKinds: new Set(["mlforecast"]), selectedMetricIds: new Set(["revenue"]),
      scenarioNames: new Map([["future", "Future plan"]]), startDate: "2026-02-01", endDate: "2026-02-01",
      includeReality: false, realityTimeseries: []
    });

    expect(charts[0].lines[0].points).toEqual([{ date: "2026-02-01", value: 11, lowerBound: 9, upperBound: 13 }]);
    expect(charts[0].lines[0].provenance).toMatch(/90% prediction interval/i);
    expect(predictionIntervalBandPath(withInterval.targets[0].results[0].points, (date) => date === "2026-01-01" ? 1 : 2, (value) => value)).toBe("M1 12 L2 13 L2 9 L1 8 Z");
  });

  it("does not construct a partial prediction band", () => {
    expect(predictionIntervalBandPath([
      { date: "2026-01-01", value: 10, lowerBound: 8, upperBound: 12 },
      { date: "2026-02-01", value: 11, lowerBound: null, upperBound: null }
    ], () => 0, (value) => value)).toBeNull();
  });

  it("keeps an unavailable fitted result as an unbanded line with its safe reason", () => {
    const unavailable = version("one", "First version", 10);
    unavailable.targets[0].results[0] = {
      ...unavailable.targets[0].results[0],
      kind: "sarima",
      predictionIntervalStatus: "unavailable",
      predictionIntervalReason: "SARIMA prediction interval is unavailable."
    };
    const charts = buildPredictionMetricCharts({
      versions: [unavailable], selectedVersionIds: new Set(["one"]), selectedScenarioIds: new Set(["future"]),
      selectedModelKinds: new Set(["sarima"]), selectedMetricIds: new Set(["revenue"]),
      scenarioNames: new Map([["future", "Future plan"]]), startDate: "", endDate: "",
      includeReality: false, realityTimeseries: []
    });

    expect(charts[0].lines[0].predictionIntervalStatus).toBe("unavailable");
    expect(charts[0].lines[0].provenance).toContain("SARIMA prediction interval is unavailable.");
  });
});
