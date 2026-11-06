import assert from "node:assert/strict";
import { test } from "node:test";

import { describeSource } from "../../src/access-sources.ts";
import { workspaceMessages } from "../../src/i18n.ts";

test("access sources read as role, direct, Group, and everyone", () => {
  const copy = workspaceMessages("en").accessOverview.sources;
  assert.equal(describeSource({ kind: "role", role: "editor", organization_role: "admin" }, copy), "Administrator (sees every Yearclock)");
  assert.equal(describeSource({ kind: "direct", role: "viewer" }, copy), "Direct: Viewer");
  assert.equal(describeSource({ kind: "group", role: "editor", group_name: "Board" }, copy), "Group Board: Editor");
  assert.equal(describeSource({ kind: "organization", role: "viewer" }, copy), "Everyone in the Organization: Viewer");
  assert.equal(describeSource({ kind: "group", role: "viewer", group_name: "Hallitus" }, workspaceMessages("fi").accessOverview.sources), "Ryhmä Hallitus: Lukija");
});
