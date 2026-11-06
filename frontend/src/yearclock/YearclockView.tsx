import { useRef, useState, type KeyboardEvent, type MouseEvent } from "react";

import type { Label, YearclockCategory, YearclockEvent } from "../organization-client";
import { describeEvent } from "./displays/describe";
import { dateLabel, formatDay } from "./displays/format";
import { placeEvents, type Placed, type PlacementLane } from "./displays/placement";
import {
  arcPath,
  dateAt,
  laneBands,
  dayTicks,
  monthScale,
  quarterScale,
  weekScale,
  polar,
  sectorPath,
  todayFraction,
  type PlanningWindow,
} from "./geometry";

export type YearclockViewMessages = {
  /** Change marks since the Previous Visit (Yearclock V2). */
  marks?: { new: string; changed: string };
  shellLabel: (name: string, from: string, to: string) => string;
  labels: (names: string) => string;
  today: string;
  elapsed: (percent: number) => string;
  summaryTitle: string;
  empty: string;
  occurrences: (count: number) => string;
  pointEvent: string;
  rangeEvent: string;
  exception: string;
  recurring: string;
  continuesBefore: string;
  continuesAfter: string;
  createHint: string;
};

type Lane = PlacementLane;

const SIZE = 400;
const CENTER = { x: SIZE / 2, y: SIZE / 2 };
const RING_OUTER = 168;
const RING_INNER = 60;
const SCALE_RADIUS = 184;
// Width of each optional week or quarter ring (Yearclock V2).
const SCALE_RING = 14;
const NEUTRAL = "#4a5a67";

export { dateLabel, formatDay } from "./displays/format";

