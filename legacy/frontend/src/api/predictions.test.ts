import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cancelPredictionRequest,
  createPrediction,
  fetchPredictionRequest,
  fetchPredictionRequests,
  MODEL_KINDS,
  preflightPredictions,
  SEASONAL_PERIOD_MODEL_KINDS,
  selectionUsesSeasonalPeriod
} from "./predictions";

const requestSummary = {
  id: "request-1",
  name: "September plan",
  state: "queued",
  submittedTime: "2026-09-09T09:00:00Z",
  startTime: null,
  finishTime: null,
  failureCode: null,
  failureReason: null,
  completedPredictionId: null
};

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("predictions API", () => {
  it("uses the accepted creation, request list/detail, and cancellation contracts", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(requestSummary, 202))
      .mockResolvedValueOnce(jsonResponse([requestSummary]))
      .mockResolvedValueOnce(jsonResponse(requestSummary))
      .mockResolvedValueOnce(jsonResponse({ ...requestSummary, state: "cancelled" }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await expect(
      createPrediction("acme & sons", {
        name: "September plan",
        targetScenarioIds: ["future"],
        startDate: "2026-09-10",
        endDate: "2026-10-10",
        cutoffMode: "asOfStart",
        confidenceLevel: 80,
        manualSeasonalPeriods: {},
        modelKinds: ["naive", "prophet"]
      })
    ).resolves.toEqual(requestSummary);
    await fetchPredictionRequests("acme & sons", controller.signal);
    await fetchPredictionRequest("acme & sons", "request / 1");
    await cancelPredictionRequest("acme & sons", "request / 1");

    expect(fetchMock.mock.calls.map(([url, init]) => [url, (init as RequestInit).method])).toEqual([
      ["/api/v1/organisations/acme%20%26%20sons/predictions", "POST"],
      ["/api/v1/organisations/acme%20%26%20sons/prediction-requests", "GET"],
      ["/api/v1/organisations/acme%20%26%20sons/prediction-requests/request%20%2F%201", "GET"],
      [
        "/api/v1/organisations/acme%20%26%20sons/prediction-requests/request%20%2F%201/cancel",
        "POST"
      ]
    ]);
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        body: expect.stringContaining('"name":"September plan"')
      })
    );
    expect(JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)).toEqual(
      expect.objectContaining({
        modelKinds: ["naive", "prophet"]
      })
    );
    expect(fetchMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({ signal: controller.signal })
    );
  });

  it("sends the model selection with preflight in the canonical display order", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ metrics: [] }));
    vi.stubGlobal("fetch", fetchMock);

    expect(MODEL_KINDS).toEqual([
      "naive",
      "seasonal_naive",
      "average",
      "mlforecast",
      "sarima",
      "prophet"
    ]);
    await preflightPredictions("acme", {
      targetScenarioIds: ["future"],
      startDate: "2026-09-10",
      endDate: "2026-10-10",
      cutoffMode: "asOfStart",
      confidenceLevel: 80,
      manualSeasonalPeriods: {},
      modelKinds: [...MODEL_KINDS]
    });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/organisations/acme/predictions/preflight");
    expect(
      JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string).modelKinds
    ).toEqual([...MODEL_KINDS]);
  });

  it("tells whether a model selection contains a seasonal-period kind", () => {
    expect(SEASONAL_PERIOD_MODEL_KINDS).toEqual(["seasonal_naive", "sarima"]);
    expect(selectionUsesSeasonalPeriod(MODEL_KINDS)).toBe(true);
    expect(selectionUsesSeasonalPeriod(["seasonal_naive"])).toBe(true);
    expect(selectionUsesSeasonalPeriod(new Set(["naive", "sarima"]))).toBe(true);
    expect(
      selectionUsesSeasonalPeriod(new Set(["naive", "average", "mlforecast", "prophet"]))
    ).toBe(false);
    expect(selectionUsesSeasonalPeriod([])).toBe(false);
  });

  it("surfaces only the server's safe validation messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          jsonResponse(
            { detail: "Prediction request exceeds the 110000 prediction point limit." },
            422
          )
        )
        .mockResolvedValueOnce(
          jsonResponse(
            {
              detail: [
                {
                  type: "value_error",
                  loc: ["body", "modelKinds"],
                  msg: "Value error, Model kinds must not contain duplicates.",
                  input: ["secret", "secret"]
                }
              ]
            },
            422
          )
        )
        .mockResolvedValueOnce(
          jsonResponse({ error: { code: "FORBIDDEN", message: "Forbidden" } }, 403)
        )
        .mockResolvedValueOnce(new Response("Bad gateway", { status: 502 }))
    );
    const payload = {
      name: "Plan",
      targetScenarioIds: ["future"],
      startDate: "2026-09-10",
      endDate: "2026-10-10",
      cutoffMode: "asOfStart" as const,
      confidenceLevel: 80,
      manualSeasonalPeriods: {},
      modelKinds: ["naive"]
    };

    await expect(createPrediction("acme", payload)).rejects.toMatchObject({
      status: 422,
      message: "Prediction request exceeds the 110000 prediction point limit."
    });
    const validation = createPrediction("acme", payload);
    await expect(validation).rejects.toThrow(
      "Value error, Model kinds must not contain duplicates."
    );
    await expect(validation).rejects.not.toThrow(/secret/);
    await expect(createPrediction("acme", payload)).rejects.toMatchObject({
      status: 403,
      message: "Forbidden"
    });
    await expect(createPrediction("acme", payload)).rejects.toThrow("Bad gateway");
  });
});
