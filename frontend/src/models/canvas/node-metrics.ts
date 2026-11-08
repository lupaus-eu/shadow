import type { Metric, SeriesPoint } from "../client";

/** Pure helpers for the metrics a node shows in the details panel (read only; metrics are managed on the Metrics tab). */

export type NodeMetric = { metric: Metric; latest: SeriesPoint | null };

const collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });

/** The metrics attached to a node (`node_id` is the node's id), sorted by name and then key so the order is stable. */
export function metricsOfNode(metrics: readonly Metric[], nodeId: string): Metric[] {
  return metrics.filter((metric) => metric.node_id === nodeId).sort((a, b) => collator.compare(a.name, b.name) || collator.compare(a.key, b.key));
}

/** The point with the latest period that has a value; periods are ISO dates, so they compare as text. Null when there is no value at all. */
export function latestPoint(points: readonly SeriesPoint[]): (SeriesPoint & { value: number }) | null {
  let best: (SeriesPoint & { value: number }) | null = null;
  for (const point of points) {
    if (point.value === null || point.value === undefined || !Number.isFinite(point.value)) continue;
    if (!best || point.period > best.period) best = { period: point.period, value: point.value };
  }
  return best;
}

/** A value in the person's language with at most two decimals, followed by the unit when the metric has one ("1 234,5 EUR"). */
export function formatMetricValue(value: number, unit: string | null | undefined, locale: string): string {
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value);
  const suffix = unit?.trim();
  return suffix ? `${number} ${suffix}` : number;
}

/** "2026-03" from a period such as "2026-03-01". */
export const periodLabel = (period: string): string => period.slice(0, 7);
