import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent, PointerEvent } from "react";
import { fetchEvents } from "../../api/events";
import Alert from "../../components/Alert";
import type { EventDto } from "../../api/events";
import { fetchGraphHistory, fetchGraphTypeCatalog } from "../../api/orgTwinStructure";
import type { GraphHistoryDto, GraphTypeCatalogDto } from "../../api/orgTwinStructure";
import { fetchTimeseries } from "../../api/timeseries";
import type { TimeserieDto } from "../../api/timeseries";
import { useWorkspaceSelection } from "../../workspace/WorkspaceSelectionContext";
import {
  MAX_PIXELS_PER_DAY,
  MIN_PIXELS_PER_DAY,
  buildTimelineRows,
  calculateChartScale,
  calculateTimelineBounds,
  clampZoom,
  dateOffset,
  filterTimelineRows,
  fitZoom,
  formatTimelineDate,
  monthMarkers,
  numericTimeserieValues,
  parseTimelineDate,
  shouldShowYearAndMonthHeader,
  shouldUseYearOnlyHeader,
  yearMarkers
} from "./summaryTimeline";
import type { TimelineBounds, TimelineFilters, TimelineRow } from "./summaryTimeline";

type SummaryData = {
  history: GraphHistoryDto;
  catalog: GraphTypeCatalogDto;
  events: EventDto[];
  timeseries: TimeserieDto[];
};

const DEFAULT_TIMESERIE_HEIGHT = 92;
const MIN_TIMESERIE_HEIGHT = 64;
const MAX_TIMESERIE_HEIGHT = 240;
const COLLAPSED_ROW_HEIGHT = 32;
const TIMESERIE_HOVER_RADIUS = 40;
const TIMESERIE_TOOLTIP_EDGE_GUARD = 160;

type TooltipAlignment = "left" | "center" | "right";

type TimelineDrag = {
  pointerId: number;
  startClientX: number;
  startScrollLeft: number;
};

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function formatZoomScale(pixelsPerDay: number): string {
  const format = (value: number) => String(Number(value.toFixed(1)));
  if (pixelsPerDay >= 1) {
    const pixels = format(pixelsPerDay);
    return `${pixels} ${pixels === "1" ? "pixel" : "pixels"} / 1 day`;
  }
  const days = format(1 / pixelsPerDay);
  return `1 pixel / ${days} ${days === "1" ? "day" : "days"}`;
}

