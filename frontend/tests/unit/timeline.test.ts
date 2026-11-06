import assert from "node:assert/strict";
import { test } from "node:test";

import { axisRows, contentWidth, crossesYear, dateAtFraction, markerSlotPx, packTracks } from "../../src/yearclock/displays/timeline.ts";

test("the content width grows with the window and never drops below the minimum", () => {
  assert.equal(contentWidth(1), 720);
  assert.equal(contentWidth(12), 768);
  assert.equal(contentWidth(24), 1536);
});

test("overlapping ranges and crowded markers go to separate tracks, others share one", () => {
  const slots = [
    { key: "a", from: 0.0, to: 0.3, minPx: 14 },
    { key: "b", from: 0.1, to: 0.2, minPx: 14 },
    { key: "c", from: 0.35, to: 0.4, minPx: 14 },
    { key: "d", from: 0.0, to: 0.0, minPx: 120 },
  ];
  const { track, count } = packTracks(slots, 1000);
  assert.equal(count, 3);
  assert.equal(track.get("d"), 0);
  assert.equal(track.get("a"), 1);
  assert.equal(track.get("b"), 2);
  assert.equal(track.get("c"), 0);
});

test("a marker's label counts toward its slot, capped", () => {
  assert.equal(markerSlotPx("Hi", false), 14);
  assert.equal(markerSlotPx("Hi", true), 14 + 6 + 13);
  assert.equal(markerSlotPx("x".repeat(100), true), 14 + 6 + 168);
});

test("labelled markers that would overlap are stacked, but dense dots on separate days share a track", () => {
  const labelled = packTracks([{ key: "a", from: 0.1, to: 0.1, minPx: markerSlotPx("Board meeting", true) }, { key: "b", from: 0.12, to: 0.12, minPx: markerSlotPx("Audit", true) }], 800);
  assert.equal(labelled.count, 2);
  const dots = packTracks([0.1, 0.12, 0.14].map((from, index) => ({ key: String(index), from, to: from, minPx: 8 })), 800);
  assert.equal(dots.count, 1);
});

test("a click position maps to its all-day date inside the window", () => {
  assert.equal(dateAtFraction("2026-01-01", 365, 0), "2026-01-01");
  assert.equal(dateAtFraction("2026-01-01", 365, 0.5), "2026-07-02");
  assert.equal(dateAtFraction("2026-01-01", 365, 0.99999), "2026-12-31");
  assert.equal(dateAtFraction("2026-01-01", 31, 1.2), "2026-01-31");
  assert.equal(dateAtFraction("2026-01-01", 31, -0.2), "2026-01-01");
});

test("month labels carry the year only across a year end", () => {
  assert.equal(crossesYear("2026-01-01", "2026-12-31"), false);
  assert.equal(crossesYear("2026-08-01", "2027-07-31"), true);
});

test("the axis adds weeks up to 3 months, days for 1 month, and the enabled rings", () => {
  assert.deepEqual(axisRows(1, false, false), { quarters: false, weeks: true, days: true });
  assert.deepEqual(axisRows(3, false, false), { quarters: false, weeks: true, days: false });
  assert.deepEqual(axisRows(12, false, false), { quarters: false, weeks: false, days: false });
  assert.deepEqual(axisRows(12, true, true), { quarters: true, weeks: true, days: false });
});
