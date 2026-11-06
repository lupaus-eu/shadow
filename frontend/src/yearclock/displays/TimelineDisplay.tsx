import { useSyncExternalStore, type CSSProperties, type MouseEvent, type ReactNode } from "react";

import type { Label, YearclockCategory, YearclockEvent } from "../../organization-client";
import { cx } from "../../ui";
import { labelNamer, type YearclockViewMessages } from "../YearclockView";
import { dayTicks, monthScale, quarterScale, todayFraction, weekScale, type PlanningWindow } from "../geometry";
import { describeEvent } from "./describe";
import { placeEvents, type Placed, type PlacementLane } from "./placement";
import { DENSE_MARKER_PX, MARKER_PX, axisRows, contentWidth, crossesYear, dateAtFraction, markerSlotPx, packTracks, type Slot } from "./timeline";

const NEUTRAL = "#4a5a67";
const LANE_COLUMN = 168;
const TRACK_PX = 28;
// Touch screens get 44 px rows so every marker and bar is a touch-sized target.
const TOUCH_TRACK_PX = 48;
const BAR_MIN_PX = 28;
const AXIS_ROW_PX = 22;

type Unit = { key: string; kind: "event"; item: Placed } | { key: string; kind: "series"; items: Placed[]; from: number; to: number };

const coarseQuery = "(pointer: coarse)";
const subscribeCoarse = (notify: () => void) => { const list = globalThis.matchMedia?.(coarseQuery); list?.addEventListener("change", notify); return () => list?.removeEventListener("change", notify); };
const isCoarse = () => Boolean(globalThis.matchMedia?.(coarseQuery).matches);

const pct = (fraction: number) => `${fraction * 100}%`;
const isRange = (item: Placed) => Boolean(item.event.ends_on && item.event.ends_on !== item.event.starts_on);
const tint = (color: string, share: number) => `color-mix(in srgb, ${color} ${share}%, transparent)`;

