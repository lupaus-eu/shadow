import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PredictionsApiError, type PredictionVersionDetailDto } from "../../api/predictions";
import PredictionsTab from "./PredictionsTab";

const api = vi.hoisted(() => ({
  fetchScenarios: vi.fn(),
  fetchEvents: vi.fn(),
  fetchPredictions: vi.fn(),
  fetchPrediction: vi.fn(),
  fetchPredictionRequests: vi.fn(),
  fetchPredictionRequest: vi.fn(),
  preflightPredictions: vi.fn(),
  createPrediction: vi.fn(),
  cancelPredictionRequest: vi.fn(),
  fetchTimeseries: vi.fn()
}));

vi.mock("../../api/scenarios", () => ({ fetchScenarios: api.fetchScenarios }));
vi.mock("../../api/events", () => ({ fetchEvents: api.fetchEvents }));
vi.mock("../../api/predictions", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../api/predictions")>(),
  fetchPredictions: api.fetchPredictions,
  fetchPrediction: api.fetchPrediction,
  fetchPredictionRequests: api.fetchPredictionRequests,
  fetchPredictionRequest: api.fetchPredictionRequest,
  preflightPredictions: api.preflightPredictions,
  createPrediction: api.createPrediction,
  cancelPredictionRequest: api.cancelPredictionRequest
}));
vi.mock("../../api/timeseries", () => ({ fetchTimeseries: api.fetchTimeseries }));

const version: PredictionVersionDetailDto = {
  id: "version-1", name: "January plan", startDate: "2026-01-10", endDate: "2026-02-10",
  cutoffMode: "asOfStart", confidenceLevel: 80, createdTime: "2026-01-01T12:00:00Z", modelConfiguration: {},
  targets: [{
    scenarioId: "future", metricId: "revenue", metricName: "Revenue",
    timeUnit: "month", unit: "EUR", status: "eligible", reason: null, seasonalPeriod: 12,
    seasonalPeriodSource: "automatic", sourceSnapshot: {}, inputSnapshot: {}, results: [{
      kind: "naive", status: "available", reason: null, predictionIntervalStatus: "not_applicable", predictionIntervalReason: null, crossValidationStatus: "unavailable",
      crossValidationMae: null, configuration: {}, points: [{ date: "2026-01-10", value: 30, lowerBound: null, upperBound: null }, { date: "2026-02-10", value: 34, lowerBound: null, upperBound: null }]
    }, {
      kind: "seasonal_naive", status: "ineligible", reason: "Insufficient seasonal history", predictionIntervalStatus: "not_applicable", predictionIntervalReason: null, crossValidationStatus: "unavailable",
      crossValidationMae: null, configuration: {}, points: []
    }]
  }, {
    scenarioId: "future", metricId: "notes", metricName: "Notes",
    timeUnit: "month", unit: null, status: "ineligible", reason: "Only numeric metrics can be forecast.", seasonalPeriod: null,
    seasonalPeriodSource: null, sourceSnapshot: {}, inputSnapshot: {}, results: [{
      kind: "naive", status: "ineligible", reason: "Only numeric metrics can be forecast.", predictionIntervalStatus: "not_applicable", predictionIntervalReason: null, crossValidationStatus: "unavailable",
      crossValidationMae: null, configuration: {}, points: []
    }]
  }]
};

const allModelKinds = ["naive", "seasonal_naive", "average", "mlforecast", "sarima", "prophet"];

