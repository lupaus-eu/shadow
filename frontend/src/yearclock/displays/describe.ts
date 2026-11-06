import type { YearclockViewMessages } from "../YearclockView";
import { dateLabel } from "./format";
import type { Placed } from "./placement";

export type DescribeContext = {
  locale: string;
  laneName: (index: number) => string;
  categoryName: (categoryId: string | null) => string | undefined;
  labelNames: (event: Placed["event"]) => string[];
  marks?: ReadonlyMap<string, "new" | "changed">;
  copy: YearclockViewMessages;
};

/** The accessible name of an Event in every display: title, mark, date, kind, Lane, Category, Labels, and state. */
export function describeEvent(item: Placed, context: DescribeContext): string {
  const { locale, laneName, categoryName, labelNames, marks, copy } = context;
  const mark = marks?.get(item.event.id);
  const names = labelNames(item.event);
  return [
    item.event.title,
    mark && copy.marks ? copy.marks[mark] : undefined,
    dateLabel(item.event, locale),
    item.event.ends_on && item.event.ends_on !== item.event.starts_on ? copy.rangeEvent : copy.pointEvent,
    laneName(item.laneIndex),
    categoryName(item.event.category_id),
    item.event.location ? item.event.location : undefined,
    names.length ? copy.labels(names.join(", ")) : undefined,
    item.event.series_id ? copy.recurring : undefined,
    item.event.exception ? copy.exception : undefined,
    item.clippedStart ? copy.continuesBefore : undefined,
    item.clippedEnd ? copy.continuesAfter : undefined,
  ].filter(Boolean).join(", ");
}
