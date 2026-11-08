import { Pencil, Plus } from "lucide-react";
import { useId } from "react";

import type { Locale } from "../../i18n";
import { Badge, Button, IconButton, cx } from "../../ui";
import type { LineEvent } from "../client";
import { eventRows } from "../timeline";
import { timelineMessages } from "../timeline-messages";

/**
 * The events of the shown line, oldest first, with a "Now" divider between the last event that has happened and the first planned one.
 * A planned event is marked by a dashed amber frame and the word "Planned" (never by colour alone); a Scenario that starts from an
 * event shows as a small badge on it. Choosing an event shows the state after it on the canvas.
 */
export function EventPanel({ lineName, events, selectedId, canWrite, locale, onSelect, onEdit, onNew, onOpenLine }: {
  lineName: string; events: readonly LineEvent[]; selectedId: string | null; canWrite: boolean; locale: Locale;
  onSelect: (event: LineEvent) => void; onEdit: (event: LineEvent) => void; onNew: () => void; onOpenLine: (lineId: string) => void;
}) {
  const text = timelineMessages(locale);
  const heading = useId();
  const rows = eventRows(events, selectedId);
  return (
    <section aria-labelledby={heading} className="flex min-h-0 min-w-0 flex-col gap-2 rounded-[var(--radius-card)] border border-line bg-surface p-3">
      <div className="flex items-center gap-2">
        <h2 id={heading} className="m-0 min-w-0 flex-1 truncate text-sm font-semibold">{text.eventsOf(lineName)}</h2>
        {canWrite ? <Button size="sm" icon={<Plus size={14} />} onClick={onNew}>{text.newEvent}</Button> : null}
      </div>
      {events.length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{text.noEvents}</p> : null}
      <ol aria-labelledby={heading} className="m-0 flex min-h-0 list-none flex-col gap-1.5 overflow-auto p-0">
        {rows.map((row) => row.kind === "now" ? (
          <li key="now" className="flex items-center gap-2 text-[12px] font-semibold text-accent" data-testid="now-divider">
            <span aria-hidden="true" className="h-px flex-1 bg-accent" />{text.now}<span aria-hidden="true" className="h-px flex-1 bg-accent" />
          </li>
        ) : (
          <li key={row.event.id} data-planned={row.event.planned ? "true" : "false"}
            className={cx("flex flex-col gap-1 rounded-[var(--radius-control)] border px-2 py-1.5",
              row.event.planned ? "border-dashed border-warning-line bg-warning-soft" : "border-line bg-surface",
              row.selected && "outline outline-2 outline-accent")}>
            <div className="flex items-start gap-1">
              <button type="button" aria-current={row.selected ? "true" : undefined} onClick={() => onSelect(row.event)}
                className="flex min-w-0 flex-1 cursor-pointer flex-col gap-0.5 border-0 bg-transparent p-0 text-left font-[inherit] text-ink">
                <span className="text-[12px] text-ink-muted"><time dateTime={row.event.occurred_on}>{row.event.occurred_on}</time>{row.selected ? ` · ${text.shown}` : ""}</span>
                <span className="break-words text-[13px] font-medium">{row.event.title}</span>
                <span className="flex flex-wrap items-center gap-1.5 text-[12px] text-ink-muted">
                  {row.event.planned ? <Badge tone="warning">{text.planned}</Badge> : null}
                  <span>{text.changesCount(row.event.change_count)}</span>
                </span>
              </button>
              {<IconButton size="sm" variant="ghost" label={text.editEvent(row.event.title)} icon={<Pencil size={14} />} onClick={() => onEdit(row.event)} />}
            </div>
            {(row.event.branches ?? []).length > 0 ? (
              <ul aria-label={text.scenario} className="m-0 flex list-none flex-wrap gap-1 p-0">
                {(row.event.branches ?? []).map((branch) => (
                  <li key={branch.line_id}><button type="button" title={text.branchBadgeOpen(branch.name)} onClick={() => onOpenLine(branch.line_id)} className="cursor-pointer rounded-full border border-line bg-surface-sunken px-2 py-0.5 text-[11px] font-semibold text-ink-muted hover:text-ink">{text.branchBadge(branch.name)}</button></li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
