import {
  MODEL_KINDS,
  type PredictionTargetDto,
  type PredictionVersionDetailDto
} from "../../api/predictions";
import type { TimeserieDto } from "../../api/timeseries";

export type PredictionChartLine = {
  id: string;
  label: string;
  provenance: string;
  kind: "prediction" | "reality";
  modelKind?: string;
  strokeDasharray?: string;
  confidenceLevel?: number;
  predictionIntervalStatus?: "available" | "unavailable" | "not_applicable";
  points: Array<{
    date: string;
    value: number;
    lowerBound: number | null;
    upperBound: number | null;
  }>;
};

export type PredictionMetricChart = {
  metricId: string;
  metricName: string;
  unit: string;
  lines: PredictionChartLine[];
  missingModelKinds: string[];
  notRunModelKinds: string[];
  realityMessage: string | null;
};

const modelKindLabels: Record<string, string> = {
  naive: "Naive",
  seasonal_naive: "Seasonal naive",
  average: "Average",
  mlforecast: "MLForecast",
  sarima: "SARIMA",
  prophet: "Prophet"
};

const modelKindDashes: Record<string, string> = {
  naive: "7 4",
  average: "2 4",
  prophet: "10 3 2 3"
};

export function formatModelKind(kind: string): string {
  return modelKindLabels[kind] ?? kind.replaceAll("_", " ");
}

// Canonical kinds first, then any unknown kinds alphabetically.
export function sortModelKinds(kinds: Iterable<string>): string[] {
  const order = (kind: string) => {
    const index = (MODEL_KINDS as readonly string[]).indexOf(kind);
    return index === -1 ? MODEL_KINDS.length : index;
  };
  return [...new Set(kinds)].sort((left, right) => order(left) - order(right) || left.localeCompare(right));
}

// Versions saved before ADR-014 have no recorded selection; their result rows
// then show which kinds ran.
export function predictionVersionModelKinds(version: PredictionVersionDetailDto): string[] {
  const recorded = version.modelConfiguration.modelKinds;
  if (Array.isArray(recorded) && recorded.every((kind) => typeof kind === "string")) {
    return sortModelKinds(recorded as string[]);
  }
  return sortModelKinds(version.targets.flatMap((target) => target.results.map((result) => result.kind)));
}

export function predictionChartAxisTicks(dates: string[], plotWidth = 646): Array<{
  date: string;
  label: string;
  isFirst: boolean;
  isYearBoundary: boolean;
  year: string;
  showDateLabel: boolean;
  showYearLabel: boolean;
}> {
  const spacing = dates.length > 1 ? plotWidth / (dates.length - 1) : 0;
  let labelCount = Math.min(dates.length, 22);
  // Rounding sampled indices must not squeeze adjacent labels below 36 units.
  while (labelCount > 2 && Math.floor((dates.length - 1) / (labelCount - 1)) * spacing < 36) {
    labelCount--;
  }
  const labelledIndices = new Set(Array.from({ length: labelCount }, (_, index) =>
    labelCount < 2 ? 0 : Math.round(index * (dates.length - 1) / (labelCount - 1))
  ));
  let lastYearPosition = -Infinity;
  return dates.map((date, index) => {
    const year = date.slice(0, 4);
    const isYearBoundary = index > 0 && year !== dates[index - 1].slice(0, 4);
    const showYearLabel = (index === 0 || isYearBoundary) && index * spacing - lastYearPosition >= 36;
    if (showYearLabel) lastYearPosition = index * spacing;
    return {
      date,
      label: date.slice(5, 10),
      isFirst: index === 0,
      isYearBoundary,
      year,
      showDateLabel: labelledIndices.has(index),
      showYearLabel
    };
  });
}

export function predictionVersionStatus(version: PredictionVersionDetailDto): string {
  const results = version.targets.flatMap((target) => target.results);
  if (!results.length) return "No eligible results";
  return results.some((result) => result.status === "available")
    ? "Completed"
    : "Completed with ineligible metrics";
}

export function predictionIntervalBandPath(
  points: PredictionChartLine["points"],
  x: (date: string) => number,
  y: (value: number) => number
): string | null {
  if (!points.length || points.some((point) =>
    point.lowerBound === null || point.upperBound === null ||
    !Number.isFinite(point.lowerBound) || !Number.isFinite(point.upperBound)
  )) {
    return null;
  }

  const upperPath = points.map((point, index) =>
    `${index ? "L" : "M"}${x(point.date)} ${y(point.upperBound as number)}`
  );
  const lowerPath = [...points].reverse().map((point) =>
    `L${x(point.date)} ${y(point.lowerBound as number)}`
  );
  return [...upperPath, ...lowerPath, "Z"].join(" ");
}

function includesDate(date: string, start: string, end: string): boolean {
  return (!start || date >= start) && (!end || date <= end);
}

