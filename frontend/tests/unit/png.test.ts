import assert from "node:assert/strict";
import { test } from "node:test";

import { canvasSize, imageFileName, layoutLegend } from "../../src/exchange/png.ts";

const measure = (text: string) => text.length * 10;

test("legend entries flow into rows within the width", () => {
  const { entries, rows } = layoutLegend([{ label: "Governance" }, { label: "Finance" }, { label: "Audit", color: "#a05000" }], 200, measure);
  assert.equal(rows, 2);
  assert.deepEqual(entries.map((entry) => [entry.row, entry.x]), [[0, 0], [0, 118], [1, 0]]);
});

test("an empty legend has no rows, and a swatch adds its width", () => {
  assert.equal(layoutLegend([], 200, measure).rows, 0);
  assert.equal(layoutLegend([{ label: "Board", color: "#000" }], 200, measure).entries[0].width, 14 + 6 + 50);
});

test("the image is twice the screen size with room for the title and legend", () => {
  const size = canvasSize(400, 2);
  assert.equal(size.width, (400 + 48) * 2);
  assert.equal(size.legendTop, 24 + 56 + 400 + 12);
  assert.equal(size.height, (size.legendTop + 2 * 22 + 24) * 2);
});

test("the file name is a safe slug with the window start", () => {
  assert.equal(imageFileName("Northwind Yearclock", "2026-01-01"), "northwind-yearclock-2026-01-01.png");
  assert.equal(imageFileName("Hallituksen käsittely 2027!", "2027-08-01"), "hallituksen-kasittely-2027-2027-08-01.png");
  assert.equal(imageFileName("???", "2026-01-01"), "yearclock-2026-01-01.png");
});
