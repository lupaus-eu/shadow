/** Formatting of Event history entries (Yearclock V2, P4). Pure, so it is unit-tested. */

export type HistoryValue = string | boolean | null | { id: string; name: string | null } | Array<{ id: string; name: string | null }>;
export type HistoryChange = { field: string; before?: HistoryValue; after?: HistoryValue };
export type HistoryItem = { id: string; kind: string; reason: string; reason_detail: Record<string, string | null>; actor: { kind: "member" | "support" | "system"; name: string | null }; changes: HistoryChange[]; created_at: string };
export type HistoryPage = { items: HistoryItem[]; next_offset: number | null };

export type HistoryMessages = {
  fields: Record<string, string>;
  none: string;
  removed: string;
  yes: string;
  no: string;
  changed: (field: string) => string;
  change: (field: string, before: string, after: string) => string;
  formerMember: string;
  support: string;
  system: string;
  reasons: Record<string, (detail: Record<string, string | null>) => string>;
  kinds: Record<string, string>;
};

const SUMMARY_ONLY = new Set(["description", "links"]);

export function formatValue(field: string, value: HistoryValue | undefined, copy: HistoryMessages, formatDay: (value: string) => string): string {
  if (value === null || value === undefined || (Array.isArray(value) && value.length === 0)) return copy.none;
  if (Array.isArray(value)) return value.map((item) => item.name ?? copy.removed).join(", ");
  if (typeof value === "object") return value.name ?? copy.removed;
  if (typeof value === "boolean") return value ? copy.yes : copy.no;
  if (field === "starts_on" || field === "ends_on") return formatDay(value);
  return value;
}

/** One readable line per changed field; long text only says that it changed. */
export function describeChanges(changes: HistoryChange[], copy: HistoryMessages, formatDay: (value: string) => string): string[] {
  return changes.map((change) => {
    const name = copy.fields[change.field] ?? change.field;
    if (SUMMARY_ONLY.has(change.field)) return copy.changed(name);
    return copy.change(name, formatValue(change.field, change.before, copy, formatDay), formatValue(change.field, change.after, copy, formatDay));
  });
}

export function describeActor(actor: HistoryItem["actor"], copy: HistoryMessages): string {
  if (actor.kind === "support") return copy.support;
  if (actor.kind === "system") return copy.system;
  return actor.name ?? copy.formerMember;
}

/** The entry's headline: the reason when it says more than the kind of change. */
export function describeEntry(item: HistoryItem, copy: HistoryMessages): string {
  const reason = copy.reasons[item.reason];
  return reason ? reason(item.reason_detail ?? {}) : copy.kinds[item.kind] ?? item.kind;
}

export type ChangeItem = { event_id: string | null; series_id: string | null; title: string; kind: "new" | "changed" | "deleted" | "series_changed"; at: string; actor: HistoryItem["actor"]; count: number };
export type ChangesPage = { items: ChangeItem[]; total: number; more: boolean; latest_at: string | null };

/** New and Changed marks per shown Event; a Series change marks every shown Occurrence of that Series. */
export function changeMarks(items: ChangeItem[], events: Array<{ id: string; series_id?: string | null }>): Map<string, "new" | "changed"> {
  const marks = new Map<string, "new" | "changed">();
  const series = new Set(items.filter((item) => item.kind === "series_changed" && item.series_id).map((item) => item.series_id));
  for (const event of events) if (event.series_id && series.has(event.series_id)) marks.set(event.id, "changed");
  for (const item of items) if (item.event_id && (item.kind === "new" || item.kind === "changed")) marks.set(item.event_id, item.kind);
  return marks;
}