function targetLine(
  version: PredictionVersionDetailDto,
  target: PredictionTargetDto,
  result: PredictionTargetDto["results"][number],
  scenarioName: string,
  start: string,
  end: string
): PredictionChartLine {
  const intervalDescription = result.predictionIntervalStatus === "available"
    ? ` Saved ${version.confidenceLevel}% prediction interval is shown.`
    : result.predictionIntervalStatus === "unavailable"
      ? ` Prediction interval unavailable${result.predictionIntervalReason ? `: ${result.predictionIntervalReason}` : "."}`
      : " This result has no prediction interval.";
  return {
    id: `${version.id}:${target.scenarioId}:${target.metricId}:${result.kind}`,
    label: `${version.name} · ${scenarioName} · ${formatModelKind(result.kind)}`,
    provenance: `Saved prediction: ${version.name}; target scenario ${scenarioName}; model ${formatModelKind(result.kind)}; selected level ${version.confidenceLevel}%.${intervalDescription}`,
    kind: "prediction",
    modelKind: result.kind,
    confidenceLevel: version.confidenceLevel,
    predictionIntervalStatus: result.predictionIntervalStatus,
    strokeDasharray: modelKindDashes[result.kind],
    points: result.points.filter((point) => includesDate(point.date, start, end))
  };
}

export function buildPredictionMetricCharts(args: {
  versions: PredictionVersionDetailDto[];
  selectedVersionIds: Set<string>;
  selectedScenarioIds: Set<string>;
  selectedModelKinds: Set<string>;
  selectedMetricIds: Set<string>;
  scenarioNames: Map<string, string>;
  startDate: string;
  endDate: string;
  realityTimeseries: TimeserieDto[];
  includeReality: boolean;
}): PredictionMetricChart[] {
  const ranges = new Map<string, { start: string; end: string }>();
  for (const version of args.versions) {
    if (!args.selectedVersionIds.has(version.id)) continue;
    for (const target of version.targets) {
      if (!args.selectedScenarioIds.has(target.scenarioId) || !args.selectedMetricIds.has(target.metricId)) continue;
      const range = ranges.get(target.metricId);
      ranges.set(target.metricId, {
        start: range && range.start < version.startDate ? range.start : version.startDate,
        end: range && range.end > version.endDate ? range.end : version.endDate
      });
    }
  }
  const includesPlotDate = (metricId: string, date: string) => includesDate(
    date, args.startDate || ranges.get(metricId)!.start, args.endDate || ranges.get(metricId)!.end
  );
  const charts = new Map<string, PredictionMetricChart>();
  const ranModelKinds = new Map<string, Set<string>>();
  for (const version of args.versions) {
    if (!args.selectedVersionIds.has(version.id)) continue;
    const versionModelKinds = predictionVersionModelKinds(version);
    for (const target of version.targets) {
      if (
        !args.selectedScenarioIds.has(target.scenarioId) ||
        !args.selectedMetricIds.has(target.metricId)
      ) {
        continue;
      }
      const chart = charts.get(target.metricId) ?? {
        metricId: target.metricId,
        metricName: target.metricName,
        unit: target.unit ?? "no unit",
        lines: [],
        missingModelKinds: [],
        notRunModelKinds: [],
        realityMessage: null
      };
      charts.set(target.metricId, chart);
      const ran = ranModelKinds.get(target.metricId) ?? new Set<string>();
      versionModelKinds.forEach((kind) => ran.add(kind));
      ranModelKinds.set(target.metricId, ran);
      for (const result of target.results) {
        if (!args.selectedModelKinds.has(result.kind) || !result.points.length) continue;
        const line = targetLine(
          version,
          target,
          result,
          args.scenarioNames.get(target.scenarioId) ?? target.scenarioId,
          args.startDate || ranges.get(target.metricId)!.start,
          args.endDate || ranges.get(target.metricId)!.end
        );
        if (line.points.length) chart.lines.push(line);
      }
    }
  }

  if (args.includeReality) {
    for (const chart of charts.values()) {
      const reality = args.realityTimeseries.find(
        (timeserie) => timeserie.id === chart.metricId && timeserie.valueUnit === "number"
      );
      if (!reality) {
        chart.realityMessage = "No matching numeric current Reality series for this metric.";
        continue;
      }
      const points = reality.values
        .filter(
          (point): point is { date: string; value: number } =>
            typeof point.value === "number" && Number.isFinite(point.value) && includesPlotDate(chart.metricId, point.date)
        )
        .map((point) => ({ date: point.date, value: point.value, lowerBound: null, upperBound: null }));
      if (!points.length) {
        chart.realityMessage = "No current Reality observations in the displayed period.";
        continue;
      }
      chart.lines.unshift({
        id: `reality:${chart.metricId}`,
        label: `Current Reality · manually entered realized data · ${reality.name}`,
        provenance: "Current manually entered realized data from Reality. This live series is not part of the saved prediction version.",
        kind: "reality",
        points
      });
    }
  }

  return [...charts.values()]
    .map((chart) => {
      const ran = ranModelKinds.get(chart.metricId) ?? new Set<string>();
      const selected = sortModelKinds(args.selectedModelKinds);
      return {
        ...chart,
        // Only kinds that a plotted version ran can be missing results.
        missingModelKinds: selected.filter((kind) =>
          ran.has(kind) && !chart.lines.some((line) => line.modelKind === kind)
        ),
        notRunModelKinds: selected.filter((kind) => !ran.has(kind))
      };
    })
    .sort((left, right) => left.metricName.localeCompare(right.metricName));
}
