import assert from "node:assert/strict";
import { test } from "node:test";

import { buildRows, nextSort, DEFAULT_SORT } from "../../src/yearclock/displays/list.ts";

const item = (id: string, title: string, startsOn: string, laneIndex: number, extra: Record<string, unknown> = {}) => ({
  event: { id, title, starts_on: startsOn, ends_on: null, lane_id: `L${laneIndex}`, ...extra },
  laneIndex, from: 0, to: 0, clippedStart: false, clippedEnd: false, dense: Boolean(extra.series_id),
}) as never;
const names = (rows: ReturnType<typeof buildRows>) => rows.map((row) => (row.kind === "event" ? row.item.event.title : `${row.title} (${row.items.length})`));

const placed = [
  item("1", "Board meeting", "2026-03-10", 1),
  item("2", "audit period", "2026-04-01", 0),
  item("3", "Year-end close", "2026-12-20", 1),
  item("4", "Weekly", "2026-01-05", 0, { series_id: "S" }),
  item("5", "Weekly", "2026-01-12", 0, { series_id: "S" }),
  item("6", "Weekly", "2026-01-19", 0, { series_id: "S" }),
];

test("rows sort by date by default, with a Series as one row at its first date", () => {
  assert.deepEqual(names(buildRows(placed)), ["Weekly (3)", "Board meeting", "audit period", "Year-end close"]);
});

test("rows sort by title ignoring case, and by Lane then date", () => {
  assert.deepEqual(names(buildRows(placed, { key: "title", direction: "asc" })), ["audit period", "Board meeting", "Weekly (3)", "Year-end close"]);
  assert.deepEqual(names(buildRows(placed, { key: "lane", direction: "asc" })), ["Weekly (3)", "audit period", "Board meeting", "Year-end close"]);
});

test("descending reverses the rows but not the Occurrences inside a Series", () => {
  const rows = buildRows(placed, { key: "date", direction: "desc" });
  assert.deepEqual(names(rows), ["Year-end close", "audit period", "Board meeting", "Weekly (3)"]);
  const series = rows.find((row) => row.kind === "series");
  assert.ok(series && series.kind === "series");
  assert.deepEqual(series.items.map((entry) => entry.event.starts_on), ["2026-01-05", "2026-01-12", "2026-01-19"]);
});

test("a Series that is not dense stays as separate rows", () => {
  const sparse = [item("a", "Monthly", "2026-02-01", 0, { series_id: "M" }), item("b", "Monthly", "2026-03-01", 0, { series_id: "M" })].map((row) => ({ ...(row as object), dense: false })) as never[];
  assert.deepEqual(names(buildRows(sparse)), ["Monthly", "Monthly"]);
});

test("choosing the sorted column again reverses it, another column starts ascending", () => {
  assert.deepEqual(nextSort(DEFAULT_SORT, "date"), { key: "date", direction: "desc" });
  assert.deepEqual(nextSort({ key: "date", direction: "desc" }, "title"), { key: "title", direction: "asc" });
});
