import { useEffect, useRef } from "react";

import type { Label, YearclockCategory, YearclockEvent } from "../../organization-client";
import { cx } from "../../ui";
import { labelNamer, type YearclockViewMessages } from "../YearclockView";
import type { PlanningWindow } from "../geometry";
import { groupAgenda } from "./agenda";
import { describeEvent } from "./describe";
import { timeLabel } from "./format";
import { placeEvents, type Placed, type PlacementLane } from "./placement";

const intl = (locale: string) => (locale === "fi" ? "fi-FI" : "en-GB");

/** The window's Events day by day, grouped by month, with weekday names; the circle above shows the same selection (Yearclock V2 P5). */
export function AgendaDisplay({ locale, window, lanes, categories, labels, events, selectedId, onSelect, marks, copy }: {
  locale: string;
  window: PlanningWindow;
  lanes: PlacementLane[];
  categories: YearclockCategory[];
  labels: Label[];
  events: YearclockEvent[];
  selectedId: string | null;
  onSelect: (eventId: string) => void;
  marks?: ReadonlyMap<string, "new" | "changed">;
  copy: YearclockViewMessages;
}) {
  const placed = placeEvents(events, lanes, window);
  const months = groupAgenda(placed, window.start);
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const labelNames = labelNamer(labels);
  const describe = (item: Placed) => describeEvent(item, { locale, laneName: (index) => lanes[index]?.name ?? "", categoryName: (id) => (id ? categoryById.get(id)?.name : undefined), labelNames, marks, copy });
  const monthName = (month: string) => new Intl.DateTimeFormat(intl(locale), { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${month}-01T00:00:00Z`));
  const dayName = (date: string) => new Intl.DateTimeFormat(intl(locale), { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`));
  const selectedRow = useRef<HTMLButtonElement | null>(null);
  // A selection made on the circle brings its row into view inside the agenda, without moving the page.
  useEffect(() => {
    const row = selectedRow.current;
    const box = row?.closest<HTMLElement>("[data-agenda-scroll]");
    if (row && box) {
      const top = row.offsetTop - box.offsetTop;
      if (top < box.scrollTop || top + row.offsetHeight > box.scrollTop + box.clientHeight) box.scrollTop = Math.max(0, top - box.clientHeight / 3);
    }
  }, [selectedId]);

  return (
    <section className="yc-agenda flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-3 shadow-[var(--shadow-card)] sm:p-4" aria-label={copy.summaryTitle}>
      {months.length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{copy.empty}</p> : null}
      <div data-agenda-scroll className="relative flex max-h-[28rem] flex-col gap-4 overflow-y-auto">
        {months.map((month) => (
          <div key={month.month} className="flex flex-col gap-2">
            <h3 className="sticky top-0 z-10 m-0 bg-surface py-1 text-sm font-semibold capitalize">{monthName(month.month)}</h3>
            <ol className="m-0 flex list-none flex-col gap-3 p-0">
              {month.days.map((day) => (
                <li key={day.date} className="flex flex-col gap-1">
                  <h4 className="yc-agenda-day m-0 text-xs font-semibold uppercase tracking-wide text-ink-muted">{dayName(day.date)}</h4>
                  <ul className="m-0 flex list-none flex-col gap-1 p-0">
                    {day.items.map((item) => {
                      const selected = item.event.id === selectedId;
                      const category = item.event.category_id ? categoryById.get(item.event.category_id) : undefined;
                      const mark = marks?.get(item.event.id);
                      return (
                        <li key={item.event.id}>
                          <button type="button" ref={selected ? selectedRow : undefined} aria-label={describe(item)} aria-pressed={selected} onClick={() => onSelect(item.event.id)} className={cx("yc-agenda-item flex min-h-8 w-full cursor-pointer flex-wrap items-center gap-x-2 rounded-[6px] border border-solid px-2 py-1 text-left font-[inherit] text-[13px] text-ink pointer-coarse:min-h-11", selected ? "border-ink bg-accent-soft font-semibold" : "border-transparent bg-transparent hover:bg-surface-subtle")}>
                            {category ? <span className="yc-swatch inline-block size-[0.8em] shrink-0 rounded-[2px] border border-ink" style={{ background: category.color ?? "#4a5a67" }} aria-hidden="true" /> : null}
                            {item.event.starts_at ? <span className="tabular-nums text-ink-muted">{timeLabel(item.event)}</span> : null}
                            <span className="font-semibold">{item.event.title}</span>
                            {mark ? <span className="yc-mark rounded-[3px] border border-solid border-warning-ink bg-warning-soft px-1 text-[11px] font-normal text-warning-ink">{copy.marks?.[mark]}</span> : null}
                            <span className="text-ink-muted">{lanes[item.laneIndex]?.name}{category ? ` · ${category.name}` : ""}{item.event.location ? ` · ${item.event.location}` : ""}{item.clippedStart ? ` · ${copy.continuesBefore}` : ""}{item.clippedEnd ? ` · ${copy.continuesAfter}` : ""}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </section>
  );
}
