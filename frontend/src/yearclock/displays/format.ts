import type { YearclockEvent } from "../../organization-client";

export function formatDay(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale === "fi" ? "fi-FI" : "en-GB", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

type Timed = Pick<YearclockEvent, "ends_on" | "starts_on"> & Partial<Pick<YearclockEvent, "starts_at" | "ends_at">>;

/** The times of an Event as 24-hour text, or an empty string for an all-day Event: `14:00` or `14:00–16:00`. */
export function timeLabel(event: Partial<Pick<YearclockEvent, "starts_at" | "ends_at">>): string {
  return event.starts_at ? `${event.starts_at}${event.ends_at ? `–${event.ends_at}` : ""}` : "";
}

/** The order of Events on one day: all-day first, then by start time (an empty string sorts first). */
export const timeKey = (event: Partial<Pick<YearclockEvent, "starts_at">>): string => event.starts_at ?? "";

export function dateLabel(event: Timed, locale: string): string {
  const multiDay = event.ends_on && event.ends_on !== event.starts_on;
  if (!multiDay) return `${formatDay(event.starts_on, locale)}${event.starts_at ? `, ${timeLabel(event)}` : ""}`;
  return `${formatDay(event.starts_on, locale)}${event.starts_at ? ` ${event.starts_at}` : ""} – ${formatDay(event.ends_on!, locale)}${event.ends_at ? ` ${event.ends_at}` : ""}`;
}
