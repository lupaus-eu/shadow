import assert from "node:assert/strict";
import { test } from "node:test";

import { EMPTY_FILTERS, NO_CATEGORY, applyFilters, categoryGroups, facetCounts, isFiltering, loadFilters, pruneFilters, saveFilters, toggle } from "../../src/yearclock/filters.ts";

const events = [
  { id: "a", lane_id: "L1", category_id: "C1", label_ids: ["X"] },
  { id: "b", lane_id: "L1", category_id: null, label_ids: ["X", "Y"] },
  { id: "c", lane_id: "L2", category_id: "C1", label_ids: [] },
  { id: "d", lane_id: "L2", category_id: "C2", label_ids: ["Y"] },
];
const ids = (list: Array<{ id: string }>) => list.map((item) => item.id);

test("no filter shows everything", () => {
  assert.deepEqual(ids(applyFilters(events, EMPTY_FILTERS)), ["a", "b", "c", "d"]);
  assert.equal(isFiltering(EMPTY_FILTERS), false);
});

test("values combine with OR within a dimension and AND across dimensions", () => {
  const lanes = toggle(EMPTY_FILTERS, "lanes", "L1", true);
  assert.deepEqual(ids(applyFilters(events, lanes)), ["a", "b"]);
  const either = toggle(toggle(EMPTY_FILTERS, "labels", "X", true), "labels", "Y", true);
  assert.deepEqual(ids(applyFilters(events, either)), ["a", "b", "d"]);
  const both = toggle(either, "lanes", "L2", true);
  assert.deepEqual(ids(applyFilters(events, both)), ["d"]);
  assert.deepEqual(ids(applyFilters(events, toggle(EMPTY_FILTERS, "categories", NO_CATEGORY, true))), ["b"]);
});

test("facet counts follow the other dimensions but not their own", () => {
  const filters = toggle(EMPTY_FILTERS, "lanes", "L1", true);
  assert.deepEqual(Object.fromEntries(facetCounts(events, filters, "lanes")), { L1: 2, L2: 2 });
  assert.deepEqual(Object.fromEntries(facetCounts(events, filters, "labels")), { X: 2, Y: 1 });
  assert.deepEqual(Object.fromEntries(facetCounts(events, filters, "categories")), { C1: 1, [NO_CATEGORY]: 1 });
});

test("unknown values are pruned and storage failures are harmless", () => {
  const stale = { lanes: ["gone", "L1"], categories: [NO_CATEGORY, "gone"], labels: ["gone"] };
  assert.deepEqual(pruneFilters(stale, { lanes: ["L1"], categories: [], labels: [] }), { lanes: ["L1"], categories: [NO_CATEGORY], labels: [] });
  const store = new Map<string, string>();
  const storage = { getItem: (key: string) => store.get(key) ?? null, setItem: (key: string, value: string) => void store.set(key, value), removeItem: (key: string) => void store.delete(key) };
  saveFilters("y1", { ...EMPTY_FILTERS, labels: ["X"] }, storage);
  assert.deepEqual(loadFilters("y1", storage), { lanes: [], categories: [], labels: ["X"] });
  saveFilters("y1", EMPTY_FILTERS, storage);
  assert.equal(store.size, 0);
  const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }, removeItem: () => { throw new Error("blocked"); } };
  assert.deepEqual(loadFilters("y1", broken), EMPTY_FILTERS);
  assert.doesNotThrow(() => saveFilters("y1", { ...EMPTY_FILTERS, lanes: ["L1"] }, broken));
  assert.deepEqual(loadFilters("y1", { getItem: () => "{not json" }), EMPTY_FILTERS);
});

test("linked Categories form their own groups and count like own ones", () => {
  const categories = [
    { id: "own", scope: "yearclock" },
    { id: "org", scope: "organization" },
    { id: "t1", scope: "linked", source_yearclock_id: "team", source_yearclock_name: "Team year" },
    { id: "h1", scope: "linked", source_yearclock_id: "hr", source_yearclock_name: "HR year" },
    { id: "t2", scope: "linked", source_yearclock_id: "team", source_yearclock_name: "Team year" },
  ];
  assert.deepEqual(categoryGroups(categories).map((group) => [group.source, group.items.map((item) => item.id)]), [[null, ["own", "org"]], ["Team year", ["t1", "t2"]], ["HR year", ["h1"]]]);
  const events = [
    { lane_id: "linked-lane", category_id: "t1" },
    { lane_id: "linked-lane", category_id: "t1" },
    { lane_id: "own-lane", category_id: "own" },
  ];
  assert.equal(facetCounts(events, { lanes: ["linked-lane"], categories: [], labels: [] }, "categories").get("t1"), 2);
  assert.deepEqual(applyFilters(events, { lanes: [], categories: ["t1"], labels: [] }).length, 2);
});
