import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cancelPredictionRequest,
  createPrediction,
  fetchPredictionRequest,
  fetchPredictionRequests
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
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(requestSummary, 202))
      .mockResolvedValueOnce(jsonResponse([requestSummary]))
      .mockResolvedValueOnce(jsonResponse(requestSummary))
      .mockResolvedValueOnce(jsonResponse({ ...requestSummary, state: "cancelled" }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await expect(createPrediction("acme & sons", {
      name: "September plan", targetScenarioIds: ["future"], startDate: "2026-09-10",
      endDate: "2026-10-10", cutoffMode: "asOfStart", confidenceLevel: 80,
      manualSeasonalPeriods: {}
    })).resolves.toEqual(requestSummary);
    await fetchPredictionRequests("acme & sons", controller.signal);
    await fetchPredictionRequest("acme & sons", "request / 1");
    await cancelPredictionRequest("acme & sons", "request / 1");

    expect(fetchMock.mock.calls.map(([url, init]) => [url, (init as RequestInit).method])).toEqual([
      ["/api/v1/organisations/acme%20%26%20sons/predictions", "POST"],
      ["/api/v1/organisations/acme%20%26%20sons/prediction-requests", "GET"],
      ["/api/v1/organisations/acme%20%26%20sons/prediction-requests/request%20%2F%201", "GET"],
      ["/api/v1/organisations/acme%20%26%20sons/prediction-requests/request%20%2F%201/cancel", "POST"]
    ]);
    expect(fetchMock.mock.calls[0][1]).toEqual(expect.objectContaining({
      body: expect.stringContaining('"name":"September plan"')
    }));
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ signal: controller.signal }));
  });
});
