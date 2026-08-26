import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PredictionVersionDetailDto } from "../../api/predictions";
import PredictionsTab from "./PredictionsTab";

const api = vi.hoisted(() => ({
  fetchScenarios: vi.fn(),
  fetchEvents: vi.fn(),
  fetchPredictions: vi.fn(),
  fetchPrediction: vi.fn(),
  preflightPredictions: vi.fn(),
  createPrediction: vi.fn(),
  fetchTimeseries: vi.fn()
}));

vi.mock("../../api/scenarios", () => ({ fetchScenarios: api.fetchScenarios }));
vi.mock("../../api/events", () => ({ fetchEvents: api.fetchEvents }));
vi.mock("../../api/predictions", () => ({
  fetchPredictions: api.fetchPredictions,
  fetchPrediction: api.fetchPrediction,
  preflightPredictions: api.preflightPredictions,
  createPrediction: api.createPrediction
}));
vi.mock("../../api/timeseries", () => ({ fetchTimeseries: api.fetchTimeseries }));

const version: PredictionVersionDetailDto = {
  id: "version-1", name: "January plan", startDate: "2026-01-10", endDate: "2026-02-10",
  cutoffMode: "asOfStart", createdTime: "2026-01-01T12:00:00Z", modelConfiguration: {},
  targets: [{
    scenarioId: "future", realityScenarioId: "reality", metricId: "revenue", metricName: "Revenue",
    timeUnit: "month", unit: "EUR", status: "eligible", reason: null, seasonalPeriod: 12,
    seasonalPeriodSource: "automatic", sourceSnapshot: {}, inputSnapshot: {}, results: [{
      kind: "naive", status: "available", reason: null, crossValidationStatus: "unavailable",
      crossValidationMae: null, configuration: {}, points: [{ date: "2026-01-10", value: 30 }, { date: "2026-02-10", value: 34 }]
    }, {
      kind: "seasonal_naive", status: "ineligible", reason: "Insufficient seasonal history", crossValidationStatus: "unavailable",
      crossValidationMae: null, configuration: {}, points: []
    }]
  }, {
    scenarioId: "future", realityScenarioId: "reality", metricId: "notes", metricName: "Notes",
    timeUnit: "month", unit: null, status: "ineligible", reason: "Only numeric metrics can be forecast.", seasonalPeriod: null,
    seasonalPeriodSource: null, sourceSnapshot: {}, inputSnapshot: {}, results: [{
      kind: "naive", status: "ineligible", reason: "Only numeric metrics can be forecast.", crossValidationStatus: "unavailable",
      crossValidationMae: null, configuration: {}, points: []
    }]
  }]
};