export function YearclockView({
  name,
  locale,
  window,
  today,
  lanes,
  categories,
  labels = [],
  events,
  selectedId,
  onSelect,
  onCreateAt,
  copy,
  startMonth = 1,
  showWeeks = false,
  showQuarters = false,
  marks,
}: {
  marks?: ReadonlyMap<string, "new" | "changed">;
  startMonth?: number;
  showWeeks?: boolean;
  showQuarters?: boolean;
  name: string;
  locale: string;
  window: PlanningWindow;
  today: string;
  lanes: Lane[];
  categories: YearclockCategory[];
  labels?: Label[];
  events: YearclockEvent[];
  selectedId: string | null;
  onSelect: (eventId: string) => void;
  onCreateAt?: (laneId: string, date: string) => void;
  copy: YearclockViewMessages;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  // Optional time-scale rings sit just inside the month ring; the Lanes narrow to make room.
  const quarterBand = showQuarters ? { inner: RING_OUTER - SCALE_RING, outer: RING_OUTER } : null;
  const weekOuter = RING_OUTER - (showQuarters ? SCALE_RING : 0);
  const weekBand = showWeeks ? { inner: weekOuter - SCALE_RING, outer: weekOuter } : null;
  const laneOuter = RING_OUTER - (Number(showQuarters) + Number(showWeeks)) * SCALE_RING;
  const bands = laneBands(lanes.length, RING_INNER, laneOuter, lanes.map((lane) => (lane.height === "tall" ? 2 : 1)));
  const placed = placeEvents(events, lanes, window);
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const labelNames = labelNamer(labels);
  const laneName = (index: number) => lanes[index]?.name ?? "";
  const now = todayFraction(today, window);
  const monthFormat = new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { month: "short", timeZone: "UTC" });
  const rangeFormat = new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
  const from = rangeFormat.format(new Date(`${window.start}T00:00:00Z`));
  const to = rangeFormat.format(new Date(`${window.end}T00:00:00Z`));
  const seriesLabelled = new Set<string>();
  const preview = previewId ? placed.find((item) => item.event.id === previewId) ?? null : null;

  const describe = (item: Placed) => describeEvent(item, { locale, laneName, categoryName: (categoryId) => (categoryId ? categoryById.get(categoryId)?.name : undefined), labelNames, marks, copy });

  function activate(event: KeyboardEvent, eventId: string) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(eventId);
    }
  }

  function createAt(event: MouseEvent<SVGCircleElement>, laneId: string) {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix || !onCreateAt) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    onCreateAt(laneId, dateAt(point, CENTER, window));
  }

  return (
    <div className="yc-view">
      <svg ref={svgRef} className="yc-svg" viewBox={`0 0 ${SIZE} ${SIZE}`} role="group" aria-label={copy.shellLabel(name, from, to)}>
        <g aria-hidden="true">
          {now ? <path className="yc-elapsed" d={sectorPath(CENTER, RING_INNER, RING_OUTER + 8, 0, now.elapsed)} /> : null}
          <circle className="yc-ring" cx={CENTER.x} cy={CENTER.y} r={RING_OUTER + 8} />
          {bands.map((band, index) => (lanes[index].unavailable ? <circle key={`gone-${lanes[index].id}`} className="yc-lane-unavailable" cx={CENTER.x} cy={CENTER.y} r={band.middle} strokeWidth={band.outer - band.inner} /> : null))}
          {bands.map((band, index) => (lanes[index].tint ? <circle key={`tint-${lanes[index].id}`} className="yc-lane-tint" cx={CENTER.x} cy={CENTER.y} r={band.middle} strokeWidth={band.outer - band.inner} stroke={lanes[index].tint!} /> : null))}
          {bands.map((band, index) => (
            <circle key={lanes[index].id} className="yc-lane" cx={CENTER.x} cy={CENTER.y} r={band.inner} />
          ))}
          {monthScale(window).map((month) => {
            const inner = polar(CENTER, RING_INNER, month.from);
            const outer = polar(CENTER, RING_OUTER + 8, month.from);
            const label = polar(CENTER, SCALE_RADIUS, (month.from + month.to) / 2);
            return (
              <g key={month.month}>
                <line className="yc-month-line" x1={inner.x} y1={inner.y} x2={outer.x} y2={outer.y} />
                {window.months > 1 ? (
                  <text className="yc-month-label" x={label.x} y={label.y} textAnchor="middle" dominantBaseline="middle">
                    {monthFormat.format(new Date(`${month.month}T00:00:00Z`))}
                  </text>
                ) : null}
              </g>
            );
          })}
          {[{ band: quarterBand, segments: showQuarters ? quarterScale(window, startMonth) : [], kind: "quarter" }, { band: weekBand, segments: showWeeks ? weekScale(window) : [], kind: "week" }].map(({ band, segments, kind }) =>
            band ? (
              <g key={kind} className={`yc-scale yc-scale--${kind}`}>
                <circle className="yc-scale-edge" cx={CENTER.x} cy={CENTER.y} r={band.inner} />
                {segments.map((segment, index) => {
                  const inner = polar(CENTER, band.inner, segment.from);
                  const outer = polar(CENTER, band.outer, segment.from);
                  const label = polar(CENTER, (band.inner + band.outer) / 2, (segment.from + segment.to) / 2);
                  return (
                    <g key={`${kind}-${index}`}>
                      {segment.from > 0 ? <line className="yc-scale-line" x1={inner.x} y1={inner.y} x2={outer.x} y2={outer.y} /> : null}
                      {segment.labelled ? <text className={`yc-scale-label yc-${kind}-label`} x={label.x} y={label.y} textAnchor="middle" dominantBaseline="middle">{segment.label}</text> : null}
                    </g>
                  );
                })}
              </g>
            ) : null,
          )}
          {dayTicks(window).map((tick) => {
            const inner = polar(CENTER, RING_OUTER + 2, tick.at);
            const outer = polar(CENTER, RING_OUTER + (tick.labelled ? 8 : 5), tick.at);
            const label = polar(CENTER, SCALE_RADIUS, (tick.day - 0.5) / window.days);
            return (
              <g key={`day-${tick.day}`}>
                <line className="yc-day-tick" x1={inner.x} y1={inner.y} x2={outer.x} y2={outer.y} />
                {tick.labelled ? <text className="yc-day-label" x={label.x} y={label.y} textAnchor="middle" dominantBaseline="middle">{tick.day}</text> : null}
              </g>
            );
          })}
          {onCreateAt
            ? bands.map((band, index) => lanes[index].readOnly ? null : (
                <circle
                  key={`hit-${lanes[index].id}`}
                  className="yc-lane-hit"
                  cx={CENTER.x}
                  cy={CENTER.y}
                  r={band.middle}
                  strokeWidth={band.outer - band.inner}
                  onClick={(event) => createAt(event, lanes[index].id)}
                >
                  <title>{`${copy.createHint}: ${lanes[index].name}`}</title>
                </circle>
              ))
            : null}
          {now ? (
            <>
              <line
                className="yc-today"
                x1={polar(CENTER, RING_INNER - 6, now.at).x}
                y1={polar(CENTER, RING_INNER - 6, now.at).y}
                x2={polar(CENTER, RING_OUTER + 12, now.at).x}
                y2={polar(CENTER, RING_OUTER + 12, now.at).y}
              />
              {preview ? null : <text className="yc-center-label" x={CENTER.x} y={CENTER.y - 8} textAnchor="middle">{copy.today}</text>}
              {preview ? null : <text className="yc-center-value" x={CENTER.x} y={CENTER.y + 12} textAnchor="middle">{formatDay(today, locale)}</text>}
            </>
          ) : preview ? null : (
            <text className="yc-center-label" x={CENTER.x} y={CENTER.y + 4} textAnchor="middle">{from.split(" ").pop()}</text>
          )}
          {preview ? (
            <g className="yc-preview">
              <text className="yc-preview-title" x={CENTER.x} y={CENTER.y - 12} textAnchor="middle">{shorten(preview.event.title, 22)}</text>
              <text className="yc-preview-meta" x={CENTER.x} y={CENTER.y + 4} textAnchor="middle">{dateLabel(preview.event, locale)}</text>
              <text className="yc-preview-meta" x={CENTER.x} y={CENTER.y + 18} textAnchor="middle">{shorten(laneName(preview.laneIndex), 22)}</text>
            </g>
          ) : null}
        </g>
        {placed.map((item) => {
          const band = bands[item.laneIndex];
          const width = band.outer - band.inner;
          const color = (item.event.category_id && categoryById.get(item.event.category_id)?.color) || NEUTRAL;
          const isRange = Boolean(item.event.ends_on && item.event.ends_on !== item.event.starts_on);
          const classes = ["yc-marker", marks?.has(item.event.id) ? `yc-marked yc-marked--${marks.get(item.event.id)}` : "", item.event.exception ? "yc-exception" : "", item.event.id === selectedId ? "yc-selected" : "", item.dense ? "yc-dense" : ""].filter(Boolean).join(" ");
          const common = {
            className: classes,
            tabIndex: 0,
            role: "button",
            "aria-label": describe(item),
            "aria-pressed": item.event.id === selectedId,
            onClick: () => onSelect(item.event.id),
            onKeyDown: (event: KeyboardEvent) => activate(event, item.event.id),
            onMouseEnter: () => setPreviewId(item.event.id),
            onFocus: () => setPreviewId(item.event.id),
            onMouseLeave: () => setPreviewId((current) => (current === item.event.id ? null : current)),
            onBlur: () => setPreviewId((current) => (current === item.event.id ? null : current)),
          } as const;
          let seriesLabel = null;
          if (item.dense && item.event.series_id && !seriesLabelled.has(item.event.series_id)) {
            seriesLabelled.add(item.event.series_id);
            const at = polar(CENTER, band.inner - 6, (item.from + item.to) / 2);
            seriesLabel = <text className="yc-series-label" x={at.x} y={at.y} textAnchor="middle" aria-hidden="true">{item.event.title}</text>;
          }
          if (isRange) {
            return (
              <g key={item.event.id}>
                <path {...common} d={arcPath(CENTER, band.middle, item.from, item.to)} stroke={color} strokeWidth={Math.max(width * 0.5, 4)} fill="none" />
                {seriesLabel}
              </g>
            );
          }
          const at = polar(CENTER, band.middle, (item.from + item.to) / 2);
          const radius = item.dense ? 2.8 : Math.min(Math.max(width * 0.22, 4), 7);
          return (
            <g key={item.event.id}>
              {item.event.exception ? (
                <rect {...common} x={at.x - radius} y={at.y - radius} width={radius * 2} height={radius * 2} transform={`rotate(45 ${at.x} ${at.y})`} fill={color} />
              ) : (
                <circle {...common} cx={at.x} cy={at.y} r={radius} fill={color} />
              )}
              {seriesLabel}
            </g>
          );
        })}
      </svg>
      {now ? <p className="yc-elapsed-text m-0 mt-1 text-center text-[13px] text-ink-muted">{copy.elapsed(Math.round(now.elapsed * 100))}</p> : null}
    </div>
  );
}

