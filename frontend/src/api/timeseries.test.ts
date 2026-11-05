import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchTimeserieSummaries, fetchTimeseries } from "./timeseries";

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

const revenue = {
  id: "revenue",
  name: "Revenue",
  shortName: "revenue",
  description: "Monthly revenue",
  unit: "EUR",
  timeUnit: "month",
  valueUnit: "number",
  isDerived: false,
  derivedFormula: null,
  shortNameEditable: false
};

const margin = {
  id: "derived_1",
  name: "Margin",
  shortName: "",
  description: "",
  unit: "EUR",
  timeUnit: "month",
  valueUnit: "number",
  isDerived: true,
  derivedFormula: "revenue - cost",
  shortNameEditable: true
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("timeseries API", () => {
  it("lists timeserie summaries without values, with the supplied abort signal", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([
        { ...revenue, values: [] },
        { ...margin, values: [] }
      ])
    );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    const summaries = await fetchTimeserieSummaries(
      "acme / north",
      "future plan",
      controller.signal
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/organisations/acme%20%2F%20north/scenarios/future%20plan/timeseries" +
        "?includeValues=false",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
    expect(summaries).toEqual([revenue, margin]);
    for (const summary of summaries) {
      expect(summary).not.toHaveProperty("values");
    }
  });

  it("normalizes summary fields like the full list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          timeseries: [
            {
              timeserie_key: "headcount",
              short_name: "hc",
              time_unit: "quarter",
              value_unit: "integer",
              is_derived: true,
              derived_formula: "a + b",
              short_name_editable: false
            }
          ]
        })
      )
    );

    await expect(fetchTimeserieSummaries("acme", "reality")).resolves.toEqual([
      {
        id: "headcount",
        name: "headcount",
        shortName: "hc",
        description: "",
        unit: "",
        timeUnit: "month",
        valueUnit: "number",
        isDerived: true,
        derivedFormula: "a + b",
        shortNameEditable: false
      }
    ]);
  });

  it("keeps the full list with values on the unchanged request", async () => {
    const values = [{ date: "2030-01-01", value: 1000 }];
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ ...revenue, values }]));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await expect(fetchTimeseries("acme", "reality", controller.signal)).resolves.toEqual([
      { ...revenue, values }
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/organisations/acme/scenarios/reality/timeseries",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
  });
});
