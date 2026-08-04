import type { EventDto } from "../../api/events";
import type {
  GraphEdgeDto,
  GraphHistoryDto,
  GraphNodeDto,
  GraphTypeCatalogDto
} from "../../api/orgTwinStructure";
import type { TimeserieDto } from "../../api/timeseries";

const DAY_MS = 86_400_000;

export const MIN_PIXELS_PER_DAY = 1 / 7;
export const MAX_PIXELS_PER_DAY = 80;

export type TimelineBounds = {
  start: Date;
  end: Date;
  dayCount: number;
};

export type TimelineFilters = {
  nodes: boolean;
  edges: boolean;
  events: boolean;
  timeseries: boolean;
  nodeTypeIds: Set<string>;
};

type NodeRow = {
  kind: "node";
  id: string;
  node: GraphNodeDto;
  label: string;
  details: string;
  color: string;
};

type EdgeRow = {
  kind: "edge";
  id: string;
  edge: GraphEdgeDto;
  label: string;
  details: string;
  color: string;
  sourceNodeTypeId: string;
  targetNodeTypeId: string;
};

type EventRow = {
  kind: "event";
  id: string;
  event: EventDto;
  label: string;
  details: string;
};

type TimeserieRow = {
  kind: "timeserie";
  id: string;
  timeserie: TimeserieDto;
  label: string;
  details: string;
};

export type TimelineRow = NodeRow | EdgeRow | EventRow | TimeserieRow;

export type ChartScale = {
  min: number;
  max: number;
  ticks: number[];
};

export function parseTimelineDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }
  return date;
}

export function formatTimelineDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function compareText(left: string, right: string): number {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base"
  });
}

export function buildTimelineRows(
  history: GraphHistoryDto,
  catalog: GraphTypeCatalogDto,
  events: EventDto[],
  timeseries: TimeserieDto[]
): TimelineRow[] {
  const nodeTypes = new Map(catalog.nodeTypes.map((item) => [item.id, item]));
  const nodesById = new Map(history.nodes.map((item) => [item.id, item]));
  const outgoing = new Map<string, GraphEdgeDto[]>();

  for (const edge of history.edges) {
    const items = outgoing.get(edge.sourceNodeId) ?? [];
    items.push(edge);
    outgoing.set(edge.sourceNodeId, items);
  }

  const nodes = [...history.nodes].sort((left, right) => {
    const typeComparison = compareText(
      nodeTypes.get(left.nodeTypeId)?.displayName ?? left.nodeTypeId,
      nodeTypes.get(right.nodeTypeId)?.displayName ?? right.nodeTypeId
    );
    if (typeComparison) return typeComparison;
    const nameComparison = compareText(left.name, right.name);
    return nameComparison || compareText(left.id, right.id);
  });

  const rows: TimelineRow[] = [];
  for (const node of nodes) {
    const nodeType = nodeTypes.get(node.nodeTypeId);
    const typeName = nodeType?.displayName ?? "Unknown node type";
    rows.push({
      kind: "node",
      id: `node:${node.id}`,
      node,
      label: `${node.name} (${typeName})`,
      details: `${node.name} · ${typeName} · ${node.createDate ?? "unknown"} – ${node.deleteDate ?? "open"}`,
      color: nodeType?.color ?? "#807868"
    });

    const edges = [...(outgoing.get(node.id) ?? [])].sort((left, right) => {
      const labelComparison = compareText(left.name, right.name);
      return labelComparison || compareText(left.id, right.id);
    });
    for (const edge of edges) {
      const target = nodesById.get(edge.targetNodeId);
      const targetTypeId = target?.nodeTypeId ?? "";
      rows.push({
        kind: "edge",
        id: `edge:${edge.id}`,
        edge,
        label: `${edge.name} (Edge)`,
        details: `${edge.name} · ${edge.sourceNodeId} → ${edge.targetNodeId} · ${edge.createDate ?? "unknown"} – ${edge.deleteDate ?? "open"}`,
        color: nodeTypes.get(targetTypeId)?.color ?? "#807868",
        sourceNodeTypeId: node.nodeTypeId,
        targetNodeTypeId: targetTypeId
      });
    }
  }

  for (const event of [...events].sort((left, right) => {
    const dateComparison = compareText(left.targetDate, right.targetDate);
    if (dateComparison) return dateComparison;
    const nameComparison = compareText(left.name, right.name);
    return nameComparison || compareText(left.id, right.id);
  })) {
    rows.push({
      kind: "event",
      id: `event:${event.id}`,
      event,
      label: `Event: ${event.name}`,
      details: `${event.name} · ${event.targetDate || "unknown date"}${event.eventDetails ? ` · ${event.eventDetails}` : ""}`
    });
  }

  for (const timeserie of [...timeseries].sort((left, right) =>
    compareText(left.id, right.id)
  )) {
    rows.push({
      kind: "timeserie",
      id: `timeserie:${timeserie.id}`,
      timeserie,
      label: `Timeserie: ${timeserie.name}`,
      details: `${timeserie.name} · ${timeserie.id} · ${timeserie.unit || "no unit"} · ${timeserie.timeUnit} · ${timeserie.valueUnit}`
    });
  }

  return rows;
}

