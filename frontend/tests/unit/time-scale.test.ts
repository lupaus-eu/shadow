import assert from "node:assert/strict";
import { test } from "node:test";

import { isoWeek, planningWindow, quarterScale, weekScale } from "../../src/yearclock/geometry.ts";

test("ISO weeks follow Monday starts and the first Thursday", () => {
  assert.deepEqual(isoWeek("2025-12-29"), { year: 2026, week: 1 });
  assert.deepEqual(isoWeek("2026-01-01"), { year: 2026, week: 1 });
  assert.deepEqual(isoWeek("2027-01-01"), { year: 2026, week: 53 });
  assert.deepEqual(isoWeek("2027-01-04"), { year: 2027, week: 1 });
  assert.deepEqual(isoWeek("2026-09-25"), { year: 2026, week: 39 });
  assert.deepEqual(isoWeek("2021-01-03"), { year: 2020, week: 53 });
});

test("week segments cover the window and thin their labels for long windows", () => {
  const year = weekScale(planningWindow("2026-01-01", 12));
  assert.equal(year[0].from, 0);
  assert.equal(year.at(-1)!.to, 1);
  assert.equal(year[0].label, "1");
  assert.ok(year.every((segment, index) => index === 0 || Math.abs(segment.from - year[index - 1].to) < 1e-12));
  assert.ok(year.filter((segment) => segment.labelled).every((segment) => Number(segment.label) % 2 === 0));
  assert.ok(weekScale(planningWindow("2026-09-01", 3)).every((segment) => segment.labelled));
  assert.ok(weekScale(planningWindow("2026-01-01", 24)).filter((segment) => segment.labelled).every((segment) => Number(segment.label) % 4 === 0));
});

test("quarters follow the start month and clip to the window", () => {
  assert.deepEqual(quarterScale(planningWindow("2026-01-01", 12)).map((segment) => segment.label), ["Q1", "Q2", "Q3", "Q4"]);
  const school = quarterScale(planningWindow("2026-08-01", 12), 8);
  assert.deepEqual(school.map((segment) => segment.label), ["Q1", "Q2", "Q3", "Q4"]);
  const july = quarterScale(planningWindow("2026-09-01", 6), 7);
  assert.deepEqual(july.map((segment) => segment.label), ["Q1", "Q2", "Q3"]);
  assert.equal(july[0].from, 0);
  assert.ok(july[0].to < 0.2 && july[0].to > 0.15);
  assert.equal(july.at(-1)!.to, 1);
});
