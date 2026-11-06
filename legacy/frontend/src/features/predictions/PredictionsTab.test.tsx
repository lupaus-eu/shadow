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
  ...(await importOriginal<typeof import("../../api/predictions")>()),
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
  id: "version-1",
  name: "January plan",
  startDate: "2026-01-10",
  endDate: "2026-02-10",
  cutoffMode: "asOfStart",
  confidenceLevel: 80,
  createdTime: "2026-01-01T12:00:00Z",
  modelConfiguration: {},
  targets: [
    {
      scenarioId: "future",
      metricId: "revenue",
      metricName: "Revenue",
      timeUnit: "month",
      unit: "EUR",
      status: "eligible",
      reason: null,
      seasonalPeriod: 12,
      seasonalPeriodSource: "automatic",
      sourceSnapshot: {},
      inputSnapshot: {},
      results: [
        {
          kind: "naive",
          status: "available",
          reason: null,
          predictionIntervalStatus: "not_applicable",
          predictionIntervalReason: null,
          crossValidationStatus: "unavailable",
          crossValidationMae: null,
          configuration: {},
          points: [
            { date: "2026-01-10", value: 30, lowerBound: null, upperBound: null },
            { date: "2026-02-10", value: 34, lowerBound: null, upperBound: null }
          ]
        },
        {
          kind: "seasonal_naive",
          status: "ineligible",
          reason: "Insufficient seasonal history",
          predictionIntervalStatus: "not_applicable",
          predictionIntervalReason: null,
          crossValidationStatus: "unavailable",
          crossValidationMae: null,
          configuration: {},
          points: []
        }
      ]
    },
    {
      scenarioId: "future",
      metricId: "notes",
      metricName: "Notes",
      timeUnit: "month",
      unit: null,
      status: "ineligible",
      reason: "Only numeric metrics can be forecast.",
      seasonalPeriod: null,
      seasonalPeriodSource: null,
      sourceSnapshot: {},
      inputSnapshot: {},
      results: [
        {
          kind: "naive",
          status: "ineligible",
          reason: "Only numeric metrics can be forecast.",
          predictionIntervalStatus: "not_applicable",
          predictionIntervalReason: null,
          crossValidationStatus: "unavailable",
          crossValidationMae: null,
          configuration: {},
          points: []
        }
      ]
    }
  ]
};

const allModelKinds = ["naive", "seasonal_naive", "average", "mlforecast", "sarima", "prophet"];

async function runPreflight() {
  fireEvent.change(screen.getByLabelText("Version name"), { target: { value: "Created plan" } });
  fireEvent.change(screen.getAllByLabelText("Start date")[0], { target: { value: "2026-01-10" } });
  fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
  fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
  await screen.findByText("Preflight eligibility");
  const manualInput = screen.queryByLabelText("Manual seasonal period for revenue");
  if (manualInput) fireEvent.change(manualInput, { target: { value: "12" } });
}

function selectRequestModels(labels: string[]) {
  const models = screen.getByRole("group", { name: "Models" });
  const all = within(models).getByLabelText("All models");
  // Clear the selection first, then pick the requested models.
  if (!(all as HTMLInputElement).checked) fireEvent.click(all);
  fireEvent.click(all);
  for (const label of labels) fireEvent.click(within(models).getByLabelText(label));
}

const nonSeasonalLabels = ["Naive", "Average", "MLForecast", "Prophet"];

function queueFormFields() {
  const manualInput = screen.queryByLabelText("Manual seasonal period for revenue");
  return [
    screen.getByLabelText("Version name"),
    screen.getAllByLabelText("Start date")[0],
    screen.getAllByLabelText("End date")[0],
    within(screen.getAllByRole("group", { name: "Target scenarios" })[0]).getByLabelText(
      "Future plan"
    ),
    screen.getByLabelText("Search Start event"),
    screen.getByLabelText("Search End event"),
    screen.getByLabelText(/As of start/),
    screen.getByLabelText(/All current scenario/),
    screen.getByLabelText("Prediction interval level"),
    within(screen.getByRole("group", { name: "Models" })).getByLabelText("Prophet"),
    ...(manualInput ? [manualInput] : [])
  ];
}

