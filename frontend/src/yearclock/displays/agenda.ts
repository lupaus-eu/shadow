import type { Placed } from "./placement";

export type AgendaDay = { date: string; items: Placed[] };
export type AgendaMonth = { month: string; days: AgendaDay[] };

/**
 * Group Events by month and day for the agenda. An Event is listed on its
 * start date, or on the first day of the window when it began earlier; items
 * of a day keep the focus order (Lane, then identity).
 */
export function groupAgenda(placed: Placed[], windowStart: string): AgendaMonth[] {
  const days = new Map<string, Placed[]>();
  for (const item of placed) {
    const date = item.clippedStart || item.event.starts_on < windowStart ? windowStart : item.event.starts_on;
    days.set(date, [...(days.get(date) ?? []), item]);
  }
  const months: AgendaMonth[] = [];
  for (const date of [...days.keys()].sort()) {
    const month = date.slice(0, 7);
    const items = (days.get(date) ?? []).sort((a, b) => (a.event.starts_at ?? "").localeCompare((b.event.starts_at ?? "")) || a.laneIndex - b.laneIndex || a.event.id.localeCompare(b.event.id));
    const current = months.at(-1);
    if (current && current.month === month) current.days.push({ date, items });
    else months.push({ month, days: [{ date, items }] });
  }
  return months;
}
