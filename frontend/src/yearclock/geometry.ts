// Pure geometry for the circular Yearclock (ADR-0017). Dates are ISO
// all-day strings (YYYY-MM-DD) and never pass through local time zones.

export type PlanningWindow = {
  start: string;
  end: string;
  days: number;
  months: number;
};

/** Planning Window lengths in months (Yearclock V2). */
export const WINDOW_LENGTHS = [1, 3, 6, 12, 18, 24] as const;
export type WindowLength = (typeof WINDOW_LENGTHS)[number];

export type Point = { x: number; y: number };

const DAY_MS = 86_400_000;

function dayNumber(isoDate: string): number {
  const [year, month, day] = isoDate.split("-").map(Number);
  return Date.UTC(year, month - 1, day) / DAY_MS;
}

function isoFromDayNumber(value: number): string {
  return new Date(value * DAY_MS).toISOString().slice(0, 10);
}

export function addMonths(isoDate: string, months: number): string {
  const [year, month] = isoDate.split("-").map(Number);
  const total = year * 12 + (month - 1) + months;
  const nextYear = Math.floor(total / 12);
  const nextMonth = (total % 12) + 1;
  return `${String(nextYear).padStart(4, "0")}-${String(nextMonth).padStart(2, "0")}-01`;
}

/** A window of whole months (12 by default) beginning on the first day of `start`'s month. */
export function planningWindow(start: string, months: WindowLength = 12): PlanningWindow {
  const first = `${start.slice(0, 7)}-01`;
  const next = addMonths(first, months);
  return {
    start: first,
    end: isoFromDayNumber(dayNumber(next) - 1),
    days: dayNumber(next) - dayNumber(first),
    months,
  };
}

/** The window of `length` months containing `today`: from the current month when shorter than a year, otherwise from the season's start month. */
export function currentPeriod(today: string, length: WindowLength, startMonth = 1): string {
  const [year, month] = today.split("-").map(Number);
  if (length < 12) return `${today.slice(0, 7)}-01`;
  const seasonYear = month >= startMonth ? year : year - 1;
  return `${String(seasonYear).padStart(4, "0")}-${String(startMonth).padStart(2, "0")}-01`;
}

/** Day marks for a one-month window; every fifth day (and the first) carries its number. */
export function dayTicks(window: PlanningWindow): Array<{ day: number; at: number; labelled: boolean }> {
  if (window.months !== 1) return [];
  return Array.from({ length: window.days }, (_, index) => ({ day: index + 1, at: index / window.days, labelled: index === 0 || (index + 1) % 5 === 0 }));
}

/** Day offset of `date` from the window start; may fall outside [0, days). */
export function dayIndex(date: string, window: PlanningWindow): number {
  return dayNumber(date) - dayNumber(window.start);
}

export function contains(date: string, window: PlanningWindow): boolean {
  const index = dayIndex(date, window);
  return index >= 0 && index < window.days;
}

/** Fractions of the circle covered by an inclusive all-day range, clipped to the window. */
export function rangeFractions(
  startsOn: string,
  endsOn: string | null,
  window: PlanningWindow,
): { from: number; to: number; clippedStart: boolean; clippedEnd: boolean } | null {
  const first = dayIndex(startsOn, window);
  const last = dayIndex(endsOn ?? startsOn, window);
  if (last < 0 || first >= window.days) return null;
  const from = Math.max(first, 0);
  const to = Math.min(last + 1, window.days);
  return {
    from: from / window.days,
    to: to / window.days,
    clippedStart: first < 0,
    clippedEnd: last + 1 > window.days,
  };
}

/** Month boundaries and label positions for the outer scale. */
export function monthScale(window: PlanningWindow): Array<{ month: string; from: number; to: number }> {
  return Array.from({ length: window.months }, (_, offset) => {
    const month = addMonths(window.start, offset);
    const next = addMonths(window.start, offset + 1);
    return {
      month,
      from: dayIndex(month, window) / window.days,
      to: dayIndex(next, window) / window.days,
    };
  });
}

/** Elapsed share of the window through the end of `today`, or null outside the window. */
export function todayFraction(today: string, window: PlanningWindow): { at: number; elapsed: number } | null {
  if (!contains(today, window)) return null;
  const index = dayIndex(today, window);
  return { at: (index + 0.5) / window.days, elapsed: (index + 1) / window.days };
}

/** Concentric bands, first Lane outermost, between `inner` and `outer` radii; `weights` widen some bands (a tall Lane weighs 2). */
export function laneBands(count: number, inner: number, outer: number, weights: number[] = []): Array<{ inner: number; outer: number; middle: number }> {
  if (count <= 0) return [];
  const shares = Array.from({ length: count }, (_, index) => Math.max(weights[index] ?? 1, 0.1));
  const unit = (outer - inner) / shares.reduce((sum, share) => sum + share, 0);
  let bandOuter = outer;
  return shares.map((share) => {
    const bandInner = bandOuter - share * unit;
    const band = { inner: bandInner, outer: bandOuter, middle: (bandInner + bandOuter) / 2 };
    bandOuter = bandInner;
    return band;
  });
}