async function runPreflight() {
  fireEvent.change(screen.getByLabelText("Version name"), { target: { value: "Created plan" } });
  fireEvent.change(screen.getAllByLabelText("Start date")[0], { target: { value: "2026-01-10" } });
  fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
  fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
  await screen.findByText("Preflight eligibility");
  fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), { target: { value: "12" } });
}

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
    api.fetchPredictionRequests.mockResolvedValue([]);
    api.preflightPredictions.mockResolvedValue({ metrics: [{
      scenarioId: "future", metricId: "revenue", status: "eligible", reason: null,
      seasonalPeriod: null, seasonalPeriodSource: null, requiresManualSeasonalPeriod: true
    }] });
    api.createPrediction.mockResolvedValue({
      id: "request-2", name: "Created plan", state: "queued",
      submittedTime: "2026-01-01T12:00:00Z", startTime: null, finishTime: null,
      failureCode: null, failureReason: null, completedPredictionId: null
    });
    api.fetchTimeseries.mockResolvedValue([{ id: "revenue", name: "Revenue", description: "", unit: "EUR", timeUnit: "month", valueUnit: "number", values: [{ date: "2026-01-10", value: 28 }] }]);
  });

  it("renders without global workspace selection, includes Reality targets, and synchronizes event dates", async () => {
    render(<PredictionsTab orgId="acme" />);

    await waitFor(() => expect(screen.getByText(/selected scenario's own data/i)).toBeVisible());
    expect(screen.getByText(/selected scenario's own data/i)).toBeVisible();
    const targetSelector = screen.getAllByRole("group", { name: "Target scenarios" })[0];
    expect(within(targetSelector).getByLabelText("Future plan")).toBeChecked();
    expect(within(targetSelector).getByLabelText("Reality")).toBeChecked();
    const startEvents = screen.getByRole("group", { name: "Start event" });
    const endEvents = screen.getByRole("group", { name: "End event" });
    fireEvent.click(startEvents.querySelector("summary") as HTMLElement);
    expect(within(startEvents).getByRole("button", { name: /Reality · Reality event/ })).toBeVisible();

    fireEvent.click(within(startEvents).getByRole("button", { name: /Future plan · Future start/ }));
    expect(screen.getAllByLabelText("Start date")[0]).toHaveValue("2026-01-05");
    expect(within(endEvents).queryByRole("button", { name: /Reality · Reality event/ })).not.toBeInTheDocument();

    const plotDateRange = screen.getByText("Plot date range").parentElement;
    expect(within(plotDateRange!).getByText("Start date")).toBeVisible();
    expect(within(plotDateRange!).getByText("End date")).toBeVisible();

    fireEvent.change(screen.getAllByLabelText("Start date")[0], { target: { value: "2026-01-06" } });
    expect(within(startEvents).getAllByText("No event selected")[0]).toBeVisible();
  });

  it("searches dropdown options and initially selects only the first saved version", async () => {
    const secondVersion = { ...version, id: "version-2", name: "February plan" };
    api.fetchPredictions.mockResolvedValueOnce([version, secondVersion]);
    api.fetchPrediction.mockImplementation((_orgId: string, id: string) =>
      Promise.resolve(id === secondVersion.id ? secondVersion : version)
    );
    render(<PredictionsTab orgId="acme" />);

    await screen.findByText(/selected scenario's own data/i);
    expect(screen.getAllByPlaceholderText("Type to search...")).toHaveLength(6);
    const versions = screen.getByRole("group", { name: "Versions" });
    expect(within(versions).getByLabelText("January plan (80% prediction interval)")).toBeChecked();
    expect(within(versions).getByLabelText("February plan (80% prediction interval)")).not.toBeChecked();

    fireEvent.change(screen.getByLabelText("Search Versions"), { target: { value: "february" } });
    expect(within(versions).queryByLabelText("January plan (80% prediction interval)")).not.toBeInTheDocument();
    expect(within(versions).getByLabelText("February plan (80% prediction interval)")).not.toBeChecked();

    const targets = screen.getAllByRole("group", { name: "Target scenarios" })[0];
    fireEvent.change(within(targets).getByLabelText("Search Target scenarios"), { target: { value: "future" } });
    expect(within(targets).queryByLabelText("Reality")).not.toBeInTheDocument();
    expect(within(targets).getByLabelText("Future plan")).toBeChecked();

    const startEvents = screen.getByRole("group", { name: "Start event" });
    fireEvent.click(startEvents.querySelector("summary") as HTMLElement);
    fireEvent.change(screen.getByLabelText("Search Start event"), { target: { value: "future start" } });
    expect(within(startEvents).getByRole("button", { name: /Future start/ })).toBeVisible();
    expect(within(startEvents).queryByRole("button", { name: /Reality event/ })).not.toBeInTheDocument();

    const metrics = screen.getByRole("group", { name: "Numeric metrics" });
    fireEvent.change(within(metrics).getByLabelText("Search Numeric metrics"), { target: { value: "revenue" } });
    expect(within(metrics).getByLabelText("Revenue (EUR)")).toBeChecked();
    expect(within(screen.getByRole("group", { name: "Models and baselines" })).queryByLabelText("Search Models and baselines")).not.toBeInTheDocument();
  });

  it("submits a preflight-backed create request with manual seasonality and renders provenance", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findAllByText(/January plan \(80% prediction interval\)/);

    fireEvent.change(screen.getByLabelText("Version name"), { target: { value: "Created plan" } });
    fireEvent.change(screen.getAllByLabelText("Start date")[0], { target: { value: "2026-01-10" } });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByLabelText(/All current scenario/));
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));

    expect(await screen.findByText("Preflight eligibility")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));

    await waitFor(() => expect(api.createPrediction).toHaveBeenCalledWith(
      "acme",
      expect.objectContaining({
        name: "Created plan", targetScenarioIds: ["reality", "future"],
        manualSeasonalPeriods: { revenue: 12 }, cutoffMode: "allCurrentScenario", confidenceLevel: 80
      })
    ));
    expect(screen.getAllByText(/Saved prediction: January plan/i).some((element) => element.tagName === "SMALL")).toBe(true);

    fireEvent.click(screen.getByLabelText(/Include current Reality/));
    await waitFor(() => expect(
      screen.getAllByText(/Current manually entered realized data from Reality/i).some((element) => element.tagName === "SMALL")
    ).toBe(true));
    expect(api.fetchTimeseries).toHaveBeenCalledWith("acme", "reality", expect.any(AbortSignal));
  });

  it("shows active and recent request states, and keeps the server cancellation result", async () => {
    const queued = {
      id: "queued-request", name: "Queued plan", state: "queued" as const,
      submittedTime: "2026-01-01T12:00:00Z", startTime: null, finishTime: null,
      failureCode: null, failureReason: null, completedPredictionId: null
    };
    const running = {
      id: "running-request", name: "Running plan", state: "running" as const,
      submittedTime: "2026-01-01T12:01:00Z", startTime: "2026-01-01T12:02:00Z", finishTime: null,
      failureCode: null, failureReason: null, completedPredictionId: null
    };
    const stopping = {
      id: "stopping-request", name: "Stopping plan", state: "cancelling" as const,
      submittedTime: "2026-01-01T12:01:30Z", startTime: "2026-01-01T12:02:00Z", finishTime: null,
      failureCode: null, failureReason: null, completedPredictionId: null
    };
    const completed = {
      id: "completed-request", name: "Completed plan", state: "completed" as const,
      submittedTime: "2026-01-01T12:03:00Z", startTime: "2026-01-01T12:04:00Z", finishTime: "2026-01-01T12:05:00Z",
      failureCode: null, failureReason: null, completedPredictionId: "version-1"
    };
    const cancelled = {
      id: "cancelled-request", name: "Cancelled plan", state: "cancelled" as const,
      submittedTime: "2026-01-01T12:03:00Z", startTime: null, finishTime: "2026-01-01T12:05:00Z",
      failureCode: null, failureReason: null, completedPredictionId: null
    };
    const failed = {
      id: "failed-request", name: "Failed plan", state: "failed" as const,
      submittedTime: "2026-01-01T12:03:00Z", startTime: "2026-01-01T12:04:00Z", finishTime: "2026-01-01T12:05:00Z",
      failureCode: "calculation_failed", failureReason: "The calculation could not be completed.", completedPredictionId: null
    };
    api.fetchPredictionRequests.mockResolvedValue([running, stopping, queued, completed, cancelled, failed]);
    api.cancelPredictionRequest.mockResolvedValue({
      ...running, state: "completed", finishTime: "2026-01-01T12:06:00Z", completedPredictionId: "version-1"
    });

    render(<PredictionsTab orgId="acme" />);
    await screen.findByText("Queued plan");
    expect(screen.getByText("Queued", { selector: ".prediction-request__state" })).toBeVisible();
    expect(screen.getByText("Calculating prediction values")).toBeVisible();
    expect(screen.getByText("Stopping")).toBeVisible();
    expect(screen.getByText("Completed")).toBeVisible();
    expect(screen.getByText("Cancelled")).toBeVisible();
    expect(screen.getByText("Failed")).toBeVisible();
    expect(screen.getByText("The calculation could not be completed.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Remove from queue" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(api.cancelPredictionRequest).toHaveBeenCalledWith("acme", "running-request"));
    const completedRow = screen.getByText("Running plan").closest("article")!;
    expect(within(completedRow).getByText("Completed")).toBeVisible();
    expect(within(completedRow).queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
  });

  it("does not overlap two-second request polls", async () => {
    vi.useFakeTimers();
    let resolveFirstPoll!: (value: unknown[]) => void;
    api.fetchPredictionRequests
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirstPoll = resolve; }))
      .mockResolvedValue([]);

    render(<PredictionsTab orgId="acme" />);
    await act(async () => undefined);
    expect(api.fetchPredictionRequests).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(6_000); });
    expect(api.fetchPredictionRequests).toHaveBeenCalledTimes(1);
    await act(async () => { resolveFirstPoll([]); });
    await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });
    expect(api.fetchPredictionRequests).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("loads and selects a completed request from this tab without resetting existing comparison choices", async () => {
    const completedVersion = { ...version, id: "version-2", name: "Completed plan" };
    const completedRequest = {
      id: "request-2", name: "Created plan", state: "completed" as const,
      submittedTime: "2026-01-01T12:00:00Z", startTime: "2026-01-01T12:01:00Z",
      finishTime: "2026-01-01T12:02:00Z", failureCode: null, failureReason: null,
      completedPredictionId: "version-2"
    };
    api.fetchPredictions
      .mockResolvedValueOnce([version])
      .mockResolvedValueOnce([version, completedVersion]);
    api.fetchPrediction.mockImplementation((_orgId: string, id: string) =>
      Promise.resolve(id === "version-2" ? completedVersion : version)
    );
    api.fetchPredictionRequests
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([completedRequest]);

    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    const versions = screen.getByRole("group", { name: "Versions" });
    fireEvent.click(within(versions).getByLabelText("January plan (80% prediction interval)"));
    expect(within(versions).getByLabelText("January plan (80% prediction interval)")).not.toBeChecked();

    fireEvent.change(screen.getByLabelText("Version name"), { target: { value: "Created plan" } });
    fireEvent.change(screen.getAllByLabelText("Start date")[0], { target: { value: "2026-01-10" } });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await screen.findByText("Preflight eligibility");
    fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    await screen.findByText(/was accepted and queued/i);

    fireEvent(document, new Event("visibilitychange"));
    await waitFor(() => expect(within(versions).getByLabelText("Completed plan (80% prediction interval)")).toBeChecked());
    expect(within(versions).getByLabelText("January plan (80% prediction interval)")).not.toBeChecked();
  });

  it("uses the visible default level, validates it, and invalidates stale preflight", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);

    const confidenceLevel = screen.getByLabelText("Prediction interval level");
    expect(confidenceLevel).toHaveValue(80);
    fireEvent.change(screen.getAllByLabelText("Start date")[0], { target: { value: "2026-01-10" } });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await waitFor(() => expect(api.preflightPredictions).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({ confidenceLevel: 80 })
    ));
    expect(screen.getByRole("button", { name: "Queue prediction" })).toBeEnabled();

    fireEvent.change(confidenceLevel, { target: { value: "90" } });
    expect(screen.getByRole("button", { name: "Queue prediction" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await waitFor(() => expect(api.preflightPredictions).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({ confidenceLevel: 90 })
    ));

    for (const invalidLevel of ["", "80.5", "49", "100"]) {
      fireEvent.change(confidenceLevel, { target: { value: invalidLevel } });
      fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(/whole-number|50 through 99/i);
    }
    expect(api.preflightPredictions).toHaveBeenCalledTimes(2);
  });

  it("renders available interval bands behind point lines with accessible bounds", async () => {
    const intervalVersion: PredictionVersionDetailDto = {
      ...version,
      confidenceLevel: 90,
      targets: [{
        ...version.targets[0],
        results: [{
          ...version.targets[0].results[0],
          kind: "mlforecast",
          predictionIntervalStatus: "available",
          points: [
            { date: "2026-01-10", value: 30, lowerBound: 20, upperBound: 40 },
            { date: "2026-02-10", value: 34, lowerBound: 24, upperBound: 44 }
          ]
        }]
      }]
    };
    api.fetchPredictions.mockResolvedValueOnce([intervalVersion]);
    api.fetchPrediction.mockResolvedValueOnce(intervalVersion);
    const { container } = render(<PredictionsTab orgId="acme" />);

    await screen.findByText(/selected scenario's own data/i);
    expect(container.querySelector(".prediction-chart__interval-band")).toBeInTheDocument();
    expect(container.querySelector("svg")?.textContent).toContain("44.000");
    expect(screen.getByText(/point estimate 30 EUR, lower bound 20 EUR, upper bound 40 EUR, saved 90% prediction interval/i)).toBeInTheDocument();
  });

  it("selects and deselects all numeric metrics for comparison", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);

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

    const comparisonModels = await screen.findByRole("group", { name: "Models and baselines" });
    expect(within(comparisonModels).getByLabelText("Seasonal naive")).toBeChecked();
    expect(screen.getByText("No results to show for: Seasonal naive.")).toBeVisible();
  });

  it("selects all six models by default and sends them with preflight and creation", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);

    const models = screen.getByRole("group", { name: "Models" });
    expect(within(models).getByText("All models", { selector: "summary" })).toBeInTheDocument();
    expect(within(models).getByLabelText("All models")).toBeChecked();
    for (const label of ["Naive", "Seasonal naive", "Average", "MLForecast", "SARIMA", "Prophet"]) {
      expect(within(models).getByLabelText(label)).toBeChecked();
    }
    await runPreflight();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));

    await waitFor(() => expect(api.createPrediction).toHaveBeenCalledWith(
      "acme", expect.objectContaining({ modelKinds: allModelKinds })
    ));
    expect(api.preflightPredictions).toHaveBeenCalledWith(
      "acme", expect.objectContaining({ modelKinds: allModelKinds })
    );
  });

  it("sends only the remaining models in canonical order without invalidating preflight", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    await runPreflight();

    const models = screen.getByRole("group", { name: "Models" });
    fireEvent.click(within(models).getByLabelText("All models"));
    fireEvent.click(within(models).getByLabelText("Prophet"));
    fireEvent.click(within(models).getByLabelText("Naive"));
    expect(within(models).getByText("2 selected", { selector: "summary" })).toBeInTheDocument();
    expect(screen.getByText("Preflight eligibility")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));

    await waitFor(() => expect(api.createPrediction).toHaveBeenCalledWith(
      "acme", expect.objectContaining({ modelKinds: ["naive", "prophet"] })
    ));
    expect(api.preflightPredictions).toHaveBeenCalledTimes(1);
  });

  it("blocks preflight and creation when no model is selected", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    await runPreflight();

    const models = screen.getByRole("group", { name: "Models" });
    fireEvent.click(within(models).getByLabelText("All models"));
    expect(within(models).getByText("No models selected", { selector: "summary" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Select at least one model.");
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Select at least one model.");

    expect(api.createPrediction).not.toHaveBeenCalled();
    expect(api.preflightPredictions).toHaveBeenCalledTimes(1);
    fireEvent.click(within(models).getByLabelText("Average"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a create-time validation error in the form", async () => {
    api.createPrediction.mockRejectedValueOnce(
      new PredictionsApiError(422, "Prediction request exceeds the 110000 prediction point limit.")
    );
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    await runPreflight();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not queue prediction. Prediction request exceeds the 110000 prediction point limit."
    );
    expect(screen.getByLabelText("Version name")).toHaveValue("Created plan");
    expect(screen.getByRole("button", { name: "Queue prediction" })).toBeEnabled();
  });

  it("compares Prophet with its own interval band and shows each version's models", async () => {
    const prophetVersion: PredictionVersionDetailDto = {
      ...version,
      id: "version-2", name: "Prophet plan",
      modelConfiguration: { modelKinds: ["naive", "prophet"] },
      targets: [{
        ...version.targets[0],
        results: [version.targets[0].results[0], {
          ...version.targets[0].results[0],
          kind: "prophet",
          predictionIntervalStatus: "available",
          points: [
            { date: "2026-01-10", value: 31, lowerBound: 21, upperBound: 41 },
            { date: "2026-02-10", value: 35, lowerBound: 25, upperBound: 45 }
          ]
        }]
      }]
    };
    api.fetchPredictions.mockResolvedValueOnce([prophetVersion, version]);
    api.fetchPrediction.mockImplementation((_orgId: string, id: string) =>
      Promise.resolve(id === prophetVersion.id ? prophetVersion : version)
    );
    const { container } = render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);

    const comparisonModels = screen.getByRole("group", { name: "Models and baselines" });
    expect(within(comparisonModels).getByLabelText("Prophet")).toBeChecked();
    const svg = screen.getByRole("img", { name: /Revenue prediction comparison chart/ });
    const prophetLine = svg.querySelector('[data-series-id="version-2:future:revenue:prophet"] path');
    expect(prophetLine).toHaveAttribute("stroke-dasharray", "10 3 2 3");
    expect(container.querySelectorAll(".prediction-chart__interval-band")).toHaveLength(1);
    expect(within(svg).getByText("Prophet plan · Future plan · Prophet: saved 80% prediction interval.")).toBeInTheDocument();
    expect(screen.queryByText(/No results to show for/)).not.toBeInTheDocument();

    const versions = screen.getByRole("group", { name: "Versions" });
    expect(within(versions).getByLabelText("Prophet plan (80% prediction interval)")).toHaveAccessibleDescription("Models: Naive, Prophet");
    expect(within(versions).getByLabelText("January plan (80% prediction interval)")).toHaveAccessibleDescription("Models: Naive, Seasonal naive");

    fireEvent.click(within(comparisonModels).getByLabelText("All models and baselines"));
    fireEvent.click(within(comparisonModels).getByLabelText("Seasonal naive"));
    expect(screen.getByText("Not run by the selected versions: Seasonal naive.")).toBeVisible();
    expect(screen.queryByText(/No results to show for/)).not.toBeInTheDocument();

    fireEvent.click(within(versions).getByLabelText("January plan (80% prediction interval)"));
    expect(screen.getByText("No results to show for: Seasonal naive.")).toBeVisible();
    expect(screen.queryByText(/Not run by the selected versions/)).not.toBeInTheDocument();
  });

  it.each(["unavailable", "not_applicable"] as const)("draws no Prophet band when its interval is %s", async (intervalStatus) => {
    const prophetVersion: PredictionVersionDetailDto = {
      ...version,
      modelConfiguration: { modelKinds: ["prophet"] },
      targets: [{
        ...version.targets[0],
        results: [{
          ...version.targets[0].results[0],
          kind: "prophet",
          predictionIntervalStatus: intervalStatus,
          predictionIntervalReason: intervalStatus === "unavailable" ? "Prophet prediction interval is unavailable." : null,
          points: [
            { date: "2026-01-10", value: 31, lowerBound: 21, upperBound: 41 },
            { date: "2026-02-10", value: 35, lowerBound: 25, upperBound: 45 }
          ]
        }]
      }]
    };
    api.fetchPredictions.mockResolvedValueOnce([prophetVersion]);
    api.fetchPrediction.mockResolvedValueOnce(prophetVersion);
    const { container } = render(<PredictionsTab orgId="acme" />);

    const svg = await screen.findByRole("img", { name: /Revenue prediction comparison chart/ });
    expect(svg.querySelector('[data-series-id="version-1:future:revenue:prophet"]')).toBeInTheDocument();
    expect(container.querySelector(".prediction-chart__interval-band")).not.toBeInTheDocument();
  });

  it("keeps deleted target scenarios available for saved-version comparison", async () => {
    api.fetchScenarios.mockResolvedValueOnce([
      { id: "reality", name: "Reality", description: "", protected: true }
    ]);
    render(<PredictionsTab orgId="acme" />);

    await screen.findByText(/selected scenario's own data/i);
    expect(within(screen.getAllByRole("group", { name: "Target scenarios" })[0]).getByLabelText("Reality")).toBeChecked();
    const comparisonSelector = screen.getAllByRole("group", { name: "Target scenarios" })[1];
    expect(within(comparisonSelector).getByLabelText("Deleted scenario (future)")).toBeChecked();
    expect(screen.getByRole("img", { name: "Revenue prediction comparison chart in EUR" })).toBeVisible();
  });

  it("keeps creation unavailable when preflight finds no forecastable metrics", async () => {
    api.preflightPredictions.mockResolvedValueOnce({ metrics: [] });
    render(<PredictionsTab orgId="acme" />);
    await screen.findAllByText(/January plan \(80% prediction interval\)/);

    fireEvent.change(screen.getAllByLabelText("Start date")[0], { target: { value: "2026-01-10" } });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));

    expect(await screen.findByText(/No forecastable metrics were found/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Queue prediction" })).toBeDisabled();
    expect(api.createPrediction).not.toHaveBeenCalled();
  });

  it("renders loading, empty, and request-error states", async () => {
    api.fetchScenarios.mockReturnValueOnce(new Promise(() => undefined));
    const { unmount } = render(<PredictionsTab orgId="acme" />);
    expect(screen.getByText("Loading prediction workspace…")).toBeVisible();
    unmount();

    api.fetchPredictions.mockResolvedValueOnce([]);
    render(<PredictionsTab orgId="acme" />);
    expect(await screen.findByText("Select saved versions, scenarios, models and metrics with available numeric points to plot them.")).toBeVisible();

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

  it.each([99, 100, 101])("renders %i-point lines with independent marker thresholds and hover details", async (count) => {
    const points = Array.from({ length: count }, (_, index) => ({
      date: new Date(Date.UTC(2025, 11, 31 + index)).toISOString().slice(0, 10),
      value: index + 30, lowerBound: index + 20, upperBound: index + 40
    }));
    const dense = {
      ...version, startDate: points[0].date, endDate: points.at(-1)!.date,
      targets: [{ ...version.targets[0], timeUnit: "day" as const, results: [
        { ...version.targets[0].results[0], kind: "mlforecast", predictionIntervalStatus: "available" as const, points },
        { ...version.targets[0].results[0], points: [points[0], points.at(-1)!] }
      ] }]
    };
    api.fetchPredictions.mockResolvedValueOnce([dense]);
    api.fetchPrediction.mockResolvedValueOnce(dense);
    api.fetchTimeseries.mockResolvedValueOnce([{ id: "revenue", name: "Revenue", unit: "EUR",
      valueUnit: "number", timeUnit: "day", values: points.map(({ date, value }) => ({ date, value: value - 1 })) }]);
    const { container } = render(<PredictionsTab orgId="acme" />);
    const svg = await screen.findByRole("img", { name: /Revenue prediction comparison chart/ });
    const fitted = svg.querySelector('[data-series-id="version-1:future:revenue:mlforecast"]')!;
    const sparse = svg.querySelector('[data-series-id="version-1:future:revenue:naive"]')!;
    expect(fitted.querySelectorAll('.prediction-chart__point')).toHaveLength(count < 100 ? count : 0);
    expect(fitted.querySelectorAll('.prediction-chart__point-hit-target')).toHaveLength(count >= 100 ? count : 0);
    expect(sparse.querySelectorAll('.prediction-chart__point')).toHaveLength(2);
    expect(fitted.querySelector('path')?.getAttribute('d')?.match(/[ML]/g)).toHaveLength(count);
    expect(fitted.querySelector('circle')).toHaveAttribute('cx', '56');
    expect(fitted.querySelector('circle')?.getAttribute('fill')).toBe(count >= 100 ? 'transparent' : '#c94a11');
    expect(fitted.querySelector('circle title')).toHaveTextContent(/2025-12-31, point estimate 30 EUR, lower bound 20 EUR, upper bound 40 EUR, saved 80% prediction interval/);
    const band = svg.querySelector('.prediction-chart__interval-band')!;
    expect(band.compareDocumentPosition(fitted) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(svg.querySelector('.prediction-chart__unit')).toHaveTextContent('EUR');
    expect(container.querySelector('.prediction-chart > header')).not.toHaveTextContent('EUR');
    const labels = svg.querySelectorAll('.prediction-chart__date');
    expect(labels.length).toBeLessThanOrEqual(22);
    expect(labels[0]).toHaveTextContent('12-31');
    expect(labels[labels.length - 1]).toHaveTextContent(points.at(-1)!.date.slice(5));
    expect(svg.querySelectorAll('.prediction-chart__year-boundary')).toHaveLength(1);
    expect(svg.querySelectorAll('.prediction-chart__year')).toHaveLength(1);

    fireEvent.click(screen.getByLabelText(/Include current Reality/));
    await waitFor(() => expect(svg.querySelector('[data-series-id="reality:revenue"]')).toBeInTheDocument());
    const reality = svg.querySelector('[data-series-id="reality:revenue"]')!;
    expect(reality.querySelectorAll('.prediction-chart__point')).toHaveLength(count < 100 ? count : 0);
    expect(reality.querySelectorAll('.prediction-chart__point-hit-target')).toHaveLength(count >= 100 ? count : 0);
    fireEvent.change(screen.getByLabelText('Plot end date'), { target: { value: points[1].date } });
    expect(fitted.querySelectorAll('.prediction-chart__point')).toHaveLength(2);
    expect(reality.querySelectorAll('.prediction-chart__point')).toHaveLength(2);
    expect(sparse.querySelectorAll('.prediction-chart__point')).toHaveLength(1);
  });

  it("plots overlapping Reality observations despite extra dates and removes the layer when unchecked", async () => {
    api.fetchTimeseries.mockResolvedValueOnce([{ id: "revenue", name: "Revenue", unit: "EUR",
      valueUnit: "number", timeUnit: "day", values: [
        { date: "2025-01-01", value: -100 }, { date: "2026-01-10", value: 28 },
        { date: "2026-02-10", value: 32 }, { date: "2027-01-01", value: 1000 }
      ] }]);
    render(<PredictionsTab orgId="acme" />);
    const svg = await screen.findByRole('img', { name: /Revenue prediction comparison chart/ });
    const toggle = screen.getByLabelText(/Include current Reality/);
    fireEvent.click(toggle);
    await waitFor(() => expect(svg.querySelector('.prediction-chart__line--reality')).toBeInTheDocument());
    expect(svg.querySelector('.prediction-chart__line--reality')).toHaveAttribute('d', 'M56 226 L702 100.66666666666667');
    const dots = svg.querySelectorAll('[data-series-id="reality:revenue"] circle');
    expect(dots).toHaveLength(2);
    expect(dots[0]).toHaveAttribute('cx', '56');
    expect(dots[1]).toHaveAttribute('cx', '702');
    expect(svg.textContent).not.toContain('point estimate -100');
    expect(svg.textContent).not.toContain('point estimate 1000');
    fireEvent.change(screen.getByLabelText('Plot start date'), { target: { value: '2025-01-01' } });
    expect(svg.querySelectorAll('[data-series-id="reality:revenue"] circle')).toHaveLength(3);
    fireEvent.click(toggle);
    expect(svg.querySelector('.prediction-chart__line--reality')).not.toBeInTheDocument();
    expect(svg.textContent).not.toContain('Current Reality');
  });

  it("shows Reality empty feedback only after a successful load and clears errors on retry", async () => {
    let resolve!: (value: unknown[]) => void;
    api.fetchTimeseries.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    render(<PredictionsTab orgId="acme" />);
    await screen.findByRole('img', { name: /Revenue prediction comparison chart/ });
    const toggle = screen.getByLabelText(/Include current Reality/);
    fireEvent.click(toggle);
    expect(screen.getByText('Loading current Reality data…')).toBeVisible();
    expect(screen.queryByText(/No matching numeric current Reality/)).not.toBeInTheDocument();
    await act(async () => resolve([]));
    expect(screen.getByText(/No matching numeric current Reality/)).toBeVisible();
    fireEvent.click(toggle);
    api.fetchTimeseries.mockRejectedValueOnce(new Error('Unavailable'));
    fireEvent.click(toggle);
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load current Reality data. Unavailable');
    expect(screen.queryByText(/No matching numeric current Reality/)).not.toBeInTheDocument();
    fireEvent.click(toggle);
    api.fetchTimeseries.mockResolvedValueOnce([{ id: 'revenue', name: 'Revenue', valueUnit: 'number', values: [{ date: '2025-01-01', value: 1 }] }]);
    fireEvent.click(toggle);
    expect(await screen.findByText('No current Reality observations in the displayed period.')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it("ignores a cancelled Reality response after a newer request succeeds", async () => {
    let resolve!: (value: unknown[]) => void;
    api.fetchTimeseries.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    render(<PredictionsTab orgId="acme" />);
    const svg = await screen.findByRole('img', { name: /Revenue prediction comparison chart/ });
    const toggle = screen.getByLabelText(/Include current Reality/);
    fireEvent.click(toggle);
    const signal = api.fetchTimeseries.mock.calls[0][2] as AbortSignal;
    fireEvent.click(toggle);
    expect(signal.aborted).toBe(true);
    fireEvent.click(toggle);
    await waitFor(() => expect(svg.querySelector('.prediction-chart__line--reality')).toBeInTheDocument());
    await act(async () => resolve([]));
    expect(svg.querySelector('.prediction-chart__line--reality')).toBeInTheDocument();
    expect(screen.queryByText(/No matching numeric current Reality/)).not.toBeInTheDocument();
  });

});