export default function SummaryTab(props: { orgId: string }) {
  const { selectedScenario, selectedOrgState } = useWorkspaceSelection();
  const [data, setData] = useState<SummaryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [rowsOpen, setRowsOpen] = useState(false);
  const [filters, setFilters] = useState<TimelineFilters>({
    nodes: true,
    edges: true,
    events: true,
    timeseries: true,
    nodeTypeIds: new Set()
  });
  const [collapsedRowIds, setCollapsedRowIds] = useState<Set<string>>(() => new Set());
  const [hiddenRowIds, setHiddenRowIds] = useState<Set<string>>(() => new Set());
  const [pixelsPerDay, setPixelsPerDay] = useState(1);
  const [timeserieHeight, setTimeserieHeight] = useState(DEFAULT_TIMESERIE_HEIGHT);
  const [timelineDragging, setTimelineDragging] = useState(false);

  const headerScrollRef = useRef<HTMLDivElement>(null);
  const labelsScrollRef = useRef<HTMLDivElement>(null);
  const timelineScrollRef = useRef<HTMLDivElement>(null);
  const bottomScrollRef = useRef<HTMLDivElement>(null);
  const selectedTargetDateRef = useRef(selectedOrgState?.targetDate);
  const timelineDragRef = useRef<TimelineDrag | null>(null);

  useEffect(() => {
    selectedTargetDateRef.current = selectedOrgState?.targetDate;
  }, [selectedOrgState?.targetDate]);

  useEffect(() => {
    const scenarioId = selectedScenario?.id;
    const controller = new AbortController();
    let ignore = false;

    if (!scenarioId) {
      return () => controller.abort();
    }
    const activeScenarioId = scenarioId;

    async function loadSummary() {
      try {
        setLoading(true);
        setError("");
        setData(null);
        const [history, catalog, events, timeseries] = await Promise.all([
          fetchGraphHistory(props.orgId, activeScenarioId, controller.signal),
          fetchGraphTypeCatalog(props.orgId, activeScenarioId, controller.signal),
          fetchEvents(props.orgId, activeScenarioId, controller.signal),
          fetchTimeseries(props.orgId, activeScenarioId, controller.signal)
        ]);
        if (ignore) return;
        setData({ history, catalog, events, timeseries });
        setCollapsedRowIds(new Set());
        setHiddenRowIds(new Set());
        setFiltersOpen(false);
        setRowsOpen(false);
        setFilters({
          nodes: true,
          edges: true,
          events: true,
          timeseries: true,
          nodeTypeIds: new Set([
            ...catalog.nodeTypes.map((item) => item.id),
            ...history.nodes.map((item) => item.nodeTypeId)
          ])
        });
      } catch (loadError) {
        const namedError = loadError as { name?: string };
        if (ignore || namedError.name === "AbortError") return;
        setError(`Could not load summary. ${messageFromError(loadError)}`);
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    void loadSummary();
    return () => {
      ignore = true;
      controller.abort();
    };
  }, [props.orgId, refreshVersion, selectedScenario?.id]);

  const allRows = useMemo(
    () => (data ? buildTimelineRows(data.history, data.catalog, data.events, data.timeseries) : []),
    [data]
  );
  const filteredRows = useMemo(() => filterTimelineRows(allRows, filters), [allRows, filters]);
  const visibleRows = useMemo(
    () => filteredRows.filter((row) => !hiddenRowIds.has(row.id)),
    [filteredRows, hiddenRowIds]
  );
  const nodeTypeOptions = useMemo(() => {
    const options = new Map(
      (data?.catalog.nodeTypes ?? []).map((item) => [item.id, item.displayName])
    );
    for (const node of data?.history.nodes ?? []) {
      if (!options.has(node.nodeTypeId)) {
        options.set(node.nodeTypeId, "Unknown node type");
      }
    }
    return [...options].sort((left, right) => left[1].localeCompare(right[1]));
  }, [data]);
  const bounds = useMemo(
    () => calculateTimelineBounds(visibleRows, selectedOrgState?.targetDate),
    [selectedOrgState?.targetDate, visibleRows]
  );
  const timelineWidth = Math.max(1, Math.ceil(bounds.dayCount * pixelsPerDay));
  const yearOnlyHeader = shouldUseYearOnlyHeader(bounds, pixelsPerDay);
  const yearAndMonthHeader = shouldShowYearAndMonthHeader(bounds, pixelsPerDay);

  useLayoutEffect(() => {
    if (!data || !timelineScrollRef.current) return;
    const initialRows = buildTimelineRows(data.history, data.catalog, data.events, data.timeseries);
    const initialBounds = calculateTimelineBounds(initialRows, selectedTargetDateRef.current);
    setPixelsPerDay(fitZoom(timelineScrollRef.current.clientWidth || 900, initialBounds.dayCount));
  }, [data]);

  const syncHorizontal = useCallback((source: HTMLDivElement) => {
    for (const target of [
      headerScrollRef.current,
      timelineScrollRef.current,
      bottomScrollRef.current
    ]) {
      if (target && target !== source) target.scrollLeft = source.scrollLeft;
    }
  }, []);

  const syncVertical = useCallback((source: HTMLDivElement) => {
    const target =
      source === labelsScrollRef.current ? timelineScrollRef.current : labelsScrollRef.current;
    if (target) target.scrollTop = source.scrollTop;
  }, []);

  function startTimelineDrag(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0 || timelineDragRef.current) return;
    timelineDragRef.current = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startScrollLeft: event.currentTarget.scrollLeft
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setTimelineDragging(true);
    event.preventDefault();
  }

  function moveTimelineDrag(event: PointerEvent<HTMLDivElement>) {
    const drag = timelineDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.currentTarget.scrollLeft = drag.startScrollLeft - (event.clientX - drag.startClientX);
    syncHorizontal(event.currentTarget);
    event.preventDefault();
  }

  function stopTimelineDrag(event: PointerEvent<HTMLDivElement>) {
    const drag = timelineDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    timelineDragRef.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setTimelineDragging(false);
  }

  function updateCategory(key: "nodes" | "edges" | "events" | "timeseries") {
    setFilters((current) => ({ ...current, [key]: !current[key] }));
  }

  function updateNodeType(nodeTypeId: string) {
    setFilters((current) => {
      const nodeTypeIds = new Set(current.nodeTypeIds);
      if (nodeTypeIds.has(nodeTypeId)) nodeTypeIds.delete(nodeTypeId);
      else nodeTypeIds.add(nodeTypeId);
      return { ...current, nodeTypeIds };
    });
  }

  function toggleCollapsedRow(rowId: string) {
    setCollapsedRowIds((current) => {
      const next = new Set(current);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }

  function toggleRowVisibility(rowId: string) {
    if (hiddenRowIds.has(rowId)) {
      setCollapsedRowIds((current) => {
        const next = new Set(current);
        next.delete(rowId);
        return next;
      });
    }
    setHiddenRowIds((current) => {
      const next = new Set(current);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }

  function zoomToFit() {
    setPixelsPerDay(fitZoom(timelineScrollRef.current?.clientWidth || 900, bounds.dayCount));
    for (const target of [
      headerScrollRef.current,
      timelineScrollRef.current,
      bottomScrollRef.current
    ]) {
      if (target) target.scrollLeft = 0;
    }
  }

  if (!selectedScenario) {
    return (
      <section className="summary-tab">
        <div className="empty-state" role="status">
          <h1 className="page-title">Summary</h1>
          <p>Select a scenario in Scenarios to view its summary timeline.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="summary-tab" aria-labelledby="summary-heading">
      <header className="summary-toolbar">
        <div className="summary-toolbar__title">
          <div className="summary-toolbar__title-line">
            <span>Summary of</span>
            <h1 id="summary-heading" className="page-title" title={selectedScenario.name}>
              {selectedScenario.name}
            </h1>
          </div>
          {data ? (
            <span className="summary-toolbar__meta">
              Timeline: {formatTimelineDate(bounds.start)} ... {formatTimelineDate(bounds.end)} |
              rows: {visibleRows.length}
            </span>
          ) : null}
        </div>
        <div className="summary-toolbar__actions">
          <div className="summary-popover-anchor">
            <button
              className="btn btn--secondary"
              type="button"
              aria-expanded={filtersOpen}
              aria-controls="summary-filters"
              onClick={() => {
                setRowsOpen(false);
                setFiltersOpen((value) => !value);
              }}
            >
              Filters
            </button>
            {filtersOpen ? (
              <div id="summary-filters" className="summary-popover" aria-label="Summary filters">
                <FilterCheckbox
                  label="Nodes and their edges"
                  checked={filters.nodes}
                  onChange={() => updateCategory("nodes")}
                />
                <FilterCheckbox
                  label="Edges"
                  checked={filters.edges}
                  onChange={() => updateCategory("edges")}
                />
                <FilterCheckbox
                  label="Events"
                  checked={filters.events}
                  onChange={() => updateCategory("events")}
                />
                <FilterCheckbox
                  label="Timeseries"
                  checked={filters.timeseries}
                  onChange={() => updateCategory("timeseries")}
                />
                <div className="summary-popover__section">
                  <span className="field-label">Node types</span>
                  <div className="summary-popover__shortcuts">
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() =>
                        setFilters((current) => ({
                          ...current,
                          nodeTypeIds: new Set(nodeTypeOptions.map(([id]) => id))
                        }))
                      }
                    >
                      All
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost"
                      onClick={() =>
                        setFilters((current) => ({ ...current, nodeTypeIds: new Set() }))
                      }
                    >
                      None
                    </button>
                  </div>
                  {nodeTypeOptions.map(([nodeTypeId, displayName]) => (
                    <FilterCheckbox
                      key={nodeTypeId}
                      label={displayName}
                      checked={filters.nodeTypeIds.has(nodeTypeId)}
                      onChange={() => updateNodeType(nodeTypeId)}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
          <div className="summary-popover-anchor">
            <button
              className="btn btn--secondary"
              type="button"
              aria-expanded={rowsOpen}
              aria-controls="summary-rows"
              onClick={() => {
                setFiltersOpen(false);
                setRowsOpen((value) => !value);
              }}
            >
              Rows
            </button>
            {rowsOpen ? (
              <div
                id="summary-rows"
                className="summary-popover summary-popover--rows"
                aria-label="Row visibility"
              >
                <div className="summary-popover__shortcuts">
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => {
                      setCollapsedRowIds((current) => {
                        const next = new Set(current);
                        for (const rowId of hiddenRowIds) next.delete(rowId);
                        return next;
                      });
                      setHiddenRowIds(new Set());
                    }}
                  >
                    All
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => setHiddenRowIds(new Set(allRows.map((row) => row.id)))}
                  >
                    None
                  </button>
                </div>
                {allRows.map((row) => (
                  <FilterCheckbox
                    key={row.id}
                    label={row.label}
                    checked={!hiddenRowIds.has(row.id)}
                    onChange={() => toggleRowVisibility(row.id)}
                  />
                ))}
              </div>
            ) : null}
          </div>
          <div className="summary-zoom" role="group" aria-label="Timeline zoom">
            <button
              className="btn btn--secondary"
              type="button"
              aria-label="Zoom out timeline"
              onClick={() => setPixelsPerDay((value) => clampZoom(value / 1.15))}
            >
              −
            </button>
            <button
              className="btn btn--secondary"
              type="button"
              aria-label="Zoom in timeline"
              onClick={() => setPixelsPerDay((value) => clampZoom(value * 1.15))}
            >
              +
            </button>
            <input
              aria-label="Timeline zoom level"
              type="range"
              min={MIN_PIXELS_PER_DAY}
              max={MAX_PIXELS_PER_DAY}
              step="0.1"
              value={pixelsPerDay}
              onChange={(event) => setPixelsPerDay(clampZoom(Number(event.target.value)))}
            />
            <output
              className="summary-zoom__scale"
              aria-label="Timeline zoom scale"
              aria-live="polite"
            >
              {formatZoomScale(pixelsPerDay)}
            </output>
            <button className="btn btn--secondary" type="button" onClick={zoomToFit}>
              Zoom to fit
            </button>
          </div>
          <label className="summary-resize-control">
            <span>Row height</span>
            <input
              aria-label="Resize all timeseries rows"
              type="range"
              min={MIN_TIMESERIE_HEIGHT}
              max={MAX_TIMESERIE_HEIGHT}
              value={timeserieHeight}
              onChange={(event) => setTimeserieHeight(Number(event.target.value))}
            />
          </label>
          <button
            className="btn btn--primary"
            type="button"
            disabled={loading}
            onClick={() => setRefreshVersion((value) => value + 1)}
          >
            Refresh
          </button>
        </div>
      </header>

      {loading ? (
        <div className="summary-state" role="status" aria-live="polite">
          Loading summary timeline…
        </div>
      ) : null}
      {error ? (
        <Alert
          variant="danger"
          role="alert"
          boxClassName="summary-state summary-state--error"
          message={error}
          onDismiss={() => setError("")}
          dismissLabel="Dismiss summary error notice"
        >
          <button
            className="btn btn--secondary"
            type="button"
            onClick={() => setRefreshVersion((value) => value + 1)}
          >
            Retry
          </button>
        </Alert>
      ) : null}
      {!loading && !error && data && allRows.length === 0 ? (
        <div className="summary-state" role="status">
          This scenario has no timeline items yet.
        </div>
      ) : null}
      {!loading && !error && data && allRows.length > 0 && visibleRows.length === 0 ? (
        <div className="summary-state" role="status">
          No timeline rows match the current filters.
        </div>
      ) : null}

      {!loading && !error && data && visibleRows.length > 0 ? (
        <div className="summary-timeline-shell">
          <div className="summary-timeline-header-label">Item</div>
          <div
            ref={headerScrollRef}
            className="summary-timeline-header-scroll"
            onScroll={(event) => syncHorizontal(event.currentTarget)}
          >
            <TimelineHeader
              bounds={bounds}
              width={timelineWidth}
              pixelsPerDay={pixelsPerDay}
              yearOnly={yearOnlyHeader}
              showYearAndMonth={yearAndMonthHeader}
            />
          </div>
          <div
            ref={labelsScrollRef}
            className="summary-labels"
            onScroll={(event) => syncVertical(event.currentTarget)}
          >
            {visibleRows.map((row) => {
              const collapsed = collapsedRowIds.has(row.id);
              return (
                <TimelineLabel
                  key={row.id}
                  row={row}
                  height={
                    collapsed
                      ? COLLAPSED_ROW_HEIGHT
                      : row.kind === "timeserie"
                        ? timeserieHeight
                        : undefined
                  }
                  collapsed={collapsed}
                  onToggle={() => toggleCollapsedRow(row.id)}
                />
              );
            })}
          </div>
          <div
            ref={timelineScrollRef}
            className={`summary-timeline-rows${timelineDragging ? " summary-timeline-rows--dragging" : ""}`}
            onPointerDown={startTimelineDrag}
            onPointerMove={moveTimelineDrag}
            onPointerUp={stopTimelineDrag}
            onPointerCancel={stopTimelineDrag}
            onScroll={(event) => {
              syncHorizontal(event.currentTarget);
              syncVertical(event.currentTarget);
            }}
          >
            <div style={{ width: timelineWidth }}>
              {visibleRows.map((row) => (
                <TimelineRowView
                  key={row.id}
                  row={row}
                  bounds={bounds}
                  width={timelineWidth}
                  pixelsPerDay={pixelsPerDay}
                  timeserieHeight={timeserieHeight}
                  collapsed={collapsedRowIds.has(row.id)}
                  showMonthGridLines={yearOnlyHeader}
                />
              ))}
            </div>
          </div>
          <div className="summary-scrollbar-label" aria-hidden="true" />
          <div
            ref={bottomScrollRef}
            className="summary-bottom-scrollbar"
            aria-label="Timeline horizontal scrollbar"
            onScroll={(event) => syncHorizontal(event.currentTarget)}
          >
            <div style={{ width: timelineWidth, height: 1 }} />
          </div>
        </div>
      ) : null}
    </section>
  );
}

function FilterCheckbox(props: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="summary-checkbox">
      <input type="checkbox" checked={props.checked} onChange={props.onChange} />
      <span title={props.label}>{props.label}</span>
    </label>
  );
}

function TimelineHeader(props: {
  bounds: TimelineBounds;
  width: number;
  pixelsPerDay: number;
  yearOnly: boolean;
  showYearAndMonth: boolean;
}) {
  const markers = props.yearOnly
    ? yearMarkers(props.bounds)
    : monthMarkers(props.bounds, props.showYearAndMonth);
  return (
    <div className="summary-date-header" style={{ width: props.width }}>
      {markers.map((marker, index) => {
        const left = dateOffset(marker.date, props.bounds.start, props.pixelsPerDay);
        const nextMarker = markers[index + 1];
        const right = nextMarker
          ? dateOffset(nextMarker.date, props.bounds.start, props.pixelsPerDay)
          : props.width;
        const yearBoundary = marker.date.getUTCMonth() === 0;
        return (
          <div
            key={marker.date.toISOString()}
            className={`summary-month-marker${yearBoundary ? " summary-month-marker--year" : ""}`}
            style={{ left, width: Math.max(0, right - left) }}
          >
            <span title={marker.label}>{marker.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function TimelineLabel(props: {
  row: TimelineRow;
  height?: number;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const className = `summary-label summary-label--${props.row.kind}${props.collapsed ? " summary-label--collapsed" : ""}`;
  return (
    <div
      className={className}
      style={props.height ? { height: props.height } : undefined}
      title={props.row.details}
    >
      <span className="summary-label__content">{props.row.label}</span>
      <button
        className={`disclosure-button${props.collapsed ? " disclosure-button--collapsed" : ""}`}
        type="button"
        onClick={props.onToggle}
        aria-expanded={!props.collapsed}
        aria-label={
          props.collapsed ? `Expand ${props.row.label} row` : `Collapse ${props.row.label} row`
        }
      >
        <span aria-hidden="true">▾</span>
      </button>
    </div>
  );
}

function TimelineRowView(props: {
  row: TimelineRow;
  bounds: TimelineBounds;
  width: number;
  pixelsPerDay: number;
  timeserieHeight: number;
  collapsed: boolean;
  showMonthGridLines: boolean;
}) {
  const plottedNumericTimeserie =
    props.row.kind === "timeserie" && numericTimeserieValues(props.row.timeserie).length > 0;
  const className = `summary-timeline-row summary-timeline-row--${props.row.kind}${plottedNumericTimeserie ? " summary-timeline-row--numeric-timeserie" : ""}${props.collapsed ? " summary-timeline-row--collapsed" : ""}`;
  const style = props.collapsed
    ? { height: COLLAPSED_ROW_HEIGHT }
    : props.row.kind === "timeserie"
      ? { height: props.timeserieHeight }
      : undefined;
  return (
    <div className={className} style={style}>
      {props.showMonthGridLines
        ? monthMarkers(props.bounds).map((marker) => (
            <span
              key={marker.date.toISOString()}
              className={`summary-grid-line${marker.date.getUTCMonth() === 0 ? " summary-grid-line--year" : ""}`}
              style={{ left: dateOffset(marker.date, props.bounds.start, props.pixelsPerDay) }}
            />
          ))
        : null}
      {!props.collapsed && props.row.kind === "node" ? (
        <LifetimeBar
          start={props.row.node.createDate}
          end={props.row.node.deleteDate}
          bounds={props.bounds}
          pixelsPerDay={props.pixelsPerDay}
          color={props.row.color}
          details={props.row.details}
        />
      ) : null}
      {!props.collapsed && props.row.kind === "edge" ? (
        <LifetimeBar
          start={props.row.edge.createDate}
          end={props.row.edge.deleteDate}
          bounds={props.bounds}
          pixelsPerDay={props.pixelsPerDay}
          color={props.row.color}
          details={props.row.details}
          thin
        />
      ) : null}
      {!props.collapsed && props.row.kind === "event" ? (
        <EventMarker row={props.row} bounds={props.bounds} pixelsPerDay={props.pixelsPerDay} />
      ) : null}
      {!props.collapsed && props.row.kind === "timeserie" ? (
        <TimeserieChart
          row={props.row}
          bounds={props.bounds}
          width={props.width}
          height={props.timeserieHeight}
          pixelsPerDay={props.pixelsPerDay}
        />
      ) : null}
    </div>
  );
}

function LifetimeBar(props: {
  start: string | null;
  end: string | null;
  bounds: TimelineBounds;
  pixelsPerDay: number;
  color: string;
  details: string;
  thin?: boolean;
}) {
  const start = parseTimelineDate(props.start);
  const end = parseTimelineDate(props.end) ?? props.bounds.end;
  if (!start) return <span className="summary-row-message">Invalid or missing lifetime date</span>;
  const left = dateOffset(start, props.bounds.start, props.pixelsPerDay);
  const width = Math.max(2, dateOffset(end, start, props.pixelsPerDay) + props.pixelsPerDay);
  return (
    <span
      className={`summary-lifetime-bar${props.thin ? " summary-lifetime-bar--thin" : ""}`}
      style={{ left, width, backgroundColor: props.color }}
      title={props.details}
    />
  );
}

function EventMarker(props: {
  row: Extract<TimelineRow, { kind: "event" }>;
  bounds: TimelineBounds;
  pixelsPerDay: number;
}) {
  const date = parseTimelineDate(props.row.event.targetDate);
  return date ? (
    <span
      className="summary-event-marker"
      style={{ left: dateOffset(date, props.bounds.start, props.pixelsPerDay) }}
      title={props.row.details}
    />
  ) : (
    <span className="summary-row-message">Invalid or missing event date</span>
  );
}

function TimeserieChart(props: {
  row: Extract<TimelineRow, { kind: "timeserie" }>;
  bounds: TimelineBounds;
  width: number;
  height: number;
  pixelsPerDay: number;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [tooltipAlignment, setTooltipAlignment] = useState<TooltipAlignment>("center");
  const values = numericTimeserieValues(props.row.timeserie);
  if (props.row.timeserie.valueUnit !== "number")
    return (
      <span className="summary-row-message">
        {props.row.timeserie.valueUnit} timeseries are not plotted.
      </span>
    );
  if (!values.length)
    return <span className="summary-row-message">No numeric values to plot.</span>;
  const numericValues = values.map((item) => item.value);
  const scale = calculateChartScale(numericValues);
  const valueMin = Math.min(...numericValues);
  const valueMax = Math.max(...numericValues);
  const chartTop = 10;
  const chartBottom = props.height - 16;
  const y = (value: number) =>
    chartBottom - ((value - scale.min) / (scale.max - scale.min)) * (chartBottom - chartTop);
  const points = values.map((item) => ({
    ...item,
    x: dateOffset(item.date, props.bounds.start, props.pixelsPerDay),
    y: y(item.value)
  }));
  const path = points.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
  function onMouseMove(event: MouseEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const pointerY = event.clientY - rect.top;
    let nearest = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    for (let index = 0; index < points.length; index += 1) {
      const distance = Math.hypot(points[index].x - x, points[index].y - pointerY);
      if (distance < nearestDistance) {
        nearest = index;
        nearestDistance = distance;
      }
    }
    if (nearestDistance > TIMESERIE_HOVER_RADIUS) {
      setHoveredIndex(null);
      return;
    }
    const viewport = event.currentTarget.closest(".summary-timeline-rows");
    let visibleLeft = 0;
    let visibleRight = props.width;
    if (viewport instanceof HTMLElement && viewport.clientWidth > 0) {
      visibleLeft = viewport.scrollLeft;
      visibleRight = viewport.scrollLeft + viewport.clientWidth;
    }
    const leftSpace = points[nearest].x - visibleLeft;
    const rightSpace = visibleRight - points[nearest].x;
    if (rightSpace < TIMESERIE_TOOLTIP_EDGE_GUARD && rightSpace <= leftSpace) {
      setTooltipAlignment("right");
    } else if (leftSpace < TIMESERIE_TOOLTIP_EDGE_GUARD) {
      setTooltipAlignment("left");
    } else {
      setTooltipAlignment("center");
    }
    setHoveredIndex(nearest);
  }
  const hovered = hoveredIndex === null ? null : points[hoveredIndex];
  return (
    <div
      className="summary-chart"
      onMouseMove={onMouseMove}
      onMouseLeave={() => setHoveredIndex(null)}
    >
      <span className="summary-chart__range">
        Y min = {valueMin} max = {valueMax}
      </span>
      <svg
        width={props.width}
        height={props.height}
        role="img"
        aria-label={`${props.row.timeserie.name} numeric timeseries chart, range ${scale.min} to ${scale.max}`}
      >
        <line className="summary-chart__baseline" x1={0} x2={props.width} y1={y(0)} y2={y(0)} />
        <path className="summary-chart__line" d={path} />
        {points.map((point) => (
          <circle
            key={`${point.date.toISOString()}:${point.value}`}
            className="summary-chart__point"
            cx={point.x}
            cy={point.y}
            r={3}
          />
        ))}
      </svg>
      {hovered ? (
        <span
          className={`summary-chart__tooltip summary-chart__tooltip--${tooltipAlignment}`}
          style={{ left: hovered.x }}
          role="status"
        >
          {formatTimelineDate(hovered.date)}: {hovered.value} {props.row.timeserie.unit}
        </span>
      ) : null}
    </div>
  );
}