/** A fraction of the circle measured clockwise from 12 o'clock. */
export function polar(center: Point, radius: number, fraction: number): Point {
  const angle = fraction * Math.PI * 2 - Math.PI / 2;
  return { x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius };
}

export function arcPath(center: Point, radius: number, from: number, to: number): string {
  const span = Math.min(Math.max(to - from, 0), 0.9999);
  const start = polar(center, radius, from);
  const end = polar(center, radius, from + span);
  const large = span > 0.5 ? 1 : 0;
  return `M ${start.x.toFixed(3)} ${start.y.toFixed(3)} A ${radius} ${radius} 0 ${large} 1 ${end.x.toFixed(3)} ${end.y.toFixed(3)}`;
}

/** A closed ring sector between two radii, used for the elapsed-time wash. */
export function sectorPath(center: Point, inner: number, outer: number, from: number, to: number): string {
  const span = Math.min(Math.max(to - from, 0), 0.9999);
  const large = span > 0.5 ? 1 : 0;
  const a = polar(center, outer, from);
  const b = polar(center, outer, from + span);
  const c = polar(center, inner, from + span);
  const d = polar(center, inner, from);
  const f = (point: Point) => `${point.x.toFixed(3)} ${point.y.toFixed(3)}`;
  return `M ${f(a)} A ${outer} ${outer} 0 ${large} 1 ${f(b)} L ${f(c)} A ${inner} ${inner} 0 ${large} 0 ${f(d)} Z`;
}

/** The all-day date whose slice of the circle contains `point`. */
export function dateAt(point: Point, center: Point, window: PlanningWindow): string {
  const angle = Math.atan2(point.y - center.y, point.x - center.x) + Math.PI / 2;
  const fraction = ((angle / (Math.PI * 2)) % 1 + 1) % 1;
  const index = Math.min(Math.floor(fraction * window.days), window.days - 1);
  return isoFromDayNumber(dayNumber(window.start) + index);
}

/** A Series with at least this many visible Occurrences is drawn compactly. */
export const DENSE_SERIES_THRESHOLD = 13;

/** ISO 8601 week of an all-day date: weeks start on Monday and week 1 holds the year's first Thursday. */
export function isoWeek(isoDate: string): { year: number; week: number } {
  const day = dayNumber(isoDate);
  const weekday = (((day + 3) % 7) + 7) % 7; // 0 = Monday (1970-01-01 was a Thursday)
  const thursday = day - weekday + 3;
  const year = new Date(thursday * DAY_MS).getUTCFullYear();
  const firstThursday = dayNumber(`${year}-01-04`) - ((((dayNumber(`${year}-01-04`) + 3) % 7) + 7) % 7) + 3;
  return { year, week: Math.floor((thursday - firstThursday) / 7) + 1 };
}

export type Segment = { label: string; from: number; to: number; labelled: boolean };

/** ISO week segments clipped to the window; longer windows label fewer weeks so numbers stay legible. */
export function weekScale(window: PlanningWindow): Segment[] {
  const step = window.months <= 6 ? 1 : window.months <= 12 ? 2 : 4;
  const start = dayNumber(window.start);
  const end = start + window.days;
  const firstMonday = start - ((((start + 3) % 7) + 7) % 7);
  const segments: Segment[] = [];
  for (let monday = firstMonday; monday < end; monday += 7) {
    const { week } = isoWeek(isoFromDayNumber(monday));
    const from = Math.max(monday, start);
    const to = Math.min(monday + 7, end);
    segments.push({ label: String(week), from: (from - start) / window.days, to: (to - start) / window.days, labelled: week % step === 0 || step === 1 });
  }
  return segments;
}

/** Quarter segments that follow the Yearclock start month (Q1 begins in `startMonth`), clipped to the window. */
export function quarterScale(window: PlanningWindow, startMonth = 1): Segment[] {
  const segments: Segment[] = [];
  const [year, month] = window.start.split("-").map(Number);
  const offset = (((month - startMonth) % 3) + 3) % 3;
  let quarterStart = addMonths(`${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-01`, -offset);
  while (dayIndex(quarterStart, window) < window.days) {
    const next = addMonths(quarterStart, 3);
    const from = Math.max(dayIndex(quarterStart, window), 0);
    const to = Math.min(dayIndex(next, window), window.days);
    const quarterMonth = Number(quarterStart.slice(5, 7));
    const index = Math.floor(((((quarterMonth - startMonth) % 12) + 12) % 12) / 3) + 1;
    segments.push({ label: `Q${index}`, from: from / window.days, to: to / window.days, labelled: true });
    quarterStart = next;
  }
  return segments;
}