describe("PredictionsTab", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.fetchScenarios.mockResolvedValue([
      { id: "reality", name: "Reality", description: "", protected: true },
      { id: "future", name: "Future plan", description: "", protected: false }
    ]);
    api.fetchEvents.mockImplementation((_org: string, scenarioId: string) => Promise.resolve(
      scenarioId === "reality"
        ? [{ id: "past", name: "Reality event", targetDate: "2026-01-03", eventDetails: "" }]
        : [
            { id: "start", name: "Future start", targetDate: "2026-01-05", eventDetails: "" },
            { id: "end", name: "Future end", targetDate: "2026-02-05", eventDetails: "" }
          ]
    ));
    api.fetchPredictions.mockResolvedValue([version]);
    api.fetchPrediction.mockResolvedValue(version);
    api.preflightPredictions.mockResolvedValue({ metrics: [{
      scenarioId: "future", metricId: "revenue", status: "eligible", reason: null,
      seasonalPeriod: null, seasonalPeriodSource: null, requiresManualSeasonalPeriod: true
    }] });
    api.createPrediction.mockResolvedValue({ ...version, id: "version-2", name: "Created plan" });
    api.fetchTimeseries.mockResolvedValue([{ id: "revenue", name: "Revenue", description: "", unit: "EUR", timeUnit: "month", valueUnit: "number", values: [{ date: "2026-01-10", value: 28 }] }]);
  });

  it("renders without global workspace selection, excludes Reality targets, and synchronizes event dates", async () => {
    render(<PredictionsTab orgId="acme" />);

    await waitFor(() => expect(screen.getByText(/Reality remains live manually entered/i)).toBeVisible());
    expect(screen.getByText(/Reality remains live manually entered/i)).toBeVisible();
    const targetSelector = screen.getAllByRole("group", { name: "Target scenarios" })[0];
    expect(within(targetSelector).getByLabelText("Future plan")).toBeChecked();
    expect(within(targetSelector).queryByLabelText("Reality")).not.toBeInTheDocument();
    expect(within(screen.getByLabelText("Start event")).getByRole("option", { name: /Reality · Reality event/ })).toBeVisible();

    fireEvent.change(screen.getByLabelText("Start event"), { target: { value: "future:start" } });
    expect(screen.getAllByLabelText("Start date")[0]).toHaveValue("2026-01-05");
    expect(within(screen.getByLabelText("End event")).queryByRole("option", { name: /Reality · Reality event/ })).not.toBeInTheDocument();

    const plotDateRange = screen.getByText("Plot date range").parentElement;
    expect(within(plotDateRange!).getByText("Start date")).toBeVisible();
    expect(within(plotDateRange!).getByText("End date")).toBeVisible();

    fireEvent.change(screen.getAllByLabelText("Start date")[0], { target: { value: "2026-01-06" } });
    expect(screen.getByLabelText("Start event")).toHaveValue("");
  });

  it("submits a preflight-backed create request with manual seasonality and renders provenance", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findAllByText("January plan");

    fireEvent.change(screen.getByLabelText("Version name"), { target: { value: "Created plan" } });
    fireEvent.change(screen.getAllByLabelText("Start date")[0], { target: { value: "2026-01-10" } });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));

    expect(await screen.findByText("Preflight eligibility")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Create immutable version" }));

    await waitFor(() => expect(api.createPrediction).toHaveBeenCalledWith(
      "acme",
      expect.objectContaining({
        name: "Created plan", targetScenarioIds: ["future"], manualSeasonalPeriods: { revenue: 12 }
      })
    ));
    expect(screen.getAllByText(/Saved prediction: January plan/i).some((element) => element.tagName === "SMALL")).toBe(true);

    fireEvent.click(screen.getByLabelText(/Include current Reality/));
    await waitFor(() => expect(
      screen.getAllByText(/Current manually entered realized data from Reality/i).some((element) => element.tagName === "SMALL")
    ).toBe(true));
    expect(api.fetchTimeseries).toHaveBeenCalledWith("acme", "reality", expect.any(AbortSignal));
  });

  it("selects and deselects all numeric metrics for comparison", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/Reality remains live manually entered/i);

    const metrics = screen.getByRole("group", { name: "Numeric metrics" });
    const allMetrics = within(metrics).getByLabelText("All numeric metrics");
    const revenue = within(metrics).getByLabelText("Revenue (EUR)");

    expect(allMetrics).toBeChecked();
    expect(revenue).toBeChecked();
    expect(within(metrics).queryByLabelText("Notes (no unit)")).not.toBeInTheDocument();
    fireEvent.click(allMetrics);
    expect(revenue).not.toBeChecked();
    fireEvent.click(allMetrics);
    expect(revenue).toBeChecked();
  });

  it("formats unavailable selected models and reports them in the chart", async () => {
    render(<PredictionsTab orgId="acme" />);

    expect(await screen.findByLabelText("seasonal naive")).toBeChecked();
    expect(screen.getByText("No results to show for: seasonal naive.")).toBeVisible();
  });

  it("keeps deleted target scenarios available for saved-version comparison", async () => {
    api.fetchScenarios.mockResolvedValueOnce([
      { id: "reality", name: "Reality", description: "", protected: true }
    ]);
    render(<PredictionsTab orgId="acme" />);

    expect(await screen.findByText(/No active non-Reality scenarios/i)).toBeVisible();
    const comparisonSelector = screen.getAllByRole("group", { name: "Target scenarios" })[1];
    expect(within(comparisonSelector).getByLabelText("Deleted scenario (future)")).toBeChecked();
    expect(screen.getByRole("img", { name: "Revenue prediction comparison chart in EUR" })).toBeVisible();
  });

  it("keeps creation unavailable when preflight finds no forecastable metrics", async () => {
    api.preflightPredictions.mockResolvedValueOnce({ metrics: [] });
    render(<PredictionsTab orgId="acme" />);
    await screen.findAllByText("January plan");

    fireEvent.change(screen.getAllByLabelText("Start date")[0], { target: { value: "2026-01-10" } });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));

    expect(await screen.findByText(/No forecastable metrics were found/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Create immutable version" })).toBeDisabled();
    expect(api.createPrediction).not.toHaveBeenCalled();
  });

  it("renders loading, empty, and request-error states", async () => {
    api.fetchScenarios.mockReturnValueOnce(new Promise(() => undefined));
    const { unmount } = render(<PredictionsTab orgId="acme" />);
    expect(screen.getByText("Loading prediction workspace…")).toBeVisible();
    unmount();

    api.fetchPredictions.mockResolvedValueOnce([]);
    render(<PredictionsTab orgId="acme" />);
    expect(await screen.findByText("No saved prediction versions yet.")).toBeVisible();

    api.fetchScenarios.mockRejectedValueOnce(new Error("Service unavailable"));
    render(<PredictionsTab orgId="acme" />);
    expect(await screen.findByText("Predictions could not be loaded")).toBeVisible();
  });

  it("aborts in-flight loading when unmounted", async () => {
    let requestSignal: AbortSignal | undefined;
    api.fetchScenarios.mockImplementationOnce((_orgId: string, signal: AbortSignal) => {
      requestSignal = signal;
      return new Promise(() => undefined);
    });
    const { unmount } = render(<PredictionsTab orgId="acme" />);

    await waitFor(() => expect(requestSignal).toBeDefined());
    unmount();
    expect(requestSignal?.aborted).toBe(true);
  });
});
