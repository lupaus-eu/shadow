import type { Placed } from "./placement";

export type SortKey = "date" | "title" | "lane";
export type Sort = { key: SortKey; direction: "asc" | "desc" };
export const DEFAULT_SORT: Sort = { key: "date", direction: "asc" };

/** A table row: one Event, or a dense Series collapsed into one expandable row, as in the Events list. */
export type ListRow = { kind: "event"; item: Placed } | { kind: "series"; seriesId: string; title: string; items: Placed[] };

const byDate = (a: Placed, b: Placed) => a.event.starts_on.localeCompare(b.event.starts_on) || (a.event.starts_at ?? "").localeCompare((b.event.starts_at ?? "")) || a.laneIndex - b.laneIndex || a.event.id.localeCompare(b.event.id);
const first = (row: ListRow): Placed => (row.kind === "event" ? row.item : row.items[0]);
const titleOf = (row: ListRow) => (row.kind === "event" ? row.item.event.title : row.title);

/** Group dense Series and sort the rows; Occurrences inside a Series always stay in date order. */
export function buildRows(placed: Placed[], sort: Sort = DEFAULT_SORT): ListRow[] {
  const groups = new Map<string, Placed[]>();
  for (const item of placed) {
    if (item.dense && item.event.series_id) groups.set(item.event.series_id, [...(groups.get(item.event.series_id) ?? []), item]);
  }
  const rows: ListRow[] = [];
  const added = new Set<string>();
  for (const item of placed) {
    const seriesId = item.event.series_id;
    if (item.dense && seriesId) {
      if (added.has(seriesId)) continue;
      added.add(seriesId);
      const items = [...(groups.get(seriesId) ?? [])].sort(byDate);
      rows.push({ kind: "series", seriesId, title: item.event.title, items });
    } else {
      rows.push({ kind: "event", item });
    }
  }
  const compare = (a: ListRow, b: ListRow): number => {
    const left = first(a);
    const right = first(b);
    if (sort.key === "title") return titleOf(a).localeCompare(titleOf(b), undefined, { sensitivity: "base" }) || byDate(left, right);
    if (sort.key === "lane") return left.laneIndex - right.laneIndex || byDate(left, right);
    return byDate(left, right);
  };
  rows.sort((a, b) => (sort.direction === "asc" ? compare(a, b) : compare(b, a)));
  return rows;
}

/** Choosing the sorted column again reverses it; choosing another starts ascending. */
export function nextSort(current: Sort, key: SortKey): Sort {
  return current.key === key ? { key, direction: current.direction === "asc" ? "desc" : "asc" } : { key, direction: "asc" };
}
