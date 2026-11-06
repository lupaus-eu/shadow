import assert from "node:assert/strict";
import { test } from "node:test";

import { WINDOW_LENGTHS, addMonths, currentPeriod, dayTicks, monthScale, planningWindow } from "../../src/yearclock/geometry.ts";

test("every length covers whole consecutive months across year ends", () => {
  const ends = { 1: "2026-11-30", 3: "2027-01-31", 6: "2027-04-30", 12: "2027-10-31", 18: "2028-04-30", 24: "2028-10-31" };
  for (const length of WINDOW_LENGTHS) {
    const window = planningWindow("2026-11-20", length);
    assert.equal(window.start, "2026-11-01");
    assert.equal(window.end, ends[length]);
    assert.equal(monthScale(window).length, length);
    assert.equal(monthScale(window).at(-1)!.to, 1);
  }
  assert.equal(planningWindow("2028-02-10", 1).days, 29);
});

test("periods step by their length and the current period contains today", () => {
  assert.equal(addMonths("2026-11-01", -3), "2026-08-01");
  assert.equal(currentPeriod("2026-09-25", 1), "2026-09-01");
  assert.equal(currentPeriod("2026-09-25", 6), "2026-09-01");
  assert.equal(currentPeriod("2026-09-25", 12), "2026-01-01");
  assert.equal(currentPeriod("2026-09-25", 24, 8), "2026-08-01");
  assert.equal(currentPeriod("2026-07-31", 12, 8), "2025-08-01");
});

test("day marks appear only in one-month windows, numbered every fifth day", () => {
  assert.deepEqual(dayTicks(planningWindow("2026-09-01", 3)), []);
  const ticks = dayTicks(planningWindow("2026-09-01", 1));
  assert.equal(ticks.length, 30);
  assert.deepEqual(ticks.filter((tick) => tick.labelled).map((tick) => tick.day), [1, 5, 10, 15, 20, 25, 30]);
  assert.equal(ticks[15].at, 15 / 30);
});

test("tall Lanes take twice the ring space", async () => {
  const { laneBands } = await import("../../src/yearclock/geometry.ts");
  const bands = laneBands(3, 60, 160, [1, 2, 1]);
  assert.deepEqual(bands.map((band) => [band.outer, band.inner]), [[160, 135], [135, 85], [85, 60]]);
  assert.deepEqual(laneBands(2, 60, 160).map((band) => band.outer - band.inner), [50, 50]);
});
