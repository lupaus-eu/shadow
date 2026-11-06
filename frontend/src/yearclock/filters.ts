/**
 * Personal Yearclock filters (Yearclock V2, P2 ticket 06).
 *
 * Each dimension lists the values to show; an empty list shows everything.
 * Values within a dimension combine with OR, dimensions with AND, and a Label
 * filter matches an Event that has any selected Label. `NO_CATEGORY` selects
 * uncategorized Events.
 */

export const NO_CATEGORY = "none";

export type FilterState = { lanes: string[]; categories: string[]; labels: string[] };
export type Dimension = keyof FilterState;
export type FilterableEvent = { lane_id: string; category_id: string | null; label_ids?: string[] };

export const EMPTY_FILTERS: FilterState = { lanes: [], categories: [], labels: [] };

function matchesDimension(event: FilterableEvent, dimension: Dimension, selected: string[]): boolean {
  if (selected.length === 0) return true;
  if (dimension === "lanes") return selected.includes(event.lane_id);
  if (dimension === "categories") return selected.includes(event.category_id ?? NO_CATEGORY);
  return (event.label_ids ?? []).some((labelId) => selected.includes(labelId));
}

export function matchesFilters(event: FilterableEvent, filters: FilterState, except?: Dimension): boolean {
  return (Object.keys(filters) as Dimension[]).every((dimension) => dimension === except || matchesDimension(event, dimension, filters[dimension]));
}

export function applyFilters<T extends FilterableEvent>(events: T[], filters: FilterState): T[] {
  return events.filter((event) => matchesFilters(event, filters));
}

export function isFiltering(filters: FilterState): boolean {
  return filters.lanes.length + filters.categories.length + filters.labels.length > 0;
}

/** How many Events each value of a dimension would show, given the other dimensions' filters. */
export function facetCounts(events: FilterableEvent[], filters: FilterState, dimension: Dimension): Map<string, number> {
  const counts = new Map<string, number>();
  for (const event of events) {
    if (!matchesFilters(event, filters, dimension)) continue;
    const values = dimension === "lanes" ? [event.lane_id] : dimension === "categories" ? [event.category_id ?? NO_CATEGORY] : event.label_ids ?? [];
    for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return counts;
}

export function toggle(filters: FilterState, dimension: Dimension, value: string, on: boolean): FilterState {
  const current = filters[dimension].filter((item) => item !== value);
  return { ...filters, [dimension]: on ? [...current, value] : current };
}

/** Keep only values that still exist, so a deleted Lane or Label never hides everything. */
export function pruneFilters(filters: FilterState, known: { lanes: string[]; categories: string[]; labels: string[] }): FilterState {
  return {
    lanes: filters.lanes.filter((value) => known.lanes.includes(value)),
    categories: filters.categories.filter((value) => value === NO_CATEGORY || known.categories.includes(value)),
    labels: filters.labels.filter((value) => known.labels.includes(value)),
  };
}

const storageKey = (yearclockId: string) => `yearclock.filters.${yearclockId}`;

export function loadFilters(yearclockId: string, storage: Pick<Storage, "getItem"> | undefined = globalThis.localStorage): FilterState {
  try {
    const parsed = JSON.parse(storage?.getItem(storageKey(yearclockId)) ?? "null") as Partial<FilterState> | null;
    if (!parsed) return EMPTY_FILTERS;
    const list = (value: unknown) => (Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []);
    return { lanes: list(parsed.lanes), categories: list(parsed.categories), labels: list(parsed.labels) };
  } catch {
    return EMPTY_FILTERS;
  }
}

export function saveFilters(yearclockId: string, filters: FilterState, storage: Pick<Storage, "setItem" | "removeItem"> | undefined = globalThis.localStorage): void {
  try {
    if (isFiltering(filters)) storage?.setItem(storageKey(yearclockId), JSON.stringify(filters));
    else storage?.removeItem(storageKey(yearclockId));
  } catch {
    // Private windows or blocked storage: filters simply stop being remembered.
  }
}

/** Categories for the Filters: the Yearclock's own first, then one group per source Yearclock of its Linked Lanes. */
export function categoryGroups<T extends { scope?: string; source_yearclock_id?: string | null; source_yearclock_name?: string | null }>(categories: T[]): Array<{ source: string | null; items: T[] }> {
  const groups: Array<{ key: string; source: string | null; items: T[] }> = [{ key: "", source: null, items: [] }];
  for (const category of categories) {
    const key = category.scope === "linked" ? category.source_yearclock_id ?? "linked" : "";
    let group = groups.find((item) => item.key === key);
    if (!group) groups.push((group = { key, source: category.source_yearclock_name ?? "", items: [] }));
    group.items.push(category);
  }
  return groups.map(({ source, items }) => ({ source, items }));
}