export function filterTimelineRows(
  rows: TimelineRow[],
  filters: TimelineFilters
): TimelineRow[] {
  return rows.filter((row) => {
    if (row.kind === "node") {
      return filters.nodes && filters.nodeTypeIds.has(row.node.nodeTypeId);
    }
    if (row.kind === "edge") {
      return (
        filters.nodes &&
        filters.edges &&
        filters.nodeTypeIds.has(row.sourceNodeTypeId) &&
        filters.nodeTypeIds.has(row.targetNodeTypeId)
      );
    }
    if (row.kind === "event") return filters.events;
    return filters.timeseries;
  });
}

function datesForRow(row: TimelineRow): Date[] {
  if (row.kind === "node") {
    return [row.node.createDate, row.node.deleteDate]
      .map(parseTimelineDate)
      .filter((item): item is Date => item !== null);
  }
  if (row.kind === "edge") {
    return [row.edge.createDate, row.edge.deleteDate]
      .map(parseTimelineDate)
      .filter((item): item is Date => item !== null);
  }
  if (row.kind === "event") {
    const date = parseTimelineDate(row.event.targetDate);
    return date ? [date] : [];
  }
  return row.timeserie.values
    .map((item) => parseTimelineDate(item.date))
    .filter((item): item is Date => item !== null);
}

export function calculateTimelineBounds(
  rows: TimelineRow[],
  selectedOrgStateTargetDate?: string | null,
  now = new Date()
): TimelineBounds {
  const dates = rows.flatMap(datesForRow);
  const selectedDate = parseTimelineDate(selectedOrgStateTargetDate);
  if (selectedDate) dates.push(selectedDate);

  let start: Date;
  let latest: Date;
  if (dates.length) {
    start = new Date(Math.min(...dates.map((item) => item.getTime())));
    latest = new Date(Math.max(...dates.map((item) => item.getTime())));
  } else {
    start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
    latest = new Date(start);
  }

  const end = new Date(
    Date.UTC(latest.getUTCFullYear(), latest.getUTCMonth() + 2, 0)
  );
  return {
    start,
    end,
    dayCount: Math.max(1, Math.round((end.getTime() - start.getTime()) / DAY_MS) + 1)
  };
}

export function clampZoom(value: number): number {
  return Math.min(MAX_PIXELS_PER_DAY, Math.max(MIN_PIXELS_PER_DAY, value));
}

export function fitZoom(viewportWidth: number, dayCount: number): number {
  return clampZoom(viewportWidth / Math.max(1, dayCount));
}

export function dateOffset(date: Date, start: Date, pixelsPerDay: number): number {
  return ((date.getTime() - start.getTime()) / DAY_MS) * pixelsPerDay;
}

