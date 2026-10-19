import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  PredictionRequestSummaryDto,
  PredictionVersionDetailDto
} from "../../api/predictions";
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
  cancelPredictionRequest: vi.fn()
}));
vi.mock("../../api/scenarios", () => ({ fetchScenarios: api.fetchScenarios }));
vi.mock("../../api/events", () => ({ fetchEvents: api.fetchEvents }));
vi.mock("../../api/predictions", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/predictions")>()),
  ...api
}));

const now = "2026-09-10T12:00:59Z";
function request(
  id: string,
  overrides: Partial<PredictionRequestSummaryDto> = {}
): PredictionRequestSummaryDto {
  return {
    id,
    name: `Plan ${id}`,
    state: "queued",
    submittedTime: "2026-09-10T12:00:00Z",
    startTime: null,
    finishTime: null,
    failureCode: null,
    failureReason: null,
    completedPredictionId: null,
    ...overrides
  };
}
function saved(id: string): PredictionVersionDetailDto {
  return {
    id,
    name: `Saved ${id}`,
    startDate: "2026-09-10",
    endDate: "2026-10-10",
    cutoffMode: "asOfStart",
    confidenceLevel: 80,
    createdTime: now,
    modelConfiguration: {},
    targets: []
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
async function mount(orgId = "acme") {
  const view = render(<PredictionsTab orgId={orgId} />);
  await act(async () => {});
  return view;
}
async function poll() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
}
async function submit(id: string) {
  const queued = request(id);
  api.createPrediction.mockResolvedValueOnce(queued);
  fireEvent.change(screen.getByLabelText("Version name"), { target: { value: queued.name } });
  const form = screen.getByRole("region", { name: "Queue a prediction" });
  fireEvent.change(within(form).getByLabelText("Start date"), { target: { value: "2026-09-10" } });
  fireEvent.change(within(form).getByLabelText("End date"), { target: { value: "2026-10-10" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Queue prediction" }));
  });
  return queued;
}
function notice(id: string) {
  return screen.getByRole("button", { name: `Dismiss prediction request “Plan ${id}” notice` })
    .parentElement!;
}
function card(id: string) {
  return screen.getByRole("heading", { name: `Plan ${id}` }).closest("article")!;
}
function metadata(id: string, label: string) {
  return within(card(id)).getByText(label, { selector: "dt" }).nextElementSibling!;
}

describe("prediction request list follow-up", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date(now));
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    api.fetchScenarios.mockResolvedValue([{ id: "future", name: "Future", protected: false }]);
    api.fetchEvents.mockResolvedValue([]);
    api.fetchPredictions.mockResolvedValue([saved("existing")]);
    api.fetchPrediction.mockImplementation((_org: string, id: string) =>
      Promise.resolve(saved(id))
    );
    api.fetchPredictionRequests.mockResolvedValue([]);
    api.preflightPredictions.mockResolvedValue({
      metrics: [
        {
          scenarioId: "future",
          metricId: "metric",
          status: "eligible",
          requiresManualSeasonalPeriod: false
        }
      ]
    });
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it.each([0, 1, 2, 3])("shows %i history records without a disclosure", async (count) => {
    api.fetchPredictionRequests.mockResolvedValue(
      Array.from({ length: count }, (_, i) =>
        request(`${i}`, { state: "cancelled", finishTime: now })
      )
    );
    await mount();
    const history = screen.getByRole("region", { name: "Recent history" });
    expect(within(history).queryAllByRole("article")).toHaveLength(count);
    expect(screen.queryByRole("button", { name: /Show more|Show less/ })).not.toBeInTheDocument();
  });

  it("preserves all active actions and server history order through disclosure, polls, and organisation reset", async () => {
    const history = Array.from({ length: 50 }, (_, i) =>
      request(`history-${i}`, { state: "cancelled", finishTime: now })
    );
    const active = [
      request("later", { submittedTime: now }),
      request("earlier"),
      request("running", { state: "running" }),
      request("stopping", { state: "cancelling" })
    ];
    api.fetchPredictionRequests.mockResolvedValue([...active, ...history]);
    const view = await mount();
    const recent = screen.getByRole("region", { name: "Recent history" });
    const work = screen.getByRole("region", { name: "Active work" });
    expect(
      within(work)
        .getAllByRole("heading", { level: 4 })
        .map((item) => item.textContent)
    ).toEqual(["Plan earlier", "Plan running", "Plan stopping", "Plan later"]);
    expect(within(work).getAllByRole("button", { name: "Remove from queue" })).toHaveLength(2);
    expect(within(work).getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(within(card("stopping")).queryByRole("button")).not.toBeInTheDocument();
    expect(within(recent).getAllByRole("article")).toHaveLength(3);
    const disclosure = within(recent).getByRole("button", { name: "Show more" });
    expect(disclosure).toHaveAttribute("aria-expanded", "false");
    expect(document.getElementById(disclosure.getAttribute("aria-controls")!)).toContainElement(
      card("history-0")
    );
    fireEvent.click(disclosure);
    expect(disclosure).toHaveAttribute("aria-expanded", "true");
    await poll();
    expect(
      within(recent)
        .getAllByRole("heading", { level: 4 })
        .map((item) => item.textContent)
    ).toEqual(history.map((item) => item.name));
    fireEvent.click(within(recent).getByRole("button", { name: "Show less" }));
    expect(within(recent).getAllByRole("article")).toHaveLength(3);
    fireEvent.click(disclosure);
    await act(async () => {
      view.rerender(<PredictionsTab orgId="other" />);
    });
    expect(screen.getByRole("button", { name: "Show more" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
  });

  it("labels semantic local timestamps and durations on every lifecycle state and refreshes ongoing minutes", async () => {
    api.fetchPredictionRequests.mockResolvedValue([
      request("queued"),
      request("running", { state: "running", startTime: "2026-09-10T12:00:20Z" }),
      request("cancelling", { state: "cancelling", startTime: "2026-09-10T12:00:20Z" }),
      ...(["completed", "failed", "cancelled"] as const).map((state) =>
        request(state, {
          state,
          finishTime: now,
          startTime: state === "cancelled" ? null : "2026-09-10T12:00:20Z"
        })
      )
    ]);
    await mount();
    for (const id of ["queued", "running", "cancelling", "completed", "failed", "cancelled"]) {
      expect(metadata(id, "Queued").querySelector("time")).toHaveAttribute(
        "datetime",
        request(id).submittedTime
      );
      const local = new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit"
      });
      for (const time of card(id).querySelectorAll("time")) {
        expect(time.textContent).toBe(local.format(new Date(time.dateTime)));
      }
      expect(metadata(id, "Queue duration")).toHaveTextContent("<1 min");
      expect(metadata(id, "Processing duration")).toHaveTextContent(
        id === "queued" || id === "cancelled" ? "Not started" : "<1 min"
      );
      expect(metadata(id, "Processing started")).toHaveTextContent(
        id === "queued" || id === "cancelled"
          ? "Not started"
          : local.format(new Date("2026-09-10T12:00:20Z"))
      );
      expect(metadata(id, "Finished")).toHaveTextContent(
        ["queued", "running", "cancelling"].includes(id)
          ? "Not finished"
          : local.format(new Date(now))
      );
    }
    await poll();
    expect(metadata("queued", "Queue duration").textContent).toBe("1 min");
    expect(metadata("cancelled", "Queue duration").textContent).toBe("<1 min");
  });

  it("keeps newest-first independent notices, announces terminal transitions once, and ignores discovered requests", async () => {
    await mount();
    const a = await submit("a");
    const b = await submit("b");
    const c = await submit("c");
    const notices = screen.getAllByRole("button", { name: /Dismiss prediction request/ });
    expect(notices.map((item) => item.getAttribute("aria-label"))).toEqual(
      ["c", "b", "a"].map((id) => `Dismiss prediction request “Plan ${id}” notice`)
    );
    const aNotice = notice("a");
    const changed = vi.fn();
    const observer = new MutationObserver(changed);
    observer.observe(aNotice, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true
    });
    api.fetchPredictionRequests.mockResolvedValue([
      { ...a, state: "running" },
      { ...b, state: "cancelling" },
      c,
      request("someone-else")
    ]);
    await poll();
    expect(changed).not.toHaveBeenCalled();
    expect(aNotice).toHaveTextContent("Prediction request “Plan a” was accepted and queued.");
    expect(notice("b")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("button", { name: /Dismiss.*someone-else/ })).not.toBeInTheDocument();
    api.fetchPredictionRequests.mockResolvedValue([
      { ...a, state: "completed", finishTime: now },
      { ...b, state: "cancelled", finishTime: now },
      {
        ...c,
        state: "failed",
        finishTime: now,
        failureReason: "Calculation could not finish. <script>safe text</script>"
      }
    ]);
    await poll();
    expect(aNotice).toHaveTextContent("Prediction request “Plan a” completed.");
    expect(notice("b")).toHaveTextContent("Prediction request “Plan b” was cancelled.");
    expect(notice("c")).toHaveAttribute("role", "alert");
    expect(notice("c")).toHaveClass("alert--danger");
    expect(notice("c")).toHaveTextContent(
      "Prediction request “Plan c” failed. Calculation could not finish. <script>safe text</script>"
    );
    expect(notice("c").querySelector("script")).toBeNull();
    changed.mockClear();
    await poll();
    expect(changed).not.toHaveBeenCalled();
    observer.disconnect();
    fireEvent.click(within(notice("b")).getByRole("button"));
    expect(screen.getAllByRole("button", { name: /Dismiss prediction request/ })).toHaveLength(2);
  });

  it("resolves a dismissed submission missing from the capped list and selects its saved result without resetting comparisons", async () => {
    await mount();
    const a = await submit("a");
    fireEvent.click(within(notice("a")).getByRole("button"));
    api.fetchPredictionRequests.mockResolvedValue(
      Array.from({ length: 50 }, (_, i) =>
        request(`other-${i}`, { state: "cancelled", finishTime: now })
      )
    );
    api.fetchPredictionRequest.mockResolvedValue({
      ...a,
      state: "completed",
      finishTime: now,
      completedPredictionId: "new"
    });
    api.fetchPredictions.mockResolvedValue([saved("new"), saved("existing")]);
    await poll();
    expect(api.fetchPredictionRequest).toHaveBeenCalledWith("acme", "a", expect.any(AbortSignal));
    const versions = screen.getByRole("group", { name: "Versions" });
    expect(
      within(versions).getByLabelText("Saved existing (80% prediction interval)")
    ).toBeChecked();
    expect(within(versions).getByLabelText("Saved new (80% prediction interval)")).toBeChecked();
    expect(
      screen.queryByRole("button", { name: /Dismiss prediction request/ })
    ).not.toBeInTheDocument();
    const calls = api.fetchPrediction.mock.calls.length;
    await poll();
    expect(api.fetchPredictionRequest).toHaveBeenCalledTimes(1);
    expect(api.fetchPrediction).toHaveBeenCalledTimes(calls);
    fireEvent.click(within(versions).getByLabelText("Saved new (80% prediction interval)"));
    api.fetchPredictionRequests.mockResolvedValue([
      request("someone-else", {
        state: "completed",
        completedPredictionId: "other",
        finishTime: now
      })
    ]);
    api.fetchPredictions.mockResolvedValue([saved("other"), saved("new"), saved("existing")]);
    await poll();
    expect(
      within(versions).getByLabelText("Saved new (80% prediction interval)")
    ).not.toBeChecked();
    expect(
      within(versions).getByLabelText("Saved other (80% prediction interval)")
    ).not.toBeChecked();
    expect(
      within(versions).getByLabelText("Saved existing (80% prediction interval)")
    ).toBeChecked();
  });

  it.each(["cancelled", "completed", "failed", "cancelling"] as const)(
    "updates a local notice from a %s cancellation response",
    async (state) => {
      await mount();
      const a = await submit("a");
      api.cancelPredictionRequest.mockResolvedValue({
        ...a,
        state,
        finishTime: state === "cancelling" ? null : now
      });
      api.fetchPredictionRequest.mockResolvedValue({ ...a, state });
      await act(async () => {
        fireEvent.click(within(card("a")).getByRole("button"));
      });
      const expected = {
        cancelled: "was cancelled.",
        completed: "completed.",
        failed: "failed.",
        cancelling: "was accepted and queued."
      }[state];
      expect(notice("a")).toHaveTextContent(`Prediction request “Plan a” ${expected}`);
      expect(notice("a")).toHaveAttribute("role", state === "failed" ? "alert" : "status");
      await poll();
      expect(api.fetchPredictionRequest).toHaveBeenCalledTimes(state === "cancelling" ? 1 : 0);
    }
  );

  it("retries saved-version refresh after an omitted request has resolved to completed", async () => {
    await mount();
    const a = await submit("a");
    api.fetchPredictionRequest.mockResolvedValue({
      ...a,
      state: "completed",
      completedPredictionId: "new",
      finishTime: now
    });
    api.fetchPredictions.mockRejectedValueOnce(new Error("Temporarily unavailable"));
    await poll();
    expect(notice("a")).toHaveTextContent("Prediction request “Plan a” completed.");
    api.fetchPredictions.mockResolvedValue([saved("new"), saved("existing")]);
    await poll();
    expect(screen.getByLabelText("Saved new (80% prediction interval)")).toBeChecked();
    expect(api.fetchPredictionRequest).toHaveBeenCalledTimes(1);
  });

  it("does not overlap detail polling, recovers from detail errors, and retains missing active work", async () => {
    await mount();
    const a = await submit("a");
    const detail = deferred<PredictionRequestSummaryDto>();
    api.fetchPredictionRequest.mockReturnValueOnce(detail.promise);
    await poll();
    const calls = api.fetchPredictionRequests.mock.calls.length;
    await poll();
    expect(api.fetchPredictionRequests).toHaveBeenCalledTimes(calls);
    await act(async () => {
      detail.reject(new Error("Unavailable"));
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Could not refresh prediction requests. Unavailable"
    );
    api.fetchPredictionRequest.mockResolvedValue({ ...a, state: "running", startTime: now });
    await poll();
    expect(within(card("a")).getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("clears notices on organisation change and remount, ignoring old detail responses", async () => {
    const view = await mount();
    const a = await submit("a");
    const detail = deferred<PredictionRequestSummaryDto>();
    api.fetchPredictionRequest.mockReturnValueOnce(detail.promise);
    await poll();
    const signal = api.fetchPredictionRequest.mock.calls[0][2] as AbortSignal;
    await act(async () => {
      view.rerender(<PredictionsTab orgId="other" />);
    });
    expect(signal.aborted).toBe(true);
    await act(async () => {
      detail.resolve({ ...a, state: "completed", completedPredictionId: "stale" });
    });
    expect(
      screen.queryByRole("button", { name: /Dismiss prediction request/ })
    ).not.toBeInTheDocument();
    expect(api.fetchPrediction).not.toHaveBeenCalledWith("other", "stale", expect.anything());
    await submit("b");
    view.unmount();
    await mount("other");
    expect(
      screen.queryByRole("button", { name: /Dismiss prediction request/ })
    ).not.toBeInTheDocument();
  });

  it("refreshes other resolved completions even when one omitted request detail fails", async () => {
    await mount();
    await submit("a");
    const b = await submit("b");
    api.fetchPredictionRequest
      .mockRejectedValueOnce(new Error("Unavailable"))
      .mockResolvedValueOnce({
        ...b,
        state: "completed",
        completedPredictionId: "new",
        finishTime: now
      });
    api.fetchPredictions.mockResolvedValue([saved("new"), saved("existing")]);
    await poll();
    expect(within(card("a")).getByRole("button", { name: "Remove from queue" })).toBeEnabled();
    expect(notice("a")).toHaveTextContent("was accepted and queued.");
    expect(notice("b")).toHaveTextContent("Prediction request “Plan b” completed.");
    expect(screen.getByLabelText("Saved new (80% prediction interval)")).toBeChecked();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Could not refresh prediction requests. Unavailable"
    );
  });

  it("ignores stale detail responses after cancellation and preserves dismissal through the transition", async () => {
    await mount();
    const a = await submit("a");
    const list = deferred<PredictionRequestSummaryDto[]>();
    api.fetchPredictionRequests.mockReturnValueOnce(list.promise);
    await poll();
    const cancellation = deferred<PredictionRequestSummaryDto>();
    api.cancelPredictionRequest.mockReturnValueOnce(cancellation.promise);
    fireEvent.click(within(card("a")).getByRole("button"));
    expect(within(card("a")).getByRole("button")).toBeDisabled();
    fireEvent.click(within(notice("a")).getByRole("button"));
    await act(async () => {
      list.resolve([]);
    });
    const detail = deferred<PredictionRequestSummaryDto>();
    api.fetchPredictionRequest.mockReturnValueOnce(detail.promise);
    await poll();
    await act(async () => {
      cancellation.resolve({ ...a, state: "cancelled", finishTime: now });
    });
    await act(async () => {
      detail.resolve({ ...a, state: "running" });
    });
    expect(within(card("a")).getByText("Cancelled")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Dismiss prediction request/ })
    ).not.toBeInTheDocument();
  });

  it("aborts hidden detail fetches, resumes when visible and stops on unmount", async () => {
    const view = await mount();
    const a = await submit("a");
    const detail = deferred<PredictionRequestSummaryDto>();
    api.fetchPredictionRequest.mockReturnValueOnce(detail.promise);
    await poll();
    const signal = api.fetchPredictionRequest.mock.calls[0][2] as AbortSignal;
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    fireEvent(document, new Event("visibilitychange"));
    expect(signal.aborted).toBe(true);
    await act(async () => {
      detail.resolve({ ...a, state: "failed" });
    });
    expect(notice("a")).toHaveTextContent("was accepted and queued.");
    const calls = api.fetchPredictionRequests.mock.calls.length;
    await poll();
    expect(api.fetchPredictionRequests).toHaveBeenCalledTimes(calls);
    api.fetchPredictionRequests.mockResolvedValue([a]);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    await act(async () => {
      fireEvent(document, new Event("visibilitychange"));
    });
    expect(api.fetchPredictionRequests).toHaveBeenCalledTimes(calls + 1);
    view.unmount();
    await poll();
    expect(api.fetchPredictionRequests).toHaveBeenCalledTimes(calls + 1);
    expect(api.cancelPredictionRequest).not.toHaveBeenCalled();
  });
});