/** Lanes as rows over the Planning Window, with markers and bars; Events change only through the drawer (Yearclock V2 P5). */
export function TimelineDisplay({ locale, window, today, lanes, categories, labels, events, selectedId, onSelect, onCreateAt, marks, startMonth, showWeeks, showQuarters, copy }: {
  locale: string;
  window: PlanningWindow;
  today: string;
  lanes: PlacementLane[];
  categories: YearclockCategory[];
  labels: Label[];
  events: YearclockEvent[];
  selectedId: string | null;
  onSelect: (eventId: string) => void;
  onCreateAt?: (laneId: string, date: string) => void;
  marks?: ReadonlyMap<string, "new" | "changed">;
  startMonth: number;
  showWeeks: boolean;
  showQuarters: boolean;
  copy: YearclockViewMessages;
}) {
  const coarse = useSyncExternalStore(subscribeCoarse, isCoarse, () => false);
  const trackPx = coarse ? TOUCH_TRACK_PX : TRACK_PX;
  const itemPx = trackPx - 8;
  const placed = placeEvents(events, lanes, window);
  const widthPx = contentWidth(window.months);
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const labelNames = labelNamer(labels);
  const describe = (item: Placed) => describeEvent(item, { locale, laneName: (index) => lanes[index]?.name ?? "", categoryName: (id) => (id ? categoryById.get(id)?.name : undefined), labelNames, marks, copy });
  const lng = locale === "fi" ? "fi-FI" : "en-GB";
  const rows = axisRows(window.months, showWeeks, showQuarters);
  const withYear = crossesYear(window.start, window.end);
  const monthLabel = (month: string) => new Intl.DateTimeFormat(lng, window.months === 1 ? { month: "long", year: "numeric", timeZone: "UTC" } : withYear ? { month: "short", year: "2-digit", timeZone: "UTC" } : { month: "short", timeZone: "UTC" }).format(new Date(`${month}T00:00:00Z`));
  const months = monthScale(window);
  const now = todayFraction(today, window);
  const colorOf = (item: Placed) => (item.event.category_id && categoryById.get(item.event.category_id)?.color) || NEUTRAL;

  const unitsOf = (laneIndex: number): Unit[] => {
    const items = placed.filter((item) => item.laneIndex === laneIndex);
    const units: Unit[] = [];
    const groups = new Map<string, Placed[]>();
    for (const item of items) if (item.dense && item.event.series_id) groups.set(item.event.series_id, [...(groups.get(item.event.series_id) ?? []), item]);
    const added = new Set<string>();
    for (const item of items) {
      const seriesId = item.event.series_id;
      if (item.dense && seriesId) {
        if (added.has(seriesId)) continue;
        added.add(seriesId);
        const group = groups.get(seriesId) ?? [];
        units.push({ key: `series-${seriesId}`, kind: "series", items: group, from: Math.min(...group.map((entry) => entry.from)), to: Math.max(...group.map((entry) => entry.to)) });
      } else {
        units.push({ key: item.event.id, kind: "event", item });
      }
    }
    return units;
  };

  const axisCell = (key: string, from: number, to: number, content: string, className?: string) => (
    <div key={key} className={cx("absolute top-0 flex h-full items-center overflow-hidden whitespace-nowrap border-l border-line px-1 text-[11px] text-ink-muted", className)} style={{ left: pct(from), width: pct(to - from) }}>{content}</div>
  );

  const createAt = (laneId: string) => (event: MouseEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget || !onCreateAt) return;
    const box = event.currentTarget.getBoundingClientRect();
    onCreateAt(laneId, dateAtFraction(window.start, window.days, (event.clientX - box.left) / box.width));
  };

  const eventButton = (item: Placed, style: CSSProperties, className: string, children: ReactNode) => {
    const selected = item.event.id === selectedId;
    const mark = marks?.get(item.event.id);
    return (
      <button key={item.event.id} type="button" title={item.event.title} aria-label={describe(item)} aria-pressed={selected}
        data-mark={mark} data-event-id={item.event.id}
        onClick={() => onSelect(item.event.id)}
        className={cx("yc-timeline-item absolute cursor-pointer border-0 bg-transparent p-0 text-left font-[inherit] text-[12px] text-ink", selected && "outline outline-2 outline-offset-1 outline-ink", mark && !selected && "outline outline-2 outline-offset-1 outline-warning-ink", className)}
        style={style}>
        {children}
      </button>
    );
  };

  return (
    <section className="yc-timeline rounded-[var(--radius-card)] border border-line bg-surface shadow-[var(--shadow-card)]" aria-label={copy.summaryTitle}>
      <div className="overflow-x-auto" data-timeline-scroll>
        <div style={{ minWidth: widthPx + LANE_COLUMN }}>
          <div className="grid border-b border-line" style={{ gridTemplateColumns: `${LANE_COLUMN}px 1fr` }} aria-hidden="true">
            <div className="sticky left-0 z-20 border-r border-line bg-surface" />
            <div className="flex flex-col">
              {rows.quarters ? <div className="relative" style={{ height: AXIS_ROW_PX }}>{quarterScale(window, startMonth).map((segment, index) => axisCell(`q${index}`, segment.from, segment.to, segment.label, "font-semibold"))}</div> : null}
              <div className="relative" style={{ height: AXIS_ROW_PX }}>{months.map((month) => axisCell(month.month, month.from, month.to, monthLabel(month.month), "font-semibold text-ink"))}</div>
              {rows.weeks ? <div className="relative" style={{ height: AXIS_ROW_PX }}>{weekScale(window).filter((segment) => segment.labelled || window.months <= 3).map((segment, index) => axisCell(`w${index}`, segment.from, segment.to, segment.label))}</div> : null}
              {rows.days ? <div className="relative" style={{ height: AXIS_ROW_PX }}>{dayTicks(window).map((tick) => axisCell(`d${tick.day}`, tick.at, tick.at + 1 / window.days, String(tick.day), "justify-center px-0 text-[10px]"))}</div> : null}
            </div>
          </div>
          {lanes.map((lane, laneIndex) => {
            const units = unitsOf(laneIndex);
            const slots: Slot[] = units.map((unit) => unit.kind === "series"
              ? { key: unit.key, from: unit.from, to: unit.to, minPx: Math.min(unit.items[0].event.title.length * 6.5 + 8, 168) }
              : { key: unit.key, from: unit.item.from, to: unit.item.to, minPx: isRange(unit.item) ? BAR_MIN_PX : markerSlotPx(unit.item.event.title, true) });
            const { track, count } = packTracks(slots, widthPx);
            const height = Math.max(lane.height === "tall" ? 76 : 44, count * trackPx + 12);
            const editable = Boolean(onCreateAt) && !lane.readOnly && !lane.unavailable;
            return (
              <div key={lane.id} role="group" aria-label={lane.name} className="yc-timeline-lane grid border-b border-line last:border-b-0" style={{ gridTemplateColumns: `${LANE_COLUMN}px 1fr` }}>
                <div className={cx("sticky left-0 z-10 flex items-center border-r border-line bg-surface px-3 py-2 text-[13px] font-semibold", (lane.readOnly || lane.unavailable) && "font-normal italic text-ink-muted")} style={lane.tint ? { backgroundImage: `linear-gradient(${tint(lane.tint, 14)}, ${tint(lane.tint, 14)})` } : undefined}>
                  <span className="truncate" title={lane.name}>{lane.name}</span>
                </div>
                <div className={cx("relative", editable && "cursor-copy", lane.unavailable && "bg-surface-subtle")} style={{ height, ...(lane.tint ? { backgroundColor: tint(lane.tint, 14) } : null) }}
                  title={editable ? copy.createHint : undefined} onClick={editable ? createAt(lane.id) : undefined}>
                  {months.map((month, index) => (index === 0 ? null : <div key={month.month} aria-hidden="true" className="pointer-events-none absolute inset-y-0 border-l border-line" style={{ left: pct(month.from) }} />))}
                  {now ? <div aria-hidden="true" className="yc-timeline-today pointer-events-none absolute inset-y-0 z-[1] w-0.5 bg-danger" style={{ left: pct(now.at) }} /> : null}
                  {units.map((unit) => {
                    const row = track.get(unit.key) ?? 0;
                    const top = 6 + row * trackPx;
                    if (unit.kind === "series") {
                      const span = Math.max(unit.to - unit.from, 0.0001);
                      return (
                        <div key={unit.key} className="yc-timeline-series pointer-events-none absolute" style={{ left: pct(unit.from), width: pct(span), top, height: itemPx }}>
                          <span aria-hidden="true" className="yc-series-label absolute -top-0.5 left-0 whitespace-nowrap text-[11px] font-semibold text-ink">{unit.items[0].event.title}</span>
                          {unit.items.map((item) => {
                            const color = colorOf(item);
                            const exception = item.event.exception;
                            const hit = coarse ? 44 : 16;
                            return eventButton(item, { left: pct((item.from - unit.from) / span), top: itemPx / 2 + 6 - hit / 2 + 4, width: hit, height: hit, marginLeft: -hit / 2 }, "pointer-events-auto yc-dense flex items-center justify-center",
                              <span aria-hidden="true" className={cx("block", exception ? "rounded-none" : "rounded-full")} style={{ width: DENSE_MARKER_PX, height: DENSE_MARKER_PX, background: color, transform: exception ? "rotate(45deg)" : undefined }} />);
                          })}
                        </div>
                      );
                    }
                    const item = unit.item;
                    const color = colorOf(item);
                    if (isRange(item)) {
                      return eventButton(item, { left: pct(item.from), width: pct(item.to - item.from), minWidth: BAR_MIN_PX, top, height: itemPx, backgroundColor: tint(color, 22), borderLeft: item.clippedStart ? undefined : `4px solid ${color}`, borderRight: item.clippedEnd ? undefined : undefined },
                        cx("flex items-center gap-1 overflow-hidden rounded-[4px] px-1.5 leading-none", item.clippedStart && "rounded-l-none", item.clippedEnd && "rounded-r-none"),
                        <>{item.clippedStart ? <span aria-hidden="true">◂</span> : null}<span className="truncate">{item.event.title}</span>{item.clippedEnd ? <span aria-hidden="true" className="ml-auto">▸</span> : null}</>);
                    }
                    return eventButton(item, { left: pct(item.from), top, height: itemPx, minWidth: MARKER_PX }, "flex items-center gap-1.5 whitespace-nowrap leading-none",
                      <><span aria-hidden="true" className={cx("inline-block shrink-0 border border-surface", item.event.exception ? "rotate-45 rounded-none" : "rounded-full")} style={{ width: MARKER_PX - 2, height: MARKER_PX - 2, background: color }} /><span className="max-w-40 truncate">{item.event.title}</span></>);
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
