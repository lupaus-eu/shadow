import assert from "node:assert/strict";
import { test } from "node:test";

import { groupAgenda } from "../../src/yearclock/displays/agenda.ts";
import { dateLabel, timeKey, timeLabel } from "../../src/yearclock/displays/format.ts";
import { buildRows } from "../../src/yearclock/displays/list.ts";

const make = (id: string, startsOn: string, startsAt: string | null = null, endsAt: string | null = null, endsOn: string | null = null) => ({ id, lane_id: "l1", category_id: null, title: id, description: null, starts_on: startsOn, ends_on: endsOn, starts_at: startsAt, ends_at: endsAt, version: 1 });

test("times read as 24-hour text and all-day Events have none", () => {
  assert.equal(timeLabel({ starts_at: "14:00", ends_at: "16:30" }), "14:00–16:30");
  assert.equal(timeLabel({ starts_at: "09:15", ends_at: null }), "09:15");
  assert.equal(timeLabel({ starts_at: null, ends_at: null }), "");
  assert.equal(timeLabel({}), "");
});

test("the date label adds the times: on one day after a comma, on a range at each end", () => {
  assert.equal(dateLabel({ starts_on: "2026-03-10", ends_on: null, starts_at: "14:00", ends_at: "16:00" }, "en"), "10 Mar 2026, 14:00–16:00");
  assert.equal(dateLabel({ starts_on: "2026-03-10", ends_on: null }, "en"), "10 Mar 2026");
  assert.equal(dateLabel({ starts_on: "2026-03-10", ends_on: "2026-03-12", starts_at: "14:00", ends_at: "10:00" }, "en"), "10 Mar 2026 14:00 – 12 Mar 2026 10:00");
  assert.equal(dateLabel({ starts_on: "2026-03-10", ends_on: "2026-03-12", starts_at: null, ends_at: null }, "en"), "10 Mar 2026 – 12 Mar 2026");
});

test("all-day sorts before timed, and times sort as text", () => {
  assert.deepEqual(["14:00", "", "08:30"].map((value) => timeKey({ starts_at: value || null })).sort(), ["", "08:30", "14:00"]);
});

test("the list and the agenda put all-day first and then order by start time", () => {
  const placed = [make("late", "2026-10-05", "16:00"), make("open", "2026-10-05"), make("early", "2026-10-05", "08:30"), make("next", "2026-10-06")].map((event) => ({ event, laneIndex: 0, start: 0, end: 0, dense: false, clippedStart: false, clippedEnd: false })) as never[];
  assert.deepEqual(buildRows(placed).map((row) => (row.kind === "event" ? row.item.event.id : "")), ["open", "early", "late", "next"]);
  const day = groupAgenda(placed, "2026-01-01").flatMap((month) => month.days).find((entry) => entry.date === "2026-10-05");
  assert.deepEqual(day?.items.map((item) => item.event.id), ["open", "early", "late"]);
});
