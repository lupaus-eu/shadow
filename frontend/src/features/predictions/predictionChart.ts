import type {
  PredictionTargetDto,
  PredictionVersionDetailDto
} from "../../api/predictions";
import type { TimeserieDto } from "../../api/timeseries";

export type PredictionChartLine = {
  id: string;
  label: string;
  provenance: string;
  kind: "prediction" | "reality";
  modelKind?: string;
  strokeDasharray?: string;
  points: Array<{ date: string; value: number }>;
};

export type PredictionMetricChart = {
  metricId: string;
  metricName: string;
  unit: string;
  lines: PredictionChartLine[];
  missingModelKinds: string[];
};

export function formatModelKind(kind: string): string {
  return kind.replaceAll("_", " ");
}

export function predictionChartAxisTicks(dates: string[]): Array<{
  date: string;
  label: string;
  isFirst: boolean;
  isYearBoundary: boolean;
  year: string;
}> {
  return dates.map((date, index) => {
    const year = date.slice(0, 4);
    return {
      date,
      label: date.slice(5, 10),
      isFirst: index === 0,
      isYearBoundary: index > 0 && year !== dates[index - 1].slice(0, 4),
      year
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
  return {
    id: `${version.id}:${target.scenarioId}:${target.metricId}:${result.kind}`,
    label: `${version.name} · ${scenarioName} · ${formatModelKind(result.kind)}`,
    provenance: `Saved prediction: ${version.name}; target scenario ${scenarioName}; model ${formatModelKind(result.kind)}.`,
    kind: "prediction",
    modelKind: result.kind,
    strokeDasharray: result.kind === "naive" ? "7 4" : result.kind === "average" ? "2 4" : undefined,
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
  const charts = new Map<string, PredictionMetricChart>();
  for (const version of args.versions) {
    if (!args.selectedVersionIds.has(version.id)) continue;
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
        missingModelKinds: []
      };
      charts.set(target.metricId, chart);
      for (const result of target.results) {
        if (!args.selectedModelKinds.has(result.kind) || !result.points.length) continue;
        const line = targetLine(
          version,
          target,
          result,
          args.scenarioNames.get(target.scenarioId) ?? target.scenarioId,
          args.startDate,
          args.endDate
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
      if (!reality) continue;
      const points = reality.values
        .filter(
          (point): point is { date: string; value: number } =>
            typeof point.value === "number" && includesDate(point.date, args.startDate, args.endDate)
        )
        .map((point) => ({ date: point.date, value: point.value }));
      if (!points.length) continue;
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
    .map((chart) => ({
      ...chart,
      missingModelKinds: [...args.selectedModelKinds].filter(
        (kind) => !chart.lines.some((line) => line.modelKind === kind)
      )
    }))
    .sort((left, right) => left.metricName.localeCompare(right.metricName));
}