export function numericTimeserieValues(timeserie: TimeserieDto) {
  if (timeserie.valueUnit !== "number") return [];
  return timeserie.values
    .map((item) => ({ date: parseTimelineDate(item.date), value: item.value }))
    .filter(
      (item): item is { date: Date; value: number } =>
        item.date !== null && typeof item.value === "number" && Number.isFinite(item.value)
    )
    .sort((left, right) => left.date.getTime() - right.date.getTime());
}

export function calculateChartScale(values: number[]): ChartScale {
  if (!values.length) return { min: -1, max: 1, ticks: [-1, 0, 1] };
  const rawMin = Math.min(0, ...values);
  const rawMax = Math.max(0, ...values);
  if (rawMin === rawMax) return { min: -1, max: 1, ticks: [-1, 0, 1] };
  const span = rawMax - rawMin;
  const roughStep = span / 4;
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const normalized = roughStep / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  const min = Number((Math.floor(rawMin / step) * step).toPrecision(12));
  const max = Number((Math.ceil(rawMax / step) * step).toPrecision(12));
  const ticks: number[] = [];
  for (let value = min; value <= max + step / 2; value += step) {
    ticks.push(Number(value.toPrecision(12)));
  }
  return { min, max, ticks };
}

export function monthMarkers(bounds: TimelineBounds, includeYear = false) {
  const markers: Array<{ date: Date; label: string }> = [];
  const cursor = new Date(
    Date.UTC(bounds.start.getUTCFullYear(), bounds.start.getUTCMonth(), 1)
  );
  markers.push({
    date: new Date(bounds.start),
    label: monthMarkerLabel(cursor, includeYear)
  });
  cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  while (cursor <= bounds.end) {
    markers.push({
      date: new Date(cursor),
      label: monthMarkerLabel(cursor, includeYear)
    });
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  return markers;
}

export function yearMarkers(bounds: TimelineBounds) {
  const markers: Array<{ date: Date; label: string }> = [];
  const firstYear = bounds.start.getUTCFullYear();
  markers.push({
    date: new Date(bounds.start),
    label: String(firstYear)
  });
  const cursor = new Date(Date.UTC(firstYear + 1, 0, 1));
  while (cursor <= bounds.end) {
    markers.push({
      date: new Date(cursor),
      label: String(cursor.getUTCFullYear())
    });
    cursor.setUTCFullYear(cursor.getUTCFullYear() + 1);
  }
  return markers;
}

export function shouldUseYearOnlyHeader(
  bounds: TimelineBounds,
  pixelsPerDay: number
): boolean {
  return !headerMarkersFit(bounds, pixelsPerDay, monthMarkers(bounds));
}

export function shouldShowYearAndMonthHeader(
  bounds: TimelineBounds,
  pixelsPerDay: number
): boolean {
  return headerMarkersFit(bounds, pixelsPerDay, monthMarkers(bounds, true));
}

function headerMarkersFit(
  bounds: TimelineBounds,
  pixelsPerDay: number,
  markers: Array<{ date: Date; label: string }>
): boolean {
  return markers.every((marker, index) => {
    const left = dateOffset(marker.date, bounds.start, pixelsPerDay);
    const nextMarker = markers[index + 1];
    const right = nextMarker
      ? dateOffset(nextMarker.date, bounds.start, pixelsPerDay)
      : bounds.dayCount * pixelsPerDay;
    const requiredWidth = 16 + marker.label.length * 7;
    return right - left >= requiredWidth;
  });
}

function monthMarkerLabel(date: Date, includeYear: boolean): string {
  const year = String(date.getUTCFullYear());
  const month = date.toLocaleDateString("en", {
    month: "short",
    timeZone: "UTC"
  });
  if (includeYear) return `${year} ${month}`;
  if (date.getUTCMonth() === 0) return String(date.getUTCFullYear());
  return month;
}
