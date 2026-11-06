/** Date shifts for planning Events again (Yearclock V2, P3). Dates are ISO `YYYY-MM-DD`. */

/** Moves a date by whole years; 29 February becomes 28 February in a common year. */
export function shiftYear(value: string, years = 1): string {
  const [year, month, day] = value.split("-").map(Number);
  const target = year + years;
  const last = new Date(Date.UTC(target, month, 0)).getUTCDate();
  return `${String(target).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(Math.min(day, last)).padStart(2, "0")}`;
}

/** 52 weeks later: the same weekday nearest to the date a year later, at most three days away. */
export function sameWeekdayNextYear(value: string): string {
  const moved = new Date(`${value}T00:00:00Z`);
  moved.setUTCDate(moved.getUTCDate() + 364);
  return moved.toISOString().slice(0, 10);
}

/** Why an Event cannot join a Bulk Edit, or null when it can. */
export function bulkBlocker(event: { occurrence_id?: string | null; linked?: boolean }): "occurrence" | "linked" | null {
  return event.linked ? "linked" : event.occurrence_id ? "occurrence" : null;
}

/** "Select all shown": the ids of the Events the filters show that a Bulk Edit may change. */
export function selectAllShown(shown: Array<{ id: string; occurrence_id?: string | null; linked?: boolean }>): string[] {
  return shown.filter((event) => bulkBlocker(event) === null).map((event) => event.id);
}
