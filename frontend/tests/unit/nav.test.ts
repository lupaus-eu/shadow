import assert from "node:assert/strict";
import { test } from "node:test";

import { adminHref, adminSections, isAdminSection, sidebarYearclocks, yearclockHref } from "../../src/shell/nav.ts";

test("administration follows the role", () => {
  assert.deepEqual(adminSections("member"), []);
  assert.deepEqual(adminSections("admin"), ["people", "groups", "yearclocks", "classification", "activity", "support", "agents"]);
  assert.deepEqual(adminSections("owner"), ["people", "groups", "yearclocks", "classification", "activity", "support", "agents", "billing", "settings"]);
  assert.equal(isAdminSection("billing", "admin"), false);
  assert.equal(isAdminSection("billing", "owner"), true);
  assert.equal(isAdminSection("people", "member"), false);
  assert.equal(isAdminSection("unknown", "owner"), false);
});

test("addresses nest under the Organization", () => {
  assert.equal(yearclockHref("o", "y"), "/organizations/o/yearclocks/y");
  assert.equal(adminHref("o", "people"), "/organizations/o/admin/people");
});

test("the sidebar lists recent Yearclocks first without repeating them", () => {
  const clocks = [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }, { id: "e" }];
  const { recent, others } = sidebarYearclocks(clocks, ["c", "gone", "a", "e", "b"]);
  assert.deepEqual(recent.map((item) => item.id), ["c", "a", "e"]);
  assert.deepEqual(others.map((item) => item.id), ["b", "d"]);
  assert.deepEqual(sidebarYearclocks(clocks).recent, []);
});
