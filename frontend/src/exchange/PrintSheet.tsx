import { useEffect, useState } from "react";

import type { PlannerMessages } from "../i18n";
import type { YearclockCategory, YearclockEvent } from "../organization-client";
import { buildRows } from "../yearclock/displays/list";
import { dateLabel, formatDay } from "../yearclock/displays/format";
import { placeEvents, type PlacementLane } from "../yearclock/displays/placement";
import type { Display } from "../yearclock/displays/display-mode";
import type { PlanningWindow } from "../yearclock/geometry";

const NEUTRAL = "#4a5a67";

/** The time shown in the printout, taken again when the print dialog opens. */
function usePrintTime(locale: string): string {
  const format = () => new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { dateStyle: "medium", timeStyle: "short" }).format(new Date());
  const [time, setTime] = useState(format);
  useEffect(() => {
    const refresh = () => setTime(format());
    globalThis.addEventListener("beforeprint", refresh);
    return () => globalThis.removeEventListener("beforeprint", refresh);
  }, [locale]);
  return time;
}

/** Name, Planning Window, and print time above a printout; hidden on screen. */
export function PrintHeader({ name, window, locale, copy }: { name: string; window: PlanningWindow; locale: string; copy: PlannerMessages["exchange"] }) {
  const time = usePrintTime(locale);
  return (
    <header className="yc-print-header hidden print:block">
      <h1 className="m-0 text-xl font-semibold">{name}</h1>
      <p className="m-0 text-[13px]">{formatDay(window.start, locale)} – {formatDay(window.end, locale)} · {copy.printed(time)}</p>
    </header>
  );
}

/** Legend and, for the circle and the timeline, the Event list below a printout; hidden on screen. */
export function PrintAppendix({ window, locale, display, lanes, categories, events, copy, listCopy, summaryTitle, recurring, occurrences }: {
  window: PlanningWindow;
  locale: string;
  display: Display;
  lanes: PlacementLane[];
  categories: YearclockCategory[];
  events: YearclockEvent[];
  copy: PlannerMessages["exchange"];
  listCopy: PlannerMessages["list"];
  summaryTitle: string;
  recurring: string;
  occurrences: (count: number) => string;
}) {
  const showList = display === "circle" || display === "timeline";
  const rows = showList ? buildRows(placeEvents(events, lanes, window)) : [];
  const categoryName = (id: string | null) => categories.find((category) => category.id === id)?.name ?? "";
  return (
    <div className="yc-print-appendix hidden flex-col gap-3 text-[12px] print:flex">
      <section className="yc-print-legend flex flex-col gap-1" aria-label={copy.legend}>
        <h2 className="m-0 text-sm font-semibold">{copy.legend}</h2>
        <p className="m-0"><strong>{copy.lanes}:</strong> {lanes.map((lane) => lane.name).join(", ")}</p>
        {categories.length ? <p className="m-0 flex flex-wrap items-center gap-x-4 gap-y-1"><strong>{copy.categories}:</strong>{categories.map((category) => <span key={category.id} className="inline-flex items-center gap-1"><span className="inline-block size-3 border border-ink" style={{ background: category.color ?? NEUTRAL, printColorAdjust: "exact" }} />{category.name}</span>)}</p> : null}
      </section>
      {showList ? (
        <section className="yc-print-events" aria-label={summaryTitle}>
          <h2 className="m-0 mb-1 text-sm font-semibold">{summaryTitle}</h2>
          <table className="w-full border-collapse">
            <thead><tr>{[listCopy.date, listCopy.title, listCopy.lane, listCopy.category].map((heading) => <th key={heading} className="border-b border-ink px-2 py-1 text-left font-semibold">{heading}</th>)}</tr></thead>
            <tbody>
              {rows.map((row) => row.kind === "series"
                ? <tr key={`s-${row.seriesId}`}><td className="border-b border-line px-2 py-1">{dateLabel(row.items[0].event, locale)}</td><td className="border-b border-line px-2 py-1"><strong>{row.title}</strong> — {recurring}, {occurrences(row.items.length)}</td><td className="border-b border-line px-2 py-1">{lanes[row.items[0].laneIndex]?.name}</td><td className="border-b border-line px-2 py-1">{categoryName(row.items[0].event.category_id)}</td></tr>
                : <tr key={row.item.event.id}><td className="border-b border-line px-2 py-1">{dateLabel(row.item.event, locale)}</td><td className="border-b border-line px-2 py-1">{row.item.event.title}{row.item.event.location ? <span className="block text-ink-muted">{row.item.event.location}</span> : null}{(row.item.event.links ?? []).map((link) => <span key={link.url} className="block text-ink-muted">{link.title}: {link.url}</span>)}</td><td className="border-b border-line px-2 py-1">{lanes[row.item.laneIndex]?.name}</td><td className="border-b border-line px-2 py-1">{categoryName(row.item.event.category_id)}</td></tr>)}
            </tbody>
          </table>
        </section>
      ) : null}
    </div>
  );
}
