import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import type { Label, YearclockCategory, YearclockEvent } from "../../organization-client";
import type { PlannerMessages } from "../../i18n";
import { cx, Select } from "../../ui";
import { labelNamer, type YearclockViewMessages } from "../YearclockView";
import type { PlanningWindow } from "../geometry";
import { describeEvent } from "./describe";
import { dateLabel } from "./format";
import { DEFAULT_SORT, buildRows, nextSort, type ListRow, type Sort, type SortKey } from "./list";
import { placeEvents, type Placed, type PlacementLane } from "./placement";

export type EventSelection = { chosen: ReadonlySet<string>; onToggle: (eventId: string) => void; blocked: (event: YearclockEvent) => boolean; label: (title: string, date: string) => string; noteId: string };

const CELL = "border-t border-line px-3 py-2 align-middle max-sm:block max-sm:border-0 max-sm:px-0 max-sm:py-0.5";
const SORTS: SortKey[] = ["date", "title", "lane"];

/** The Events of the Planning Window as a sortable table, cards on a phone (Yearclock V2 P5). */
export function ListDisplay({ locale, window, lanes, categories, labels, events, selectedId, onSelect, selection, marks, copy, viewCopy }: {
  locale: string;
  window: PlanningWindow;
  lanes: PlacementLane[];
  categories: YearclockCategory[];
  labels: Label[];
  events: YearclockEvent[];
  selectedId: string | null;
  onSelect: (eventId: string) => void;
  selection?: EventSelection;
  marks?: ReadonlyMap<string, "new" | "changed">;
  copy: PlannerMessages["list"];
  viewCopy: YearclockViewMessages;
}) {
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const placed = placeEvents(events, lanes, window);
  const rows = buildRows(placed, sort);
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  const labelById = new Map(labels.map((label) => [label.id, label]));
  const labelNames = labelNamer(labels);
  const describe = (item: Placed) => describeEvent(item, { locale, laneName: (index) => lanes[index]?.name ?? "", categoryName: (id) => (id ? categoryById.get(id)?.name : undefined), labelNames, marks, copy: viewCopy });
  const columns: Array<{ key: SortKey; label: string }> = [{ key: "date", label: copy.date }, { key: "title", label: copy.title }, { key: "lane", label: copy.lane }];
  const columnCount = 5 + (selection ? 1 : 0);

  const eventRow = (item: Placed, nested = false) => {
    const { event } = item;
    const category = event.category_id ? categoryById.get(event.category_id) : undefined;
    const eventLabels = (event.label_ids ?? []).map((id) => labelById.get(id)).filter((label): label is Label => label !== undefined);
    const mark = marks?.get(event.id);
    const selected = event.id === selectedId;
    return (
      <tr key={event.id} className={cx("yc-list-row max-sm:flex max-sm:flex-col max-sm:gap-0.5 max-sm:border-t max-sm:border-line max-sm:px-3 max-sm:py-2", selected && "bg-accent-soft")}>
        {selection ? (
          <td className={cx(CELL, "w-10")}>
            <input type="checkbox" className="size-5 accent-[var(--color-accent)]" aria-label={selection.label(event.title, dateLabel(event, locale))} aria-describedby={selection.blocked(event) ? selection.noteId : undefined} disabled={selection.blocked(event)} checked={selection.chosen.has(event.id)} onChange={() => selection.onToggle(event.id)} />
          </td>
        ) : null}
        <td className={cx(CELL, "whitespace-nowrap text-ink-muted", nested && "pl-8")}><span className="text-xs sm:hidden" aria-hidden="true">{copy.date}: </span>{dateLabel(event, locale)}</td>
        <td className={cx(CELL, "min-w-40")}>
          <button type="button" aria-label={describe(item)} aria-pressed={selected} onClick={() => onSelect(event.id)} className="inline-flex min-h-8 cursor-pointer items-center gap-1.5 border-0 bg-transparent p-0 text-left font-[inherit] text-[13px] font-semibold text-ink hover:underline pointer-coarse:min-h-11">
            {event.title}
            {mark ? <span className="yc-mark rounded-[3px] border border-solid border-warning-ink bg-warning-soft px-1 text-[11px] font-normal text-warning-ink">{viewCopy.marks?.[mark]}</span> : null}
          </button>
          {event.location ? <span className="block text-xs text-ink-muted">{event.location}</span> : null}
        </td>
        <td className={CELL}><span className="text-xs text-ink-muted sm:hidden" aria-hidden="true">{copy.lane}: </span>{lanes[item.laneIndex]?.name}</td>
        <td className={CELL}>
          {category ? <span className="inline-flex items-center gap-1.5"><span className="yc-swatch inline-block size-[0.8em] rounded-[2px] border border-ink" style={{ background: category.color ?? "#4a5a67" }} aria-hidden="true" />{category.name}</span> : <span className="text-ink-muted max-sm:hidden">{copy.none}</span>}
        </td>
        <td className={CELL}>
          {eventLabels.length ? <span className="inline-flex flex-wrap gap-x-3">{eventLabels.map((label) => <span key={label.id} className="inline-flex items-center gap-1"><span className="label-swatch inline-block size-[0.8em] rounded-full" style={{ background: label.color }} aria-hidden="true" />{label.name}</span>)}</span> : <span className="text-ink-muted max-sm:hidden">{copy.none}</span>}
        </td>
      </tr>
    );
  };

  const seriesRows = (row: Extract<ListRow, { kind: "series" }>) => {
    const isOpen = open.has(row.seriesId) || row.items.some((entry) => entry.event.id === selectedId);
    return [
      <tr key={`series-${row.seriesId}`} className="yc-list-series max-sm:block max-sm:border-t max-sm:border-line max-sm:px-3 max-sm:py-2">
        <td colSpan={columnCount} className={cx(CELL, "max-sm:block")}>
          <button type="button" aria-expanded={isOpen} onClick={() => setOpen((current) => { const next = new Set(current); if (isOpen) next.delete(row.seriesId); else next.add(row.seriesId); return next; })} className="inline-flex min-h-8 cursor-pointer items-center gap-1.5 border-0 bg-transparent p-0 text-left font-[inherit] text-[13px] text-ink pointer-coarse:min-h-11">
            {isOpen ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
            <strong className="font-semibold">{row.title}</strong> — {viewCopy.recurring}, {viewCopy.occurrences(row.items.length)}
          </button>
        </td>
      </tr>,
      ...(isOpen ? row.items.map((entry) => eventRow(entry, true)) : []),
    ];
  };

  return (
    <section className="yc-list flex flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-3 shadow-[var(--shadow-card)] sm:p-4" aria-label={viewCopy.summaryTitle}>
      <div className="flex items-center gap-2 sm:hidden">
        <label htmlFor="yc-list-sort" className="text-[13px] font-medium">{copy.sortBy}</label>
        <Select id="yc-list-sort" className="w-40" value={sort.key} onChange={(event) => setSort({ key: event.target.value as SortKey, direction: "asc" })}>{SORTS.map((key) => <option key={key} value={key}>{columns.find((column) => column.key === key)?.label}</option>)}</Select>
      </div>
      {rows.length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{viewCopy.empty}</p> : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <caption className="sr-only">{viewCopy.summaryTitle}</caption>
            <thead className="max-sm:sr-only">
              <tr>
                {selection ? <th scope="col" className="w-10 px-3 py-2 text-left"><span className="sr-only">{copy.select}</span></th> : null}
                {columns.slice(0, 2).map((column) => <SortHeader key={column.key} column={column} sort={sort} onSort={(key) => setSort(nextSort(sort, key))} />)}
                <SortHeader column={columns[2]} sort={sort} onSort={(key) => setSort(nextSort(sort, key))} />
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-ink-muted">{copy.category}</th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-ink-muted">{copy.labels}</th>
              </tr>
            </thead>
            <tbody className="max-sm:block">{rows.flatMap((row) => (row.kind === "event" ? [eventRow(row.item)] : seriesRows(row)))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SortHeader({ column, sort, onSort }: { column: { key: SortKey; label: string }; sort: Sort; onSort: (key: SortKey) => void }) {
  const active = sort.key === column.key;
  return (
    <th scope="col" aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"} className="px-3 py-2 text-left text-xs font-semibold text-ink-muted">
      <button type="button" onClick={() => onSort(column.key)} className="inline-flex min-h-8 cursor-pointer items-center gap-1 border-0 bg-transparent p-0 font-[inherit] text-xs font-semibold text-ink-muted hover:text-ink">
        {column.label}<span aria-hidden="true">{active ? (sort.direction === "asc" ? "▲" : "▼") : ""}</span>
      </button>
    </th>
  );
}
