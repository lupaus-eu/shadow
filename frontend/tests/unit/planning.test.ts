import assert from "node:assert/strict";
import { test } from "node:test";

import { shiftYear } from "../../src/yearclock/planning.ts";

test("planning again moves dates one year and clamps 29 February", () => {
  assert.equal(shiftYear("2026-03-10"), "2027-03-10");
  assert.equal(shiftYear("2026-12-31"), "2027-12-31");
  assert.equal(shiftYear("2028-02-29"), "2029-02-28");
  assert.equal(shiftYear("2027-02-28"), "2028-02-28");
  assert.equal(shiftYear("2026-01-05", 2), "2028-01-05");
});

test("select all shown follows the filters and skips recurring occurrences", async () => {
  const { selectAllShown, bulkBlocker } = await import("../../src/yearclock/planning.ts");
  const { applyFilters } = await import("../../src/yearclock/filters.ts");
  const events = [
    { id: "a", lane_id: "l1", category_id: null, label_ids: ["x"] },
    { id: "b", lane_id: "l2", category_id: null, label_ids: ["x"] },
    { id: "c", lane_id: "l1", category_id: null, label_ids: [], occurrence_id: "o1" },
    { id: "d", lane_id: "l1", category_id: null, label_ids: ["y"], occurrence_id: null },
  ];
  assert.deepEqual(selectAllShown(events), ["a", "b", "d"]);
  const shown = applyFilters(events as never, { lanes: ["l1"], categories: [], labels: [] } as never) as typeof events;
  assert.deepEqual(selectAllShown(shown), ["a", "d"]);
  assert.equal(bulkBlocker(events[2]), "occurrence");
});

test("same weekday next year stays on the weekday within three days", async () => {
  const { sameWeekdayNextYear } = await import("../../src/yearclock/planning.ts");
  for (const day of ["2026-03-10", "2026-01-01", "2028-02-29", "2027-12-31"]) {
    const moved = sameWeekdayNextYear(day);
    const [from, to, plain] = [new Date(`${day}T00:00:00Z`), new Date(`${moved}T00:00:00Z`), new Date(`${shiftYear(day)}T00:00:00Z`)];
    assert.equal(to.getUTCDay(), from.getUTCDay());
    assert.ok(Math.abs(to.valueOf() - plain.valueOf()) <= 3 * 86_400_000);
  }
  assert.equal(sameWeekdayNextYear("2026-03-10"), "2027-03-09");
});
