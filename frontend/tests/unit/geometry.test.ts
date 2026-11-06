import assert from "node:assert/strict";
import { test } from "node:test";

import {
  addMonths,
  arcPath,
  contains,
  dateAt,
  dayIndex,
  laneBands,
  monthScale,
  planningWindow,
  polar,
  rangeFractions,
  todayFraction,
} from "../../src/yearclock/geometry.ts";

const center = { x: 200, y: 200 };

test("a calendar-year window has 365 or 366 days", () => {
  assert.deepEqual(planningWindow("2026-01-01"), { start: "2026-01-01", end: "2026-12-31", days: 365, months: 12 });
  assert.deepEqual(planningWindow("2028-01-15"), { start: "2028-01-01", end: "2028-12-31", days: 366, months: 12 });
});

test("an arbitrary starting month spans exactly 12 months across the year boundary", () => {
  const window = planningWindow("2027-09-01");
  assert.equal(window.end, "2028-08-31");
  assert.equal(window.days, 366);
  assert.equal(addMonths("2027-11-01", 3), "2028-02-01");
});

test("month segments follow unequal month lengths", () => {
  const scale = monthScale(planningWindow("2028-01-01"));
  assert.equal(scale.length, 12);
  assert.equal(scale[0].from, 0);
  assert.equal(scale[11].to, 1);
  assert.ok(Math.abs((scale[1].to - scale[1].from) * 366 - 29) < 1e-9, "February 2028 has 29 days");
  assert.ok(Math.abs((scale[0].to - scale[0].from) * 366 - 31) < 1e-9);
  for (let index = 1; index < 12; index += 1) assert.equal(scale[index].from, scale[index - 1].to);
});

test("inclusive ranges cover their last day and clip to the window", () => {
  const window = planningWindow("2026-01-01");
  const single = rangeFractions("2026-03-10", null, window)!;
  assert.ok(Math.abs((single.to - single.from) * 365 - 1) < 1e-9);
  const range = rangeFractions("2026-03-10", "2026-03-12", window)!;
  assert.ok(Math.abs((range.to - range.from) * 365 - 3) < 1e-9);
  const crossing = rangeFractions("2025-12-20", "2026-01-05", window)!;
  assert.equal(crossing.from, 0);
  assert.equal(crossing.clippedStart, true);
  assert.ok(Math.abs(crossing.to * 365 - 5) < 1e-9);
  const tail = rangeFractions("2026-12-30", "2027-01-02", window)!;
  assert.equal(tail.to, 1);
  assert.equal(tail.clippedEnd, true);
  assert.equal(rangeFractions("2027-01-01", null, window), null);
  assert.equal(rangeFractions("2025-01-01", "2025-12-31", window), null);
});

test("today and elapsed time exist only inside the window", () => {
  const window = planningWindow("2026-01-01");
  assert.deepEqual(todayFraction("2026-01-01", window), { at: 0.5 / 365, elapsed: 1 / 365 });
  assert.equal(todayFraction("2026-12-31", window)!.elapsed, 1);
  assert.equal(todayFraction("2027-01-01", window), null);
  assert.equal(contains("2025-12-31", window), false);
});

test("the first Lane is the outermost band and bands tile the ring", () => {
  const bands = laneBands(3, 60, 150);
  assert.deepEqual(bands.map((band) => band.outer), [150, 120, 90]);
  assert.equal(bands[2].inner, 60);
  assert.deepEqual(laneBands(0, 60, 150), []);
});

test("angles start at 12 o'clock and run clockwise", () => {
  const top = polar(center, 100, 0);
  const right = polar(center, 100, 0.25);
  assert.ok(Math.abs(top.x - 200) < 1e-9 && Math.abs(top.y - 100) < 1e-9);
  assert.ok(Math.abs(right.x - 300) < 1e-9 && Math.abs(right.y - 200) < 1e-9);
  assert.match(arcPath(center, 100, 0, 0.75), / 1 1 /, "a three-quarter arc uses the large-arc flag");
});

test("a point on the ring maps back to its all-day date", () => {
  const window = planningWindow("2026-01-01");
  const mid = (date: string) => polar(center, 120, (dayIndex(date, window) + 0.5) / window.days);
  for (const date of ["2026-01-01", "2026-02-28", "2026-07-15", "2026-12-31"]) assert.equal(dateAt(mid(date), center, window), date);
  const leap = planningWindow("2028-02-01");
  assert.equal(dateAt(polar(center, 120, (dayIndex("2028-02-29", leap) + 0.5) / leap.days), center, leap), "2028-02-29");
});
