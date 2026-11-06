import assert from "node:assert/strict";
import { test } from "node:test";

import { adminHref, adminSections, isAdminSection } from "../../src/shell/nav.ts";

test("administration follows the role", () => {
  assert.deepEqual(adminSections("member"), []);
  assert.deepEqual(adminSections("admin"), ["people", "activity", "support", "agents"]);
  assert.deepEqual(adminSections("owner"), ["people", "activity", "support", "agents", "billing", "settings"]);
  assert.equal(isAdminSection("billing", "admin"), false);
  assert.equal(isAdminSection("billing", "owner"), true);
  assert.equal(isAdminSection("people", "member"), false);
  assert.equal(isAdminSection("unknown", "owner"), false);
});

test("addresses nest under the Organization", () => {
  assert.equal(adminHref("o", "people"), "/organizations/o/admin/people");
});
