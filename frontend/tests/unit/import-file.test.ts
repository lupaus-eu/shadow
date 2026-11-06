import assert from "node:assert/strict";
import { test } from "node:test";

import { importFormat, megabytes } from "../../src/exchange/import-file.ts";

test("only .xlsx and text files are accepted, whatever the case", () => {
  assert.equal(importFormat("Plan.XLSX"), "xlsx");
  assert.equal(importFormat("events.csv"), "csv");
  assert.equal(importFormat("export.txt"), "csv");
  assert.equal(importFormat("macros.xlsm"), null);
  assert.equal(importFormat("old.xls"), null);
  assert.equal(importFormat("no-extension"), null);
});

test("the size limit is shown in whole megabytes, at least one", () => {
  assert.equal(megabytes(2 * 1024 * 1024), 2);
  assert.equal(megabytes(100), 1);
  assert.equal(megabytes("3145728"), 3);
});
