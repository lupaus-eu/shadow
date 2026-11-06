import assert from "node:assert/strict";
import { test } from "node:test";

import { describeActor, describeChanges, describeEntry } from "../../src/yearclock/history.ts";
import { workspaceMessages } from "../../src/i18n.ts";

const copy = workspaceMessages("en").planner.history;
const day = (value: string) => `day:${value}`;

test("history lines show old and new values, names, removed items, and summaries", () => {
  assert.deepEqual(
    describeChanges([
      { field: "title", before: "Board", after: "Board meeting" },
      { field: "starts_on", before: "2026-03-10", after: "2026-03-17" },
      { field: "category_id", before: null, after: { id: "c", name: null } },
      { field: "label_ids", before: [], after: [{ id: "a", name: "Budget" }, { id: "b", name: "Final" }] },
      { field: "description" },
      { field: "skipped", before: false, after: true },
    ], copy, day),
    ["Title: Board → Board meeting", "Start: day:2026-03-10 → day:2026-03-17", "Category: none → (removed)", "Labels: none → Budget, Final", "Description changed", "Skipped: no → yes"],
  );
});

test("actors and reasons read naturally", () => {
  assert.equal(describeActor({ kind: "member", name: null }, copy), "Former member");
  assert.equal(describeActor({ kind: "support", name: null }, copy), "Support");
  assert.equal(describeActor({ kind: "member", name: "Olivia" }, copy), "Olivia");
  const item = { id: "1", kind: "updated", reason: "label_merged", reason_detail: { from: "Draft", into: "Final" }, actor: { kind: "member" as const, name: "Olivia" }, changes: [], created_at: "2026-09-25T10:00:00Z" };
  assert.equal(describeEntry(item, copy), "Label Draft merged into Final");
  assert.equal(describeEntry({ ...item, reason: "edit" }, copy), "Changed");
  assert.equal(describeEntry({ ...item, reason: "lane_copy", reason_detail: { yearclock_name: "HR year" } }, copy), "Copied with a Lane from HR year");
});

test("change marks cover changed Events and every shown occurrence of a changed Series", async () => {
  const { changeMarks } = await import("../../src/yearclock/history.ts");
  const actor = { kind: "member" as const, name: "Eddie" };
  const items = [
    { event_id: "a", series_id: null, title: "A", kind: "new" as const, at: "", actor, count: 1 },
    { event_id: "b", series_id: null, title: "B", kind: "changed" as const, at: "", actor, count: 1 },
    { event_id: "c", series_id: null, title: "C", kind: "deleted" as const, at: "", actor, count: 1 },
    { event_id: null, series_id: "s", title: "S", kind: "series_changed" as const, at: "", actor, count: 2 },
  ];
  const marks = changeMarks(items, [{ id: "a" }, { id: "o1", series_id: "s" }, { id: "o2", series_id: "s" }, { id: "x", series_id: "other" }]);
  assert.deepEqual([...marks.entries()].sort(), [["a", "new"], ["b", "changed"], ["o1", "changed"], ["o2", "changed"]]);
});
