import { describe, expect, it } from "vitest";

import { formatMetricValue, latestPoint, metricsOfNode, periodLabel } from "../../src/models/canvas/node-metrics.ts";
import type { Metric } from "../../src/models/client.ts";

const metric = (id: string, name: string, node_id: string | null, unit: string | null = null): Metric => ({ id, key: id, name, unit, node_id, formula: null, derived: false, version: 1, values: 0 });

describe("metricsOfNode", () => {
  it("keeps the metrics attached to the node, sorted by name", () => {
    const all = [metric("m1", "Revenue", "n1"), metric("m2", "Cost", "n2"), metric("m3", "Absence", "n1"), metric("m4", "Free", null)];
    expect(metricsOfNode(all, "n1").map((item) => item.id)).toEqual(["m3", "m1"]);
    expect(metricsOfNode(all, "n3")).toEqual([]);
  });
});

describe("latestPoint", () => {
  it("takes the latest period that has a value", () => {
    expect(latestPoint([{ period: "2026-01-01", value: 1 }, { period: "2026-03-01", value: 3 }, { period: "2026-02-01", value: 2 }])).toEqual({ period: "2026-03-01", value: 3 });
  });
  it("skips empty and non-finite months, even the latest", () => {
    expect(latestPoint([{ period: "2026-01-01", value: 1 }, { period: "2026-02-01", value: null }, { period: "2026-03-01", value: Number.NaN }])).toEqual({ period: "2026-01-01", value: 1 });
  });
  it("keeps a value of zero", () => {
    expect(latestPoint([{ period: "2026-01-01", value: 5 }, { period: "2026-02-01", value: 0 }])).toEqual({ period: "2026-02-01", value: 0 });
  });
  it("is null without any value", () => {
    expect(latestPoint([])).toBeNull();
    expect(latestPoint([{ period: "2026-01-01", value: null }])).toBeNull();
  });
});

describe("formatMetricValue", () => {
  it("formats in the language of the person with the unit after a space", () => {
    expect(formatMetricValue(1234.5, "EUR", "en")).toBe("1,234.5 EUR");
    expect(formatMetricValue(1234.5, "EUR", "fi").replace(/\s/g, " ")).toBe("1 234,5 EUR");
  });
  it("rounds to two decimals and leaves out an empty unit", () => {
    expect(formatMetricValue(1 / 3, null, "en")).toBe("0.33");
    expect(formatMetricValue(7, "  ", "en")).toBe("7");
    expect(formatMetricValue(0, "%", "en")).toBe("0 %");
  });
});

describe("periodLabel", () => {
  it("shows the month", () => expect(periodLabel("2026-03-01")).toBe("2026-03"));
});