describe("PredictionsTab", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.fetchScenarios.mockResolvedValue([
      { id: "reality", name: "Reality", description: "", protected: true },
      { id: "future", name: "Future plan", description: "", protected: false }
    ]);
    api.fetchEvents.mockImplementation((_org: string, scenarioId: string) =>
      Promise.resolve(
        scenarioId === "reality"
          ? [{ id: "past", name: "Reality event", targetDate: "2026-01-03", eventDetails: "" }]
          : [
              { id: "start", name: "Future start", targetDate: "2026-01-05", eventDetails: "" },
              { id: "end", name: "Future end", targetDate: "2026-02-05", eventDetails: "" }
            ]
      )
    );
    api.fetchPredictions.mockResolvedValue([version]);
    api.fetchPrediction.mockResolvedValue(version);
    api.fetchPredictionRequests.mockResolvedValue([]);
    api.preflightPredictions.mockResolvedValue({
      metrics: [
        {
          scenarioId: "future",
          metricId: "revenue",
          status: "eligible",
          reason: null,
          seasonalPeriod: null,
          seasonalPeriodSource: null,
          requiresManualSeasonalPeriod: true
        }
      ]
    });
    api.createPrediction.mockResolvedValue({
      id: "request-2",
      name: "Created plan",
      state: "queued",
      submittedTime: "2026-01-01T12:00:00Z",
      startTime: null,
      finishTime: null,
      failureCode: null,
      failureReason: null,
      completedPredictionId: null
    });
    api.fetchTimeseries.mockResolvedValue([
      {
        id: "revenue",
        name: "Revenue",
        description: "",
        unit: "EUR",
        timeUnit: "month",
        valueUnit: "number",
        values: [{ date: "2026-01-10", value: 28 }]
      }
    ]);
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
    expect(
      within(startEvents).getByRole("button", { name: /Reality · Reality event/ })
    ).toBeVisible();

    fireEvent.click(
      within(startEvents).getByRole("button", { name: /Future plan · Future start/ })
    );
    expect(screen.getAllByLabelText("Start date")[0]).toHaveValue("2026-01-05");
    expect(
      within(endEvents).queryByRole("button", { name: /Reality · Reality event/ })
    ).not.toBeInTheDocument();

    const plotDateRange = screen.getByText("Plot date range").parentElement;
    expect(within(plotDateRange!).getByText("Start date")).toBeVisible();
    expect(within(plotDateRange!).getByText("End date")).toBeVisible();

    fireEvent.change(screen.getAllByLabelText("Start date")[0], {
      target: { value: "2026-01-06" }
    });
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
    expect(
      within(versions).getByLabelText("February plan (80% prediction interval)")
    ).not.toBeChecked();

    fireEvent.change(screen.getByLabelText("Search Versions"), { target: { value: "february" } });
    expect(
      within(versions).queryByLabelText("January plan (80% prediction interval)")
    ).not.toBeInTheDocument();
    expect(
      within(versions).getByLabelText("February plan (80% prediction interval)")
    ).not.toBeChecked();

    const targets = screen.getAllByRole("group", { name: "Target scenarios" })[0];
    fireEvent.change(within(targets).getByLabelText("Search Target scenarios"), {
      target: { value: "future" }
    });
    expect(within(targets).queryByLabelText("Reality")).not.toBeInTheDocument();
    expect(within(targets).getByLabelText("Future plan")).toBeChecked();

    const startEvents = screen.getByRole("group", { name: "Start event" });
    fireEvent.click(startEvents.querySelector("summary") as HTMLElement);
    fireEvent.change(screen.getByLabelText("Search Start event"), {
      target: { value: "future start" }
    });
    expect(within(startEvents).getByRole("button", { name: /Future start/ })).toBeVisible();
    expect(
      within(startEvents).queryByRole("button", { name: /Reality event/ })
    ).not.toBeInTheDocument();

    const metrics = screen.getByRole("group", { name: "Numeric metrics" });
    fireEvent.change(within(metrics).getByLabelText("Search Numeric metrics"), {
      target: { value: "revenue" }
    });
    expect(within(metrics).getByLabelText("Revenue (EUR)")).toBeChecked();
    expect(
      within(screen.getByRole("group", { name: "Models and baselines" })).queryByLabelText(
        "Search Models and baselines"
      )
    ).not.toBeInTheDocument();
  });

  it("submits a preflight-backed create request with manual seasonality and renders provenance", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findAllByText(/January plan \(80% prediction interval\)/);

    fireEvent.change(screen.getByLabelText("Version name"), { target: { value: "Created plan" } });
    fireEvent.change(screen.getAllByLabelText("Start date")[0], {
      target: { value: "2026-01-10" }
    });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByLabelText(/All current scenario/));
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));

    expect(await screen.findByText("Preflight eligibility")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), {
      target: { value: "12" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));

    await waitFor(() =>
      expect(api.createPrediction).toHaveBeenCalledWith(
        "acme",
        expect.objectContaining({
          name: "Created plan",
          targetScenarioIds: ["reality", "future"],
          manualSeasonalPeriods: { revenue: 12 },
          cutoffMode: "allCurrentScenario",
          confidenceLevel: 80
        })
      )
    );
    expect(
      screen
        .getAllByText(/Saved prediction: January plan/i)
        .some((element) => element.tagName === "SMALL")
    ).toBe(true);

    fireEvent.click(screen.getByLabelText(/Include current Reality/));
    await waitFor(() =>
      expect(
        screen
          .getAllByText(/Current manually entered realized data from Reality/i)
          .some((element) => element.tagName === "SMALL")
      ).toBe(true)
    );
    expect(api.fetchTimeseries).toHaveBeenCalledWith("acme", "reality", expect.any(AbortSignal));
  });

  it("keeps an entered manual seasonal period for consecutive queue cycles", async () => {
    api.preflightPredictions
      .mockResolvedValueOnce({
        metrics: [
          {
            scenarioId: "future",
            metricId: "revenue",
            status: "eligible",
            reason: null,
            seasonalPeriod: null,
            seasonalPeriodSource: null,
            requiresManualSeasonalPeriod: true
          }
        ]
      })
      .mockResolvedValueOnce({
        metrics: [
          {
            scenarioId: "future",
            metricId: "revenue",
            status: "eligible",
            reason: null,
            seasonalPeriod: 3,
            seasonalPeriodSource: "manual",
            requiresManualSeasonalPeriod: false
          }
        ]
      });
    api.createPrediction.mockImplementation((_orgId: string, payload: { name: string }) =>
      Promise.resolve({
        id: `request-${payload.name}`,
        name: payload.name,
        state: "queued",
        submittedTime: "2026-01-01T12:00:00Z",
        startTime: null,
        finishTime: null,
        failureCode: null,
        failureReason: null,
        completedPredictionId: null
      })
    );
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);

    await runPreflight();
    fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), {
      target: { value: "3" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    await waitFor(() => expect(api.createPrediction).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.queryByText("Preflight eligibility")).not.toBeInTheDocument()
    );

    fireEvent.change(screen.getByLabelText("Version name"), { target: { value: "Second plan" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await screen.findByText("Preflight eligibility");
    expect(api.preflightPredictions).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({ manualSeasonalPeriods: { revenue: 3 } })
    );
    expect(screen.getByLabelText("Manual seasonal period for revenue")).toHaveValue(3);
    expect(screen.queryByText(/Automatic seasonal period/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));

    await waitFor(() => expect(api.createPrediction).toHaveBeenCalledTimes(2));
    for (const [, payload] of api.createPrediction.mock.calls) {
      expect(payload).toEqual(expect.objectContaining({ manualSeasonalPeriods: { revenue: 3 } }));
    }
  });

  it("drops a manual period that preflight no longer lists or that the user clears", async () => {
    const requiresManual = {
      metrics: [
        {
          scenarioId: "future",
          metricId: "revenue",
          status: "eligible",
          reason: null,
          seasonalPeriod: null,
          seasonalPeriodSource: null,
          requiresManualSeasonalPeriod: true
        }
      ]
    };
    api.preflightPredictions
      .mockResolvedValueOnce(requiresManual)
      .mockResolvedValueOnce({
        metrics: [
          {
            scenarioId: "future",
            metricId: "cost",
            status: "eligible",
            reason: null,
            seasonalPeriod: 12,
            seasonalPeriodSource: "automatic",
            requiresManualSeasonalPeriod: false
          }
        ]
      })
      .mockResolvedValueOnce(requiresManual)
      .mockResolvedValueOnce({
        metrics: [
          {
            scenarioId: "future",
            metricId: "revenue",
            status: "eligible",
            reason: null,
            seasonalPeriod: 12,
            seasonalPeriodSource: "automatic",
            requiresManualSeasonalPeriod: false
          }
        ]
      });
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);

    await runPreflight();
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await waitFor(() =>
      expect(screen.queryByLabelText("Manual seasonal period for revenue")).not.toBeInTheDocument()
    );
    expect(api.preflightPredictions).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({ manualSeasonalPeriods: { revenue: 12 } })
    );
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    const manualInput = await screen.findByLabelText("Manual seasonal period for revenue");
    expect(api.preflightPredictions).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({ manualSeasonalPeriods: {} })
    );
    expect(manualInput).toHaveValue(2);

    fireEvent.change(manualInput, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    expect(
      await screen.findByText("Automatic seasonal period: 12 (automatic)")
    ).toBeInTheDocument();
    expect(api.preflightPredictions).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({ manualSeasonalPeriods: {} })
    );
    expect(screen.queryByLabelText("Manual seasonal period for revenue")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    await waitFor(() =>
      expect(api.createPrediction).toHaveBeenCalledWith(
        "acme",
        expect.objectContaining({ manualSeasonalPeriods: {} })
      )
    );
  });

  it("shows the manual input for a manual-source metric and blocks a missing or invalid period", async () => {
    api.preflightPredictions.mockResolvedValue({
      metrics: [
        {
          scenarioId: "future",
          metricId: "revenue",
          status: "eligible",
          reason: null,
          seasonalPeriod: 4,
          seasonalPeriodSource: "manual",
          requiresManualSeasonalPeriod: false
        },
        {
          scenarioId: "future",
          metricId: "cost",
          status: "eligible",
          reason: null,
          seasonalPeriod: 12,
          seasonalPeriodSource: "automatic",
          requiresManualSeasonalPeriod: false
        }
      ]
    });
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    fireEvent.change(screen.getByLabelText("Version name"), { target: { value: "Created plan" } });
    fireEvent.change(screen.getAllByLabelText("Start date")[0], {
      target: { value: "2026-01-10" }
    });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await screen.findByText("Preflight eligibility");

    const manualInput = screen.getByLabelText("Manual seasonal period for revenue");
    expect(manualInput).toHaveValue(4);
    expect(screen.queryByText("Automatic seasonal period: 4 (manual)")).not.toBeInTheDocument();
    expect(screen.getByText("Automatic seasonal period: 12 (automatic)")).toBeInTheDocument();
    expect(screen.queryByLabelText("Manual seasonal period for cost")).not.toBeInTheDocument();

    for (const invalidPeriod of ["", "1", "2.5"]) {
      fireEvent.change(manualInput, { target: { value: invalidPeriod } });
      fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Enter every manual seasonal period as a whole number of 2 or more, or clear it and run preflight again to try automatic detection."
      );
    }
    expect(api.createPrediction).not.toHaveBeenCalled();

    fireEvent.change(manualInput, { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    await waitFor(() =>
      expect(api.createPrediction).toHaveBeenCalledWith(
        "acme",
        expect.objectContaining({ manualSeasonalPeriods: { revenue: 5 } })
      )
    );
  });

  it("shows active and recent request states, and keeps the server cancellation result", async () => {
    const queued = {
      id: "queued-request",
      name: "Queued plan",
      state: "queued" as const,
      submittedTime: "2026-01-01T12:00:00Z",
      startTime: null,
      finishTime: null,
      failureCode: null,
      failureReason: null,
      completedPredictionId: null
    };
    const running = {
      id: "running-request",
      name: "Running plan",
      state: "running" as const,
      submittedTime: "2026-01-01T12:01:00Z",
      startTime: "2026-01-01T12:02:00Z",
      finishTime: null,
      failureCode: null,
      failureReason: null,
      completedPredictionId: null
    };
    const stopping = {
      id: "stopping-request",
      name: "Stopping plan",
      state: "cancelling" as const,
      submittedTime: "2026-01-01T12:01:30Z",
      startTime: "2026-01-01T12:02:00Z",
      finishTime: null,
      failureCode: null,
      failureReason: null,
      completedPredictionId: null
    };
    const completed = {
      id: "completed-request",
      name: "Completed plan",
      state: "completed" as const,
      submittedTime: "2026-01-01T12:03:00Z",
      startTime: "2026-01-01T12:04:00Z",
      finishTime: "2026-01-01T12:05:00Z",
      failureCode: null,
      failureReason: null,
      completedPredictionId: "version-1"
    };
    const cancelled = {
      id: "cancelled-request",
      name: "Cancelled plan",
      state: "cancelled" as const,
      submittedTime: "2026-01-01T12:03:00Z",
      startTime: null,
      finishTime: "2026-01-01T12:05:00Z",
      failureCode: null,
      failureReason: null,
      completedPredictionId: null
    };
    const failed = {
      id: "failed-request",
      name: "Failed plan",
      state: "failed" as const,
      submittedTime: "2026-01-01T12:03:00Z",
      startTime: "2026-01-01T12:04:00Z",
      finishTime: "2026-01-01T12:05:00Z",
      failureCode: "calculation_failed",
      failureReason: "The calculation could not be completed.",
      completedPredictionId: null
    };
    api.fetchPredictionRequests.mockResolvedValue([
      running,
      stopping,
      queued,
      completed,
      cancelled,
      failed
    ]);
    api.cancelPredictionRequest.mockResolvedValue({
      ...running,
      state: "completed",
      finishTime: "2026-01-01T12:06:00Z",
      completedPredictionId: "version-1"
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
    await waitFor(() =>
      expect(api.cancelPredictionRequest).toHaveBeenCalledWith("acme", "running-request")
    );
    const completedRow = await waitFor(() => {
      const row = screen.getByText("Running plan").closest("article")!;
      expect(within(row).getByText("Completed")).toBeVisible();
      return row;
    });
    expect(within(completedRow).queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
  });

  it("does not overlap two-second request polls", async () => {
    vi.useFakeTimers();
    let resolveFirstPoll!: (value: unknown[]) => void;
    api.fetchPredictionRequests
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveFirstPoll = resolve;
        })
      )
      .mockResolvedValue([]);

    render(<PredictionsTab orgId="acme" />);
    await act(async () => undefined);
    expect(api.fetchPredictionRequests).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });
    expect(api.fetchPredictionRequests).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveFirstPoll([]);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(api.fetchPredictionRequests).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("loads and selects a completed request from this tab without resetting existing comparison choices", async () => {
    const completedVersion = { ...version, id: "version-2", name: "Completed plan" };
    const completedRequest = {
      id: "request-2",
      name: "Created plan",
      state: "completed" as const,
      submittedTime: "2026-01-01T12:00:00Z",
      startTime: "2026-01-01T12:01:00Z",
      finishTime: "2026-01-01T12:02:00Z",
      failureCode: null,
      failureReason: null,
      completedPredictionId: "version-2"
    };
    api.fetchPredictions
      .mockResolvedValueOnce([version])
      .mockResolvedValueOnce([version, completedVersion]);
    api.fetchPrediction.mockImplementation((_orgId: string, id: string) =>
      Promise.resolve(id === "version-2" ? completedVersion : version)
    );
    api.fetchPredictionRequests.mockResolvedValueOnce([]).mockResolvedValueOnce([completedRequest]);

    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    const versions = screen.getByRole("group", { name: "Versions" });
    fireEvent.click(within(versions).getByLabelText("January plan (80% prediction interval)"));
    expect(
      within(versions).getByLabelText("January plan (80% prediction interval)")
    ).not.toBeChecked();

    fireEvent.change(screen.getByLabelText("Version name"), { target: { value: "Created plan" } });
    fireEvent.change(screen.getAllByLabelText("Start date")[0], {
      target: { value: "2026-01-10" }
    });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await screen.findByText("Preflight eligibility");
    fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), {
      target: { value: "12" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    await screen.findByText(/was accepted and queued/i);

    fireEvent(document, new Event("visibilitychange"));
    await waitFor(() =>
      expect(
        within(versions).getByLabelText("Completed plan (80% prediction interval)")
      ).toBeChecked()
    );
    expect(
      within(versions).getByLabelText("January plan (80% prediction interval)")
    ).not.toBeChecked();
  });

  it("uses the visible default level, validates it, and invalidates stale preflight", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);

    const confidenceLevel = screen.getByLabelText("Prediction interval level");
    expect(confidenceLevel).toHaveValue(80);
    fireEvent.change(screen.getAllByLabelText("Start date")[0], {
      target: { value: "2026-01-10" }
    });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await waitFor(() =>
      expect(api.preflightPredictions).toHaveBeenLastCalledWith(
        "acme",
        expect.objectContaining({ confidenceLevel: 80 })
      )
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Queue prediction" })).toBeEnabled()
    );

    fireEvent.change(confidenceLevel, { target: { value: "90" } });
    expect(screen.getByRole("button", { name: "Queue prediction" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await waitFor(() =>
      expect(api.preflightPredictions).toHaveBeenLastCalledWith(
        "acme",
        expect.objectContaining({ confidenceLevel: 90 })
      )
    );

    for (const invalidLevel of ["", "80.5", "49", "100"]) {
      fireEvent.change(confidenceLevel, { target: { value: invalidLevel } });
      fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(/whole-number|50 through 99/i);
      expect(confidenceLevel).toHaveAttribute("aria-invalid", "true");
    }
    expect(api.preflightPredictions).toHaveBeenCalledTimes(2);

    // Closing the error keeps the marker while the value stays invalid.
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notice" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(confidenceLevel).toHaveAttribute("aria-invalid", "true");
    expect(confidenceLevel).toHaveAttribute("aria-describedby", "prediction-interval-help");
    fireEvent.change(confidenceLevel, { target: { value: "85" } });
    expect(confidenceLevel).not.toHaveAttribute("aria-invalid");
  });

  it("renders available interval bands behind point lines with accessible bounds", async () => {
    const intervalVersion: PredictionVersionDetailDto = {
      ...version,
      confidenceLevel: 90,
      targets: [
        {
          ...version.targets[0],
          results: [
            {
              ...version.targets[0].results[0],
              kind: "mlforecast",
              predictionIntervalStatus: "available",
              points: [
                { date: "2026-01-10", value: 30, lowerBound: 20, upperBound: 40 },
                { date: "2026-02-10", value: 34, lowerBound: 24, upperBound: 44 }
              ]
            }
          ]
        }
      ]
    };
    api.fetchPredictions.mockResolvedValueOnce([intervalVersion]);
    api.fetchPrediction.mockResolvedValueOnce(intervalVersion);
    const { container } = render(<PredictionsTab orgId="acme" />);

    await screen.findByText(/selected scenario's own data/i);
    expect(container.querySelector(".prediction-chart__interval-band")).toBeInTheDocument();
    // The interval bounds set the range.
    expect(
      [...container.querySelectorAll(".prediction-chart__range")].map((label) => label.textContent)
    ).toEqual(["44", "20"]);
    expect(
      container.querySelector('[data-series-id="version-1:future:revenue:mlforecast"] circle title')
        ?.textContent
    ).toBe(
      [
        "30 EUR, lower bound 20 EUR, upper bound 40 EUR (90% prediction interval)",
        "January plan · Future plan · MLForecast",
        "2026-01-10"
      ].join("\n")
    );
  });

  it("rounds prediction hover values without changing plot geometry or Reality values", async () => {
    const preciseVersion: PredictionVersionDetailDto = {
      ...version,
      targets: [
        {
          ...version.targets[0],
          results: [
            {
              ...version.targets[0].results[0],
              kind: "mlforecast",
              predictionIntervalStatus: "available",
              points: [
                { date: "2026-01-10", value: 30.25, lowerBound: 20.125, upperBound: 40.375 },
                { date: "2026-02-10", value: 34.5678, lowerBound: 24.1, upperBound: 40 }
              ]
            }
          ]
        }
      ]
    };
    api.fetchPredictions.mockResolvedValueOnce([preciseVersion]);
    api.fetchPrediction.mockResolvedValueOnce(preciseVersion);
    api.fetchTimeseries.mockResolvedValueOnce([
      {
        id: "revenue",
        name: "Revenue",
        description: "",
        unit: "EUR",
        timeUnit: "month",
        valueUnit: "number",
        values: [{ date: "2026-01-10", value: 28.125 }]
      }
    ]);
    render(<PredictionsTab orgId="acme" />);

    const svg = await screen.findByRole("img", { name: /Revenue prediction comparison chart/ });
    const series = svg.querySelector('[data-series-id="version-1:future:revenue:mlforecast"]')!;
    const titles = [...series.querySelectorAll("circle title")].map((title) => title.textContent);
    expect(titles[0]?.split("\n")[0]).toBe(
      "30.25 EUR, lower bound 20.13 EUR, upper bound 40.38 EUR (80% prediction interval)"
    );
    expect(titles[1]?.split("\n")[0]).toBe(
      "34.57 EUR, lower bound 24.1 EUR, upper bound 40 EUR (80% prediction interval)"
    );
    expect(
      [...svg.querySelectorAll(".prediction-chart__range")].map((label) => label.textContent)
    ).toEqual(["40.38", "20.13"]);
    // Raw values: the first point lies exactly halfway between 20.125 and 40.375.
    expect(series.querySelector("circle")).toHaveAttribute("cy", "132");
    expect(series.querySelector("path")?.getAttribute("d")).toMatch(/^M56 132 L702 /);
    const band = svg.querySelector(".prediction-chart__interval-band")!.getAttribute("d")!;
    expect(band).toMatch(/^M56 38 L702 /);
    expect(band).toMatch(/L56 226 Z$/);

    fireEvent.click(screen.getByLabelText(/Include current Reality/));
    await waitFor(() =>
      expect(svg.querySelector('[data-series-id="reality:revenue"]')).toBeInTheDocument()
    );
    expect(svg.querySelector('[data-series-id="reality:revenue"] circle title')?.textContent).toBe(
      "28.125 EUR\nCurrent Reality · manually entered realized data · Revenue\n2026-01-10"
    );
  });

  it("lists every series whose dot cannot be hovered separately and formats a Reality-set range", async () => {
    const result = (kind: string, values: [number, number]) => ({
      ...version.targets[0].results[0],
      kind,
      points: [
        { date: "2026-01-10", value: values[0], lowerBound: null, upperBound: null },
        { date: "2026-02-10", value: values[1], lowerBound: null, upperBound: null }
      ]
    });
    const overlappingVersion: PredictionVersionDetailDto = {
      ...version,
      targets: [
        {
          ...version.targets[0],
          results: [
            {
              ...version.targets[0].results[0],
              kind: "mlforecast",
              predictionIntervalStatus: "available",
              points: [
                { date: "2026-01-10", value: 30, lowerBound: 20, upperBound: 40 },
                { date: "2026-02-10", value: 34, lowerBound: 24, upperBound: 44 }
              ]
            },
            result("naive", [30, 34]),
            // Over the 20-44 EUR range, 0.3 EUR is about 2.4 SVG units, closer than the dot radius.
            result("seasonal_naive", [30.3, 34]),
            // 1 EUR is about 7.8 SVG units, so this dot can be hovered separately.
            result("sarima", [31, 34])
          ]
        }
      ]
    };
    api.fetchPredictions.mockResolvedValueOnce([overlappingVersion]);
    api.fetchPrediction.mockResolvedValueOnce(overlappingVersion);
    api.fetchTimeseries.mockResolvedValueOnce([
      {
        id: "revenue",
        name: "Revenue",
        description: "",
        unit: "EUR",
        timeUnit: "month",
        valueUnit: "number",
        values: [{ date: "2026-02-10", value: 50.567 }]
      }
    ]);
    render(<PredictionsTab orgId="acme" />);

    const svg = await screen.findByRole("img", { name: /Revenue prediction comparison chart/ });
    const title = (kind: string) =>
      svg.querySelector(`[data-series-id="version-1:future:revenue:${kind}"] circle title`)
        ?.textContent;
    expect(title("mlforecast")).toBe(
      [
        "30 EUR, lower bound 20 EUR, upper bound 40 EUR (80% prediction interval)",
        "January plan · Future plan · MLForecast",
        "January plan · Future plan · Naive (no prediction interval)",
        "January plan · Future plan · Seasonal naive (30.3 EUR, no prediction interval)",
        "2026-01-10"
      ].join("\n")
    );
    expect(title("naive")).toBe(
      [
        "30 EUR",
        "January plan · Future plan · MLForecast (lower bound 20 EUR, upper bound 40 EUR (80% prediction interval))",
        "January plan · Future plan · Naive",
        "January plan · Future plan · Seasonal naive (30.3 EUR)",
        "2026-01-10"
      ].join("\n")
    );
    expect(title("sarima")).toBe("31 EUR\nJanuary plan · Future plan · SARIMA\n2026-01-10");

    // Legend samples use each line's colour and dash pattern.
    const legend = svg.closest("article")!.querySelector(".prediction-chart__legend")!;
    expect(legend.querySelectorAll("svg[aria-hidden='true']")).toHaveLength(4);
    expect(
      [...legend.querySelectorAll("line")].map((sample) => [
        sample.getAttribute("stroke"),
        sample.getAttribute("stroke-dasharray")
      ])
    ).toEqual([
      ["#c94a11", null],
      ["#2563eb", "7 4"],
      ["#8b5cf6", null],
      ["#0f766e", null]
    ]);

    fireEvent.click(screen.getByLabelText(/Include current Reality/));
    await waitFor(() =>
      expect(svg.querySelector('[data-series-id="reality:revenue"]')).toBeInTheDocument()
    );
    const realitySample = legend.querySelector("line")!;
    expect(realitySample).toHaveClass("prediction-chart__line--reality");
    expect(realitySample).toHaveAttribute("stroke", "#166534");
    expect(
      [...svg.querySelectorAll(".prediction-chart__range")].map((label) => label.textContent)
    ).toEqual(["50.57", "20"]);
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

    await waitFor(() =>
      expect(api.createPrediction).toHaveBeenCalledWith(
        "acme",
        expect.objectContaining({ modelKinds: allModelKinds })
      )
    );
    expect(api.preflightPredictions).toHaveBeenCalledWith(
      "acme",
      expect.objectContaining({ modelKinds: allModelKinds })
    );
  });

  it("sends only the remaining models in canonical order without invalidating preflight", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    await runPreflight();

    const models = screen.getByRole("group", { name: "Models" });
    for (const label of ["Seasonal naive", "Average", "MLForecast", "Prophet"]) {
      fireEvent.click(within(models).getByLabelText(label));
    }
    expect(within(models).getByText("2 selected", { selector: "summary" })).toBeInTheDocument();
    expect(screen.getByText("Preflight eligibility")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));

    await waitFor(() =>
      expect(api.createPrediction).toHaveBeenCalledWith(
        "acme",
        expect.objectContaining({
          modelKinds: ["naive", "sarima"],
          manualSeasonalPeriods: { revenue: 12 }
        })
      )
    );
    expect(api.preflightPredictions).toHaveBeenCalledTimes(1);
  });

  it("drops invalid manual periods but keeps valid ones when a request-field change clears preflight", async () => {
    api.preflightPredictions.mockResolvedValue({
      metrics: ["revenue", "cost"].map((metricId) => ({
        scenarioId: "future",
        metricId,
        status: "eligible",
        reason: null,
        seasonalPeriod: null,
        seasonalPeriodSource: null,
        requiresManualSeasonalPeriod: true
      }))
    });
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    await runPreflight();
    fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), {
      target: { value: "1" }
    });
    fireEvent.change(screen.getByLabelText("Manual seasonal period for cost"), {
      target: { value: "4" }
    });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-03-10" } });
    expect(screen.queryByText("Preflight eligibility")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await screen.findByText("Preflight eligibility");
    expect(api.preflightPredictions).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({ manualSeasonalPeriods: { cost: 4 } })
    );
    expect(screen.getByLabelText("Manual seasonal period for revenue")).toHaveValue(2);
    expect(screen.getByLabelText("Manual seasonal period for cost")).toHaveValue(4);
  });

  it.each(["1", "2.5"])(
    "drops an invalid manual period %s when a class change hides it",
    async (invalidPeriod) => {
      render(<PredictionsTab orgId="acme" />);
      await screen.findByText(/selected scenario's own data/i);
      await runPreflight();
      fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), {
        target: { value: invalidPeriod }
      });
      selectRequestModels(["Prophet"]);
      fireEvent.click(
        within(screen.getByRole("group", { name: "Models" })).getByLabelText("SARIMA")
      );

      fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
      expect(await screen.findByLabelText("Manual seasonal period for revenue")).toHaveValue(2);
      expect(api.preflightPredictions).toHaveBeenLastCalledWith(
        "acme",
        expect.objectContaining({ modelKinds: ["sarima", "prophet"], manualSeasonalPeriods: {} })
      );
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    }
  );

  it("disables the queue form fields while preflight is running", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    await runPreflight();
    let resolvePreflight!: (value: unknown) => void;
    api.preflightPredictions.mockReturnValueOnce(
      new Promise((resolve) => {
        resolvePreflight = resolve;
      })
    );
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));

    expect(queueFormFields()).toHaveLength(11);
    for (const field of queueFormFields()) expect(field).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run preflight" })).toBeDisabled();
    // The comparison filters are not part of the queue form.
    expect(
      within(screen.getByRole("group", { name: "Versions" })).getByLabelText("All saved versions")
    ).toBeEnabled();

    await act(async () =>
      resolvePreflight({
        metrics: [
          {
            scenarioId: "future",
            metricId: "revenue",
            status: "eligible",
            reason: null,
            seasonalPeriod: null,
            seasonalPeriodSource: null,
            requiresManualSeasonalPeriod: true
          }
        ]
      })
    );
    for (const field of queueFormFields()) expect(field).toBeEnabled();
  });

  it("disables the queue form fields while a prediction is being queued", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    await runPreflight();
    let resolveCreate!: (value: unknown) => void;
    api.createPrediction.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveCreate = resolve;
      })
    );
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));

    expect(queueFormFields()).toHaveLength(11);
    for (const field of queueFormFields()) expect(field).toBeDisabled();
    expect(screen.getByRole("button", { name: "Queue prediction" })).toBeDisabled();

    await act(async () =>
      resolveCreate({
        id: "request-2",
        name: "Created plan",
        state: "queued",
        submittedTime: "2026-01-01T12:00:00Z",
        startTime: null,
        finishTime: null,
        failureCode: null,
        failureReason: null,
        completedPredictionId: null
      })
    );
    for (const field of queueFormFields()) expect(field).toBeEnabled();
  });

  it("re-enables the queue form fields when preflight fails", async () => {
    api.preflightPredictions.mockRejectedValueOnce(new Error("Service unavailable"));
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    fireEvent.change(screen.getAllByLabelText("Start date")[0], {
      target: { value: "2026-01-10" }
    });
    fireEvent.change(screen.getAllByLabelText("End date")[0], { target: { value: "2026-02-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Preflight failed. Service unavailable"
    );
    expect(screen.getByLabelText("Version name")).toBeEnabled();
    expect(
      within(screen.getByRole("group", { name: "Models" })).getByLabelText("Prophet")
    ).toBeEnabled();
  });

  it("hides seasonal periods for a non-seasonal selection and still shows every status and reason", async () => {
    api.preflightPredictions.mockResolvedValue({
      metrics: [
        {
          scenarioId: "future",
          metricId: "revenue",
          status: "eligible",
          reason: null,
          seasonalPeriod: null,
          seasonalPeriodSource: null,
          requiresManualSeasonalPeriod: false
        },
        {
          // A stale automatic period must not be shown without a seasonal-period kind.
          scenarioId: "future",
          metricId: "cost",
          status: "eligible",
          reason: null,
          seasonalPeriod: 12,
          seasonalPeriodSource: "automatic",
          requiresManualSeasonalPeriod: false
        },
        {
          scenarioId: "reality",
          metricId: "revenue",
          status: "ineligible",
          reason: "Target scenario has no observations available under the selected cutoff.",
          seasonalPeriod: null,
          seasonalPeriodSource: null,
          requiresManualSeasonalPeriod: true
        }
      ]
    });
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    selectRequestModels(nonSeasonalLabels);
    await runPreflight();

    expect(api.preflightPredictions).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({ modelKinds: ["naive", "average", "mlforecast", "prophet"] })
    );
    expect(screen.queryByLabelText(/Manual seasonal period/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Automatic seasonal period/)).not.toBeInTheDocument();
    expect(screen.getByText("future · revenue")).toBeVisible();
    expect(screen.getByText("future · cost")).toBeVisible();
    expect(screen.getByText("reality · revenue")).toBeVisible();
    expect(screen.getAllByText("eligible")).toHaveLength(2);
    expect(
      screen.getByText(
        "ineligible — Target scenario has no observations available under the selected cutoff."
      )
    ).toBeVisible();
  });

  it.each([
    ["Seasonal naive", "seasonal_naive"],
    ["SARIMA", "sarima"]
  ])("shows the manual input and automatic period for %s alone", async (label, kind) => {
    api.preflightPredictions.mockResolvedValue({
      metrics: [
        {
          scenarioId: "future",
          metricId: "revenue",
          status: "eligible",
          reason: null,
          seasonalPeriod: null,
          seasonalPeriodSource: null,
          requiresManualSeasonalPeriod: true
        },
        {
          scenarioId: "future",
          metricId: "cost",
          status: "eligible",
          reason: null,
          seasonalPeriod: 12,
          seasonalPeriodSource: "automatic",
          requiresManualSeasonalPeriod: false
        }
      ]
    });
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    selectRequestModels([label]);
    await runPreflight();

    expect(screen.getByLabelText("Manual seasonal period for revenue")).toHaveValue(12);
    expect(screen.getByText("Automatic seasonal period: 12 (automatic)")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    await waitFor(() =>
      expect(api.createPrediction).toHaveBeenCalledWith(
        "acme",
        expect.objectContaining({ modelKinds: [kind], manualSeasonalPeriods: { revenue: 12 } })
      )
    );
  });

  it("invalidates preflight only when the selection changes between seasonal and non-seasonal", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    selectRequestModels(["Naive", "Prophet"]);
    await runPreflight();
    const models = screen.getByRole("group", { name: "Models" });

    fireEvent.click(within(models).getByLabelText("Average"));
    fireEvent.click(within(models).getByLabelText("Prophet"));
    expect(screen.getByText("Preflight eligibility")).toBeVisible();

    fireEvent.click(within(models).getByLabelText("SARIMA"));
    expect(screen.queryByText("Preflight eligibility")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Queue prediction" })).toBeDisabled();

    await runPreflight();
    fireEvent.click(within(models).getByLabelText("Seasonal naive"));
    fireEvent.click(within(models).getByLabelText("SARIMA"));
    expect(screen.getByText("Preflight eligibility")).toBeVisible();

    fireEvent.click(within(models).getByLabelText("Seasonal naive"));
    expect(screen.queryByText("Preflight eligibility")).not.toBeInTheDocument();
    expect(api.preflightPredictions).toHaveBeenCalledTimes(2);
  });

  it("sends no periods and does not require one without a seasonal-period kind, then restores them", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    await runPreflight();
    fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), {
      target: { value: "3" }
    });
    selectRequestModels(["Prophet"]);

    api.preflightPredictions.mockResolvedValueOnce({
      metrics: [
        {
          scenarioId: "future",
          metricId: "revenue",
          status: "eligible",
          reason: null,
          seasonalPeriod: null,
          seasonalPeriodSource: null,
          requiresManualSeasonalPeriod: false
        }
      ]
    });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await screen.findByText("Preflight eligibility");
    expect(api.preflightPredictions).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({ modelKinds: ["prophet"], manualSeasonalPeriods: {} })
    );
    expect(screen.queryByLabelText(/Manual seasonal period/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    await waitFor(() =>
      expect(api.createPrediction).toHaveBeenCalledWith(
        "acme",
        expect.objectContaining({ modelKinds: ["prophet"], manualSeasonalPeriods: {} })
      )
    );
    await waitFor(() =>
      expect(screen.queryByText("Preflight eligibility")).not.toBeInTheDocument()
    );

    fireEvent.click(within(screen.getByRole("group", { name: "Models" })).getByLabelText("SARIMA"));
    fireEvent.change(screen.getByLabelText("Version name"), { target: { value: "Second plan" } });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    expect(await screen.findByLabelText("Manual seasonal period for revenue")).toHaveValue(3);
    expect(api.preflightPredictions).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({
        modelKinds: ["sarima", "prophet"],
        manualSeasonalPeriods: { revenue: 3 }
      })
    );
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    await waitFor(() =>
      expect(api.createPrediction).toHaveBeenLastCalledWith(
        "acme",
        expect.objectContaining({
          modelKinds: ["sarima", "prophet"],
          manualSeasonalPeriods: { revenue: 3 }
        })
      )
    );
  });

  it("does not block creation on a hidden missing period", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    await runPreflight();
    fireEvent.change(screen.getByLabelText("Manual seasonal period for revenue"), {
      target: { value: "" }
    });
    selectRequestModels(["Naive"]);
    // The check follows the selection, even if a response still reports a required period.
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    await screen.findByText("Preflight eligibility");
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));

    await waitFor(() =>
      expect(api.createPrediction).toHaveBeenCalledWith(
        "acme",
        expect.objectContaining({ modelKinds: ["naive"], manualSeasonalPeriods: {} })
      )
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("blocks preflight and creation when no model is selected", async () => {
    render(<PredictionsTab orgId="acme" />);
    await screen.findByText(/selected scenario's own data/i);
    // An empty selection has no seasonal-period kind, so a non-seasonal preflight stays valid.
    selectRequestModels(["Average"]);
    await runPreflight();

    const models = screen.getByRole("group", { name: "Models" });
    fireEvent.click(within(models).getByLabelText("Average"));
    expect(
      within(models).getByText("No models selected", { selector: "summary" })
    ).toBeInTheDocument();
    expect(screen.getByText("Preflight eligibility")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Select at least one model.");
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Select at least one model.");

    expect(api.createPrediction).not.toHaveBeenCalled();
    expect(api.preflightPredictions).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notice" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Select at least one model.");
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
    for (const field of queueFormFields()) expect(field).toBeEnabled();
  });

  it("compares Prophet with its own interval band and shows each version's models", async () => {
    const prophetVersion: PredictionVersionDetailDto = {
      ...version,
      id: "version-2",
      name: "Prophet plan",
      modelConfiguration: { modelKinds: ["naive", "prophet"] },
      targets: [
        {
          ...version.targets[0],
          results: [
            version.targets[0].results[0],
            {
              ...version.targets[0].results[0],
              kind: "prophet",
              predictionIntervalStatus: "available",
              points: [
                { date: "2026-01-10", value: 31, lowerBound: 21, upperBound: 41 },
                { date: "2026-02-10", value: 35, lowerBound: 25, upperBound: 45 }
              ]
            }
          ]
        }
      ]
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
    const prophetLine = svg.querySelector(
      '[data-series-id="version-2:future:revenue:prophet"] path'
    );
    expect(prophetLine).toHaveAttribute("stroke-dasharray", "10 3 2 3");
    expect(container.querySelectorAll(".prediction-chart__interval-band")).toHaveLength(1);
    expect(
      within(svg).getByText("Prophet plan · Future plan · Prophet: saved 80% prediction interval.")
    ).toBeInTheDocument();
    expect(screen.queryByText(/No results to show for/)).not.toBeInTheDocument();

    const versions = screen.getByRole("group", { name: "Versions" });
    expect(
      within(versions).getByLabelText("Prophet plan (80% prediction interval)")
    ).toHaveAccessibleDescription("Models: Naive, Prophet");
    expect(
      within(versions).getByLabelText("January plan (80% prediction interval)")
    ).toHaveAccessibleDescription("Models: Naive, Seasonal naive");

    fireEvent.click(within(comparisonModels).getByLabelText("All models and baselines"));
    fireEvent.click(within(comparisonModels).getByLabelText("Seasonal naive"));
    expect(screen.getByText("Not run by the selected versions: Seasonal naive.")).toBeVisible();
    expect(screen.queryByText(/No results to show for/)).not.toBeInTheDocument();

    fireEvent.click(within(versions).getByLabelText("January plan (80% prediction interval)"));
    expect(screen.getByText("No results to show for: Seasonal naive.")).toBeVisible();
    expect(screen.queryByText(/Not run by the selected versions/)).not.toBeInTheDocument();
  });

  it.each(["unavailable", "not_applicable"] as const)(
    "draws no Prophet band when its interval is %s",
    async (intervalStatus) => {
      const prophetVersion: PredictionVersionDetailDto = {
        ...version,
        modelConfiguration: { modelKinds: ["prophet"] },
        targets: [
          {
            ...version.targets[0],
            results: [
              {
                ...version.targets[0].results[0],
                kind: "prophet",
                predictionIntervalStatus: intervalStatus,
                predictionIntervalReason:
                  intervalStatus === "unavailable"
                    ? "Prophet prediction interval is unavailable."
                    : null,
                points: [
                  { date: "2026-01-10", value: 31, lowerBound: 21, upperBound: 41 },
                  { date: "2026-02-10", value: 35, lowerBound: 25, upperBound: 45 }
                ]
              }
            ]
          }
        ]
      };
      api.fetchPredictions.mockResolvedValueOnce([prophetVersion]);
      api.fetchPrediction.mockResolvedValueOnce(prophetVersion);
      const { container } = render(<PredictionsTab orgId="acme" />);

      const svg = await screen.findByRole("img", { name: /Revenue prediction comparison chart/ });
      expect(
        svg.querySelector('[data-series-id="version-1:future:revenue:prophet"]')
      ).toBeInTheDocument();
      expect(container.querySelector(".prediction-chart__interval-band")).not.toBeInTheDocument();
    }
  );

  it("keeps deleted target scenarios available for saved-version comparison", async () => {
    api.fetchScenarios.mockResolvedValueOnce([
      { id: "reality", name: "Reality", description: "", protected: true }
    ]);
    render(<PredictionsTab orgId="acme" />);

    await screen.findByText(/selected scenario's own data/i);
    expect(
      within(screen.getAllByRole("group", { name: "Target scenarios" })[0]).getByLabelText(
        "Reality"
      )
    ).toBeChecked();
    const comparisonSelector = screen.getAllByRole("group", { name: "Target scenarios" })[1];
    expect(within(comparisonSelector).getByLabelText("Deleted scenario (future)")).toBeChecked();
    expect(
      screen.getByRole("img", { name: "Revenue prediction comparison chart in EUR" })
    ).toBeVisible();
  });

  it("keeps creation unavailable when preflight finds no forecastable metrics", async () => {
    api.preflightPredictions.mockResolvedValueOnce({ metrics: [] });
    render(<PredictionsTab orgId="acme" />);
    await screen.findAllByText(/January plan \(80% prediction interval\)/);

    fireEvent.change(screen.getAllByLabelText("Start date")[0], {
      target: { value: "2026-01-10" }
    });
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
    expect(
      await screen.findByText(
        "Select saved versions, scenarios, models and metrics with available numeric points to plot them."
      )
    ).toBeVisible();

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

  it.each([99, 100, 101])(
    "renders %i-point lines with independent marker thresholds and hover details",
    async (count) => {
      const points = Array.from({ length: count }, (_, index) => ({
        date: new Date(Date.UTC(2025, 11, 31 + index)).toISOString().slice(0, 10),
        value: index + 30,
        lowerBound: index + 20,
        upperBound: index + 40
      }));
      const dense = {
        ...version,
        startDate: points[0].date,
        endDate: points.at(-1)!.date,
        targets: [
          {
            ...version.targets[0],
            timeUnit: "day" as const,
            results: [
              {
                ...version.targets[0].results[0],
                kind: "mlforecast",
                predictionIntervalStatus: "available" as const,
                points
              },
              { ...version.targets[0].results[0], points: [points[0], points.at(-1)!] }
            ]
          }
        ]
      };
      api.fetchPredictions.mockResolvedValueOnce([dense]);
      api.fetchPrediction.mockResolvedValueOnce(dense);
      api.fetchTimeseries.mockResolvedValueOnce([
        {
          id: "revenue",
          name: "Revenue",
          unit: "EUR",
          valueUnit: "number",
          timeUnit: "day",
          values: points.map(({ date, value }) => ({ date, value: value - 1 }))
        }
      ]);
      const { container } = render(<PredictionsTab orgId="acme" />);
      const svg = await screen.findByRole("img", { name: /Revenue prediction comparison chart/ });
      const fitted = svg.querySelector('[data-series-id="version-1:future:revenue:mlforecast"]')!;
      const sparse = svg.querySelector('[data-series-id="version-1:future:revenue:naive"]')!;
      expect(fitted.querySelectorAll(".prediction-chart__point")).toHaveLength(
        count < 100 ? count : 0
      );
      expect(fitted.querySelectorAll(".prediction-chart__point-hit-target")).toHaveLength(
        count >= 100 ? count : 0
      );
      expect(sparse.querySelectorAll(".prediction-chart__point")).toHaveLength(2);
      expect(fitted.querySelector("path")?.getAttribute("d")?.match(/[ML]/g)).toHaveLength(count);
      expect(fitted.querySelector("circle")).toHaveAttribute("cx", "56");
      expect(fitted.querySelector("circle")?.getAttribute("fill")).toBe(
        count >= 100 ? "transparent" : "#c94a11"
      );
      // The sparse naive line has the same first point without an interval.
      expect(fitted.querySelector("circle title")?.textContent).toBe(
        [
          "30 EUR, lower bound 20 EUR, upper bound 40 EUR (80% prediction interval)",
          "January plan · Future plan · MLForecast",
          "January plan · Future plan · Naive (no prediction interval)",
          "2025-12-31"
        ].join("\n")
      );
      const band = svg.querySelector(".prediction-chart__interval-band")!;
      expect(band.compareDocumentPosition(fitted) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(svg.querySelector(".prediction-chart__unit")).toHaveTextContent("EUR");
      expect(container.querySelector(".prediction-chart > header")).not.toHaveTextContent("EUR");
      const labels = svg.querySelectorAll(".prediction-chart__date");
      expect(labels.length).toBeLessThanOrEqual(22);
      expect(labels[0]).toHaveTextContent("12-31");
      expect(labels[labels.length - 1]).toHaveTextContent(points.at(-1)!.date.slice(5));
      expect(svg.querySelectorAll(".prediction-chart__year-boundary")).toHaveLength(1);
      expect(svg.querySelectorAll(".prediction-chart__year")).toHaveLength(1);

      fireEvent.click(screen.getByLabelText(/Include current Reality/));
      await waitFor(() =>
        expect(svg.querySelector('[data-series-id="reality:revenue"]')).toBeInTheDocument()
      );
      const reality = svg.querySelector('[data-series-id="reality:revenue"]')!;
      expect(reality.querySelectorAll(".prediction-chart__point")).toHaveLength(
        count < 100 ? count : 0
      );
      expect(reality.querySelectorAll(".prediction-chart__point-hit-target")).toHaveLength(
        count >= 100 ? count : 0
      );
      fireEvent.change(screen.getByLabelText("Plot end date"), {
        target: { value: points[1].date }
      });
      expect(fitted.querySelectorAll(".prediction-chart__point")).toHaveLength(2);
      expect(reality.querySelectorAll(".prediction-chart__point")).toHaveLength(2);
      expect(sparse.querySelectorAll(".prediction-chart__point")).toHaveLength(1);
    }
  );

  it("plots overlapping Reality observations despite extra dates and removes the layer when unchecked", async () => {
    api.fetchTimeseries.mockResolvedValueOnce([
      {
        id: "revenue",
        name: "Revenue",
        unit: "EUR",
        valueUnit: "number",
        timeUnit: "day",
        values: [
          { date: "2025-01-01", value: -100 },
          { date: "2026-01-10", value: 28 },
          { date: "2026-02-10", value: 32 },
          { date: "2027-01-01", value: 1000 }
        ]
      }
    ]);
    render(<PredictionsTab orgId="acme" />);
    const svg = await screen.findByRole("img", { name: /Revenue prediction comparison chart/ });
    const toggle = screen.getByLabelText(/Include current Reality/);
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(svg.querySelector(".prediction-chart__line--reality")).toBeInTheDocument()
    );
    expect(svg.querySelector(".prediction-chart__line--reality")).toHaveAttribute(
      "d",
      "M56 226 L702 100.66666666666667"
    );
    const dots = svg.querySelectorAll('[data-series-id="reality:revenue"] circle');
    expect(dots).toHaveLength(2);
    expect(dots[0]).toHaveAttribute("cx", "56");
    expect(dots[1]).toHaveAttribute("cx", "702");
    expect(svg.textContent).not.toContain("-100 EUR");
    expect(svg.textContent).not.toContain("1000 EUR");
    fireEvent.change(screen.getByLabelText("Plot start date"), { target: { value: "2025-01-01" } });
    expect(svg.querySelectorAll('[data-series-id="reality:revenue"] circle')).toHaveLength(3);
    fireEvent.click(toggle);
    expect(svg.querySelector(".prediction-chart__line--reality")).not.toBeInTheDocument();
    expect(svg.textContent).not.toContain("Current Reality");
  });

  it("shows Reality empty feedback only after a successful load and clears errors on retry", async () => {
    let resolve!: (value: unknown[]) => void;
    api.fetchTimeseries.mockReturnValueOnce(
      new Promise((done) => {
        resolve = done;
      })
    );
    render(<PredictionsTab orgId="acme" />);
    await screen.findByRole("img", { name: /Revenue prediction comparison chart/ });
    const toggle = screen.getByLabelText(/Include current Reality/);
    fireEvent.click(toggle);
    expect(screen.getByText("Loading current Reality data…")).toBeVisible();
    expect(screen.queryByText(/No matching numeric current Reality/)).not.toBeInTheDocument();
    await act(async () => resolve([]));
    expect(screen.getByText(/No matching numeric current Reality/)).toBeVisible();
    fireEvent.click(toggle);
    api.fetchTimeseries.mockRejectedValueOnce(new Error("Unavailable"));
    fireEvent.click(toggle);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load current Reality data. Unavailable"
    );
    expect(screen.queryByText(/No matching numeric current Reality/)).not.toBeInTheDocument();
    fireEvent.click(toggle);
    api.fetchTimeseries.mockResolvedValueOnce([
      {
        id: "revenue",
        name: "Revenue",
        valueUnit: "number",
        values: [{ date: "2025-01-01", value: 1 }]
      }
    ]);
    fireEvent.click(toggle);
    expect(
      await screen.findByText("No current Reality observations in the displayed period.")
    ).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("ignores a cancelled Reality response after a newer request succeeds", async () => {
    let resolve!: (value: unknown[]) => void;
    api.fetchTimeseries.mockReturnValueOnce(
      new Promise((done) => {
        resolve = done;
      })
    );
    render(<PredictionsTab orgId="acme" />);
    const svg = await screen.findByRole("img", { name: /Revenue prediction comparison chart/ });
    const toggle = screen.getByLabelText(/Include current Reality/);
    fireEvent.click(toggle);
    const signal = api.fetchTimeseries.mock.calls[0][2] as AbortSignal;
    fireEvent.click(toggle);
    expect(signal.aborted).toBe(true);
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(svg.querySelector(".prediction-chart__line--reality")).toBeInTheDocument()
    );
    await act(async () => resolve([]));
    expect(svg.querySelector(".prediction-chart__line--reality")).toBeInTheDocument();
    expect(screen.queryByText(/No matching numeric current Reality/)).not.toBeInTheDocument();
  });
});
