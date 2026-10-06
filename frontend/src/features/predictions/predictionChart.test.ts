import { describe, expect, it } from "vitest";
import { buildPredictionMetricCharts, formatModelKind, predictionChartAxisTicks, predictionIntervalBandPath, predictionVersionModelKinds, predictionVersionStatus } from "./predictionChart";
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
      "First version · Future plan · Naive",
      "Second version · Future plan · Naive"
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
      ["reality-version:reality:revenue:naive", "Reality forecast · Reality · Naive"]
    ]);
    expect(charts[0].lines[0].provenance).toMatch(/not part of the saved prediction/i);
    expect(charts[0].lines[1].provenance).toMatch(/saved prediction/i);
  });

  it("identifies selected models without points in the chosen date range", () => {
    const ranBoth = { ...version("one", "First version", 10), modelConfiguration: { modelKinds: ["naive", "seasonal_naive"] } };
    const charts = buildPredictionMetricCharts({
      versions: [ranBoth],
      selectedVersionIds: new Set(["one"]), selectedScenarioIds: new Set(["future"]),
      selectedModelKinds: new Set(["naive", "seasonal_naive"]), selectedMetricIds: new Set(["revenue"]),
      scenarioNames: new Map([["future", "Future plan"]]), startDate: "2026-03-01", endDate: "2026-03-31",
      includeReality: false, realityTimeseries: []
    });

    expect(charts[0].lines).toEqual([]);
    expect(charts[0].missingModelKinds).toEqual(["naive", "seasonal_naive"]);
  });

  it("labels known model kinds and falls back to spaced unknown kinds", () => {
    expect(["naive", "seasonal_naive", "average", "mlforecast", "sarima", "prophet", "custom_kind"].map(formatModelKind))
      .toEqual(["Naive", "Seasonal naive", "Average", "MLForecast", "SARIMA", "Prophet", "custom kind"]);
  });

  it("reads recorded version models and falls back to saved result kinds", () => {
    const legacy = version("legacy", "Legacy", 10);
    legacy.targets[0].results.push({ ...legacy.targets[0].results[0], kind: "average", status: "ineligible", points: [] });
    expect(predictionVersionModelKinds(legacy)).toEqual(["naive", "average"]);
    expect(predictionVersionModelKinds({ ...legacy, modelConfiguration: { modelKinds: ["prophet", "naive"] } }))
      .toEqual(["naive", "prophet"]);
  });

  it("reports missing results only for models that a plotted version ran", () => {
    const allKinds = ["naive", "seasonal_naive", "average", "mlforecast", "sarima", "prophet"];
    const subset = { ...version("subset", "Subset", 10), modelConfiguration: { modelKinds: ["naive", "prophet"] } };
    subset.targets[0].results.push({
      ...subset.targets[0].results[0], kind: "prophet", status: "ineligible",
      reason: "Prophet needs at least 12 contiguous observations.", points: []
    });
    const full = { ...version("full", "Full", 20), modelConfiguration: { modelKinds: allKinds } };
    const chartArgs = {
      versions: [subset, full], selectedVersionIds: new Set(["subset"]), selectedScenarioIds: new Set(["future"]),
      selectedModelKinds: new Set(allKinds), selectedMetricIds: new Set(["revenue"]),
      scenarioNames: new Map([["future", "Future plan"]]), startDate: "", endDate: "",
      includeReality: false, realityTimeseries: []
    };

    const [subsetChart] = buildPredictionMetricCharts(chartArgs);
    expect(subsetChart.lines.map((line) => line.modelKind)).toEqual(["naive"]);
    expect(subsetChart.missingModelKinds).toEqual(["prophet"]);
    expect(subsetChart.notRunModelKinds).toEqual(["seasonal_naive", "average", "mlforecast", "sarima"]);

    chartArgs.selectedVersionIds.add("full");
    const [combinedChart] = buildPredictionMetricCharts(chartArgs);
    expect(combinedChart.missingModelKinds)
      .toEqual(["seasonal_naive", "average", "mlforecast", "sarima", "prophet"]);
    expect(combinedChart.notRunModelKinds).toEqual([]);
  });

  it("gives Prophet its own line style", () => {
    const prophet = version("one", "First version", 10);
    prophet.targets[0].results[0] = { ...prophet.targets[0].results[0], kind: "prophet" };
    const [chart] = buildPredictionMetricCharts({
      versions: [prophet, version("two", "Second version", 20)], selectedVersionIds: new Set(["one", "two"]),
      selectedScenarioIds: new Set(["future"]), selectedModelKinds: new Set(["naive", "prophet"]),
      selectedMetricIds: new Set(["revenue"]), scenarioNames: new Map([["future", "Future plan"]]),
      startDate: "", endDate: "", includeReality: false, realityTimeseries: []
    });

    expect(chart.lines.map((line) => [line.label, line.strokeDasharray])).toEqual([
      ["First version · Future plan · Prophet", "10 3 2 3"],
      ["Second version · Future plan · Naive", "7 4"]
    ]);
  });

  it("formats dates as MM-dd and marks later year boundaries", () => {
    expect(predictionChartAxisTicks(["2026-12-31", "2027-01-01", "2027-02-15"])).toEqual([
      { date: "2026-12-31", label: "12-31", isFirst: true, isYearBoundary: false, year: "2026", showDateLabel: true, showYearLabel: true },
      { date: "2027-01-01", label: "01-01", isFirst: false, isYearBoundary: true, year: "2027", showDateLabel: true, showYearLabel: true },
      { date: "2027-02-15", label: "02-15", isFirst: false, isYearBoundary: false, year: "2027", showDateLabel: true, showYearLabel: false }
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


describe("prediction chart readability", () => {
  it.each([0, 1, 22, 23, 100, 365])("spaces labels without losing points for %i dates", (count) => {
    const dates = Array.from({ length: count }, (_, index) =>
      new Date(Date.UTC(2025, 11, 31 + index)).toISOString().slice(0, 10));
    const ticks = predictionChartAxisTicks(dates);
    const labels = ticks.filter((tick) => tick.showDateLabel);
    expect(ticks.map((tick) => tick.date)).toEqual(dates);
    expect(labels.length).toBeLessThanOrEqual(22);
    if (!count) return;
    expect(labels[0].date).toBe(dates[0]);
    expect(labels.at(-1)?.date).toBe(dates.at(-1));
    for (let index = 1; index < labels.length; index++) {
      const gap = dates.indexOf(labels[index].date) - dates.indexOf(labels[index - 1].date);
      expect(gap * 646 / (count - 1)).toBeGreaterThanOrEqual(36);
    }
    if (count > 1) expect(ticks[1].isYearBoundary).toBe(true);
    if (count >= 22) expect(ticks[1].showYearLabel).toBe(false);
  });

  const args = () => ({
    versions: [version("one", "First version", 10)],
    selectedVersionIds: new Set(["one"]), selectedScenarioIds: new Set(["future"]),
    selectedModelKinds: new Set(["naive"]), selectedMetricIds: new Set(["revenue"]),
    scenarioNames: new Map([["future", "Future plan"]]), startDate: "", endDate: "",
    includeReality: true,
    realityTimeseries: [{ id: "revenue", name: "Revenue", description: "", unit: "EUR",
      timeUnit: "month" as const, valueUnit: "number" as const,
      values: ["2025-12-01", "2026-01-01", "2026-02-01", "2026-03-01"].map((date) => ({ date, value: 9 })) }]
  });

  it.each([
    ["", "", ["2026-01-01", "2026-02-01"]],
    ["2025-12-01", "", ["2025-12-01", "2026-01-01", "2026-02-01"]],
    ["", "2026-03-01", ["2026-01-01", "2026-02-01", "2026-03-01"]],
    ["2026-02-01", "2026-02-01", ["2026-02-01"]]
  ])("filters both layers with independent plot overrides %s–%s", (startDate, endDate, expected) => {
    const chart = buildPredictionMetricCharts({ ...args(), startDate, endDate })[0];
    expect(chart.lines[0].points.map((point) => point.date)).toEqual(expected);
    expect(chart.lines[1].points.map((point) => point.date)).toEqual(
      ["2026-01-01", "2026-02-01"].filter((date) => expected.includes(date)));
    expect(chart.realityMessage).toBeNull();
  });

  it("uses only selected versions with matching metrics and scenarios for each range", () => {
    const input = args();
    const later = { ...version("two", "Later", 20), startDate: "2026-02-01", endDate: "2026-03-01" };
    const otherScenario = { ...version("other", "Other", 20, "excluded"), startDate: "2025-01-01" };
    const otherMetric = { ...version("metric", "Other metric", 20), startDate: "2025-01-01" };
    otherMetric.targets[0].metricId = "cost";
    input.versions.push(later, otherScenario, otherMetric);
    input.selectedVersionIds = new Set(["one", "two", "other", "metric"]);
    expect(buildPredictionMetricCharts(input)[0].lines[0].points.map((point) => point.date))
      .toEqual(["2026-01-01", "2026-02-01", "2026-03-01"]);
    input.selectedVersionIds.delete("two");
    expect(buildPredictionMetricCharts(input)[0].lines[0].points).toHaveLength(2);
    input.selectedModelKinds.clear();
    expect(buildPredictionMetricCharts(input)[0].lines[0].points).toHaveLength(2);
  });

  it("distinguishes missing matching Reality from observations outside the displayed period", () => {
    const input = args();
    input.realityTimeseries[0].id = "different-metric";
    expect(buildPredictionMetricCharts(input)[0].realityMessage).toMatch(/No matching numeric/);
    input.realityTimeseries[0].id = "revenue";
    input.realityTimeseries[0].values = [{ date: "2025-12-01", value: 9 }];
    expect(buildPredictionMetricCharts(input)[0].realityMessage).toMatch(/No current Reality observations/);
    input.includeReality = false;
    const chart = buildPredictionMetricCharts(input)[0];
    expect(chart.realityMessage).toBeNull();
    expect(chart.lines.every((line) => line.kind === "prediction")).toBe(true);
  });
});