export function EventSummary({
  locale,
  lanes,
  categories,
  labels = [],
  events,
  window,
  selectedId,
  onSelect,
  copy,
  selection,
  marks,
}: {
  marks?: ReadonlyMap<string, "new" | "changed">;
  locale: string;
  lanes: Lane[];
  categories: YearclockCategory[];
  labels?: Label[];
  events: YearclockEvent[];
  window: PlanningWindow;
  selectedId: string | null;
  onSelect: (eventId: string) => void;
  copy: YearclockViewMessages;
  selection?: { chosen: ReadonlySet<string>; onToggle: (eventId: string) => void; blocked: (event: YearclockEvent) => boolean; label: (title: string, date: string) => string; noteId: string };
}) {
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => new Set());
  const placed = placeEvents(events, lanes, window);
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const labelById = new Map(labels.map((label) => [label.id, label]));
  const denseGroups = new Map<string, Placed[]>();
  for (const item of placed) {
    if (item.dense && item.event.series_id) denseGroups.set(item.event.series_id, [...(denseGroups.get(item.event.series_id) ?? []), item]);
  }
  const shown = new Set<string>();
  const entry = (item: Placed) => {
    const category = item.event.category_id ? categoryById.get(item.event.category_id) : undefined;
    const checkbox = selection ? (
      <input
        type="checkbox"
        className="yc-bulk-check mt-1.5 size-5 flex-none accent-[var(--color-accent)]"
        aria-label={selection.label(item.event.title, dateLabel(item.event, locale))}
        aria-describedby={selection.blocked(item.event) ? selection.noteId : undefined}
        disabled={selection.blocked(item.event)}
        checked={selection.chosen.has(item.event.id)}
        onChange={() => selection.onToggle(item.event.id)}
      />
    ) : null;
    return (
      <>
      {checkbox}
      <button type="button" className="yc-summary-item w-full pointer-coarse:min-h-11 pointer-coarse:py-2 cursor-pointer rounded-[6px] border border-solid border-transparent bg-transparent px-1.5 py-1 text-left font-[inherit] text-[13px] text-ink hover:bg-surface-subtle aria-pressed:border-ink aria-pressed:font-semibold" aria-pressed={item.event.id === selectedId} onClick={() => onSelect(item.event.id)}>
        <span aria-hidden="true" className="yc-summary-shape">{item.event.ends_on && item.event.ends_on !== item.event.starts_on ? "▬" : item.event.exception ? "◆" : "●"}</span>{" "}
        <span>{dateLabel(item.event, locale)}</span>{" "}
        <strong>{item.event.title}</strong>
        {marks?.get(item.event.id) && copy.marks ? <> <span className={`yc-mark yc-mark--${marks.get(item.event.id)} rounded-[3px] border border-solid border-warning-ink bg-warning-soft px-1 text-[11px] text-warning-ink`}>{copy.marks[marks.get(item.event.id)!]}</span></> : null}
        <span className="yc-summary-meta text-ink-muted">
          {" — "}{lanes[item.laneIndex]?.name}
          {category ? <> · <span className="yc-swatch inline-block size-[0.8em] rounded-[2px] border border-ink align-[-0.05em]" style={{ background: category.color ?? NEUTRAL }} aria-hidden="true" /> {category.name}</> : null}
          {(item.event.label_ids ?? []).map((labelId) => labelById.get(labelId)).filter((label): label is Label => label !== undefined).map((label) => <span key={label.id} className="yc-label-chip"> · <span className="label-swatch inline-block size-[0.8em] rounded-full align-middle" style={{ background: label.color }} aria-hidden="true" /> {label.name}</span>)}
          {item.event.exception ? ` · ${copy.exception}` : ""}
          {item.clippedStart ? ` · ${copy.continuesBefore}` : ""}
          {item.clippedEnd ? ` · ${copy.continuesAfter}` : ""}
        </span>
      </button>
      </>
    );
  };
  return (
    <section className="yc-summary flex flex-col gap-2" aria-label={copy.summaryTitle}>
      <h4 className="m-0 text-sm font-semibold">{copy.summaryTitle}</h4>
      {placed.length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{copy.empty}</p> : null}
      <ol className="m-0 flex list-none flex-col gap-1 p-0">
        {placed.map((item) => {
          const seriesId = item.event.series_id;
          if (item.dense && seriesId) {
            if (shown.has(seriesId)) return null;
            shown.add(seriesId);
            const group = denseGroups.get(seriesId) ?? [];
            return (
              <li key={`series-${seriesId}`}>
                <details
                  open={openGroups.has(seriesId) || group.some((member) => member.event.id === selectedId)}
                  onToggle={(event) => {
                    const isOpen = event.currentTarget.open;
                    setOpenGroups((current) => {
                      const next = new Set(current);
                      if (isOpen) next.add(seriesId); else next.delete(seriesId);
                      return next;
                    });
                  }}
                >
                  <summary className="cursor-pointer rounded-[6px] px-1.5 py-1 text-[13px]">
                    <strong>{item.event.title}</strong> — {copy.recurring}, {copy.occurrences(group.length)}
                  </summary>
                  <ol className="m-0 mt-1 flex list-none flex-col gap-1 p-0 pl-4">{group.map((member) => <li key={member.event.id} className={selection ? "flex items-start gap-1" : undefined}>{entry(member)}</li>)}</ol>
                </details>
              </li>
            );
          }
          return <li key={item.event.id} className={selection ? "flex items-start gap-1" : undefined}>{entry(item)}</li>;
        })}
      </ol>
    </section>
  );
}

/** Names of an Event's Labels, in the order the API returns them. */
export function labelNamer(labels: Label[]): (event: YearclockEvent) => string[] {
  const byId = new Map(labels.map((label) => [label.id, label.name]));
  return (event) => (event.label_ids ?? []).map((labelId) => byId.get(labelId)).filter((name): name is string => name !== undefined);
}

/** Shorten text for the small circle centre, ending with an ellipsis. */
function shorten(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}…` : text;
}
