import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    fireEvent.click(screen.getByRole("button", { name: "Create immutable version" }));

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
    expect(screen.getByRole("button", { name: "Create immutable version" })).toBeEnabled();

    fireEvent.change(confidenceLevel, { target: { value: "90" } });
    expect(screen.getByRole("button", { name: "Create immutable version" })).toBeDisabled();
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

    expect(await screen.findByLabelText("seasonal naive")).toBeChecked();
    expect(screen.getByText("No results to show for: seasonal naive.")).toBeVisible();
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
