import assert from "node:assert/strict";
import { test } from "node:test";

import { groupAgenda } from "../../src/yearclock/displays/agenda.ts";

const item = (id: string, startsOn: string, laneIndex: number, clippedStart = false) => ({ event: { id, starts_on: startsOn }, laneIndex, from: 0, to: 0, clippedStart, clippedEnd: false, dense: false }) as never;

test("Events group by month and day in date order, Lane order within a day", () => {
  const months = groupAgenda([item("b", "2026-03-10", 1), item("a", "2026-03-10", 0), item("c", "2026-04-01", 0), item("d", "2026-03-02", 0)], "2026-01-01");
  assert.deepEqual(months.map((month) => month.month), ["2026-03", "2026-04"]);
  assert.deepEqual(months[0].days.map((day) => day.date), ["2026-03-02", "2026-03-10"]);
  assert.deepEqual(months[0].days[1].items.map((entry) => entry.event.id), ["a", "b"]);
});

test("an Event that began before the window is listed on the window's first day", () => {
  const months = groupAgenda([item("x", "2025-12-20", 0, true), item("y", "2026-01-05", 0)], "2026-01-01");
  assert.deepEqual(months.map((month) => [month.month, month.days.map((day) => day.date)]), [["2026-01", ["2026-01-01", "2026-01-05"]]]);
});

test("months and years boundaries stay separate, and nothing placed gives no months", () => {
  const months = groupAgenda([item("a", "2026-12-31", 0), item("b", "2027-01-01", 0)], "2026-07-01");
  assert.deepEqual(months.map((month) => month.month), ["2026-12", "2027-01"]);
  assert.deepEqual(groupAgenda([], "2026-01-01"), []);
});
