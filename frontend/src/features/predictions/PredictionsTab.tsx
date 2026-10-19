import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import { fetchEvents } from "../../api/events";
import type { EventDto } from "../../api/events";
import {
  cancelPredictionRequest,
  createPrediction,
  fetchPrediction,
  fetchPredictionRequest,
  fetchPredictionRequests,
  fetchPredictions,
  MODEL_KINDS,
  preflightPredictions,
  selectionUsesSeasonalPeriod,
  type PredictionCutoffMode,
  type PredictionPreflightDto,
  type PredictionPreflightMetricDto,
  type PredictionRequestSummaryDto,
  type PredictionTargetDto,
  type PredictionVersionDetailDto
} from "../../api/predictions";
import { fetchScenarios } from "../../api/scenarios";
import type { ScenarioDto } from "../../api/scenarios";
import { fetchTimeseries } from "../../api/timeseries";
import type { TimeserieDto } from "../../api/timeseries";
import {
  buildPredictionMetricCharts,
  formatModelKind,
  formatPredictionPointValue,
  predictionChartAxisTicks,
  predictionIntervalBandPath,
  predictionPointTitles,
  predictionVersionModelKinds,
  sortModelKinds,
  type PredictionChartLine
} from "./predictionChart";
import {
  formatRequestTimestamp,
  isTerminalRequest,
  requestDurations,
  requestNoticeMessage
} from "./predictionRequestPresentation";

type EventOption = EventDto & {
  selectionId: string;
  scenarioId: string;
  scenarioName: string;
};

const lineColors = ["#c94a11", "#2563eb", "#8b5cf6", "#0f766e", "#b45309", "#be185d"];
const NON_NUMERIC_METRIC_REASON = "Only numeric metrics can be forecast.";
const DEFAULT_CONFIDENCE_LEVEL = "80";
const REQUEST_POLL_INTERVAL_MS = 2_000;

const requestStateLabels = {
  queued: "Queued",
  running: "Calculating prediction values",
  cancelling: "Stopping",
  completed: "Completed",
  cancelled: "Cancelled",
  failed: "Failed"
} as const;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function inputDate(event: EventOption | undefined): string {
  return event?.targetDate ?? "";
}

function isNumericPredictionTarget(target: PredictionTargetDto): boolean {
  // TASK-041B identifies non-numeric targets with this stable eligibility reason.
  // Other ineligible numeric metrics remain selectable so their missing results
  // can be communicated in the chart.
  return target.reason !== NON_NUMERIC_METRIC_REASON;
}

// A metric keeps its manual period after preflight reports it as the source,
// so later requests from this tab still send it.
function usesManualSeasonalPeriod(metric: PredictionPreflightMetricDto): boolean {
  return metric.requiresManualSeasonalPeriod || metric.seasonalPeriodSource === "manual";
}

// The backend rejects any other period, so a kept one would fail every later request.
function isValidManualSeasonalPeriod(value: number): boolean {
  return Number.isInteger(value) && value >= 2;
}

function toggleSet(set: Set<string>, value: string): Set<string> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export default function PredictionsTab(props: { orgId: string }) {
  return <PredictionsWorkspace key={props.orgId} orgId={props.orgId} />;
}

function PredictionsWorkspace(props: { orgId: string }) {
  const [scenarios, setScenarios] = useState<ScenarioDto[]>([]);
  const [events, setEvents] = useState<EventOption[]>([]);
  const [versions, setVersions] = useState<PredictionVersionDetailDto[]>([]);
  const [predictionRequests, setPredictionRequests] = useState<PredictionRequestSummaryDto[]>([]);
  const [requestLoading, setRequestLoading] = useState(true);
  const [requestRefreshError, setRequestRefreshError] = useState("");
  const [cancellingRequestIds, setCancellingRequestIds] = useState<Set<string>>(new Set());
  const [requestActionError, setRequestActionError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [name, setName] = useState("");
  const [targetScenarioIds, setTargetScenarioIds] = useState<Set<string>>(new Set());
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [startEventId, setStartEventId] = useState("");
  const [endEventId, setEndEventId] = useState("");
  const [cutoffMode, setCutoffMode] = useState<PredictionCutoffMode>("asOfStart");
  const [confidenceLevel, setConfidenceLevel] = useState(DEFAULT_CONFIDENCE_LEVEL);
  const [confidenceLevelError, setConfidenceLevelError] = useState("");
  const [preflight, setPreflight] = useState<PredictionPreflightDto | null>(null);
  const [manualPeriods, setManualPeriods] = useState<Record<string, number>>({});
  const [requestModelKinds, setRequestModelKinds] = useState<Set<string>>(
    () => new Set(MODEL_KINDS)
  );
  const [formError, setFormError] = useState("");
  const [submissionNotices, setSubmissionNotices] = useState<PredictionRequestSummaryDto[]>([]);
  const [requestNow, setRequestNow] = useState(() => Date.now());
  // Also disables the queue form's fields, so a response always matches the form.
  const [submitting, setSubmitting] = useState(false);
  const [selectedVersionIds, setSelectedVersionIds] = useState<Set<string>>(new Set());
  const [selectedScenarioFilter, setSelectedScenarioFilter] = useState<Set<string>>(new Set());
  const [selectedModelKinds, setSelectedModelKinds] = useState<Set<string>>(new Set());
  const [selectedMetricIds, setSelectedMetricIds] = useState<Set<string>>(new Set());
  const [plotStartDate, setPlotStartDate] = useState("");
  const [plotEndDate, setPlotEndDate] = useState("");
  const [includeReality, setIncludeReality] = useState(false);
  const [realityResult, setRealityResult] = useState<{
    orgId: string;
    scenarioId: string;
    timeseries: TimeserieDto[];
    error: string;
  } | null>(null);
  const versionsRef = useRef<PredictionVersionDetailDto[]>([]);
  const submittedRequestIdsRef = useRef(new Set<string>());
  // Tracking outlives notice dismissal so completion still selects saved output.
  const trackedRequestsRef = useRef(new Map<string, PredictionRequestSummaryDto>());
  const completedVersionFetchesRef = useRef(new Set<string>());
  const processedCompletedRequestIdsRef = useRef(new Set<string>());
  const requestMutationEpochRef = useRef(0);
  const initialWorkspaceLoadedRef = useRef(false);
  const currentOrgIdRef = useRef<string | null>(props.orgId);

  useLayoutEffect(() => {
    currentOrgIdRef.current = props.orgId;
    return () => {
      currentOrgIdRef.current = null;
    };
  }, [props.orgId]);

  const updateTrackedRequests = useCallback((requests: PredictionRequestSummaryDto[]) => {
    for (const request of requests) {
      if (trackedRequestsRef.current.has(request.id)) {
        trackedRequestsRef.current.set(request.id, request);
      }
    }
    setSubmissionNotices((current) => {
      const byId = new Map(requests.map((request) => [request.id, request]));
      let changed = false;
      const next = current.map((notice) => {
        const updated = byId.get(notice.id);
        if (!isTerminalRequest(notice) && updated && isTerminalRequest(updated)) {
          changed = true;
          return updated;
        }
        return notice;
      });
      return changed ? next : current;
    });
  }, []);

  useEffect(() => {
    versionsRef.current = versions;
  }, [versions]);

  useEffect(() => {
    submittedRequestIdsRef.current = new Set();
    completedVersionFetchesRef.current = new Set();
    processedCompletedRequestIdsRef.current = new Set();
    requestMutationEpochRef.current += 1;
    initialWorkspaceLoadedRef.current = false;
  }, [props.orgId]);

  const targetScenarios = useMemo(() => scenarios, [scenarios]);
  const comparisonScenarios = useMemo(() => {
    const names = new Map(scenarios.map((scenario) => [scenario.id, scenario.name]));
    for (const version of versions)
      for (const target of version.targets) {
        if (!names.has(target.scenarioId)) {
          names.set(target.scenarioId, `Deleted scenario (${target.scenarioId})`);
        }
      }
    return [...names.entries()].sort((left, right) => left[1].localeCompare(right[1]));
  }, [scenarios, versions]);
  const realityScenario = useMemo(
    () => scenarios.find((scenario) => scenario.protected || scenario.id === "reality"),
    [scenarios]
  );
  const currentReality =
    includeReality &&
    realityResult?.orgId === props.orgId &&
    realityResult.scenarioId === realityScenario?.id
      ? realityResult
      : null;
  const scenarioNames = useMemo(() => new Map(comparisonScenarios), [comparisonScenarios]);
  const eventById = useMemo(
    () => new Map(events.map((event) => [event.selectionId, event])),
    [events]
  );
  const availableStartEvents = useMemo(
    () => events.filter((event) => !endDate || event.targetDate < endDate),
    [endDate, events]
  );
  const availableEndEvents = useMemo(
    () => events.filter((event) => !startDate || event.targetDate > startDate),
    [events, startDate]
  );
  const invalidDates = Boolean(startDate && endDate && startDate >= endDate);
  // A shown preflight always matches this, because a change of it invalidates preflight.
  const seasonalPeriodSelected = selectionUsesSeasonalPeriod(requestModelKinds);
  // Periods entered for other selections stay in the tab but are not sent.
  const sentManualPeriods = seasonalPeriodSelected ? manualPeriods : {};

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    void (async () => {
      try {
        setLoading(true);
        setError("");
        const loadedScenarios = await fetchScenarios(props.orgId, controller.signal);
        const eventLists = await Promise.all(
          loadedScenarios.map(async (scenario) => ({
            scenario,
            items: await fetchEvents(props.orgId, scenario.id, controller.signal)
          }))
        );
        const versionSummaries = await fetchPredictions(props.orgId, controller.signal);
        const details = await Promise.all(
          versionSummaries.map((version) =>
            fetchPrediction(props.orgId, version.id, controller.signal)
          )
        );
        const data = {
          scenarios: loadedScenarios,
          events: eventLists
            .flatMap(({ scenario, items }) =>
              items.map((item) => ({
                ...item,
                selectionId: `${scenario.id}:${item.id}`,
                scenarioId: scenario.id,
                scenarioName: scenario.name
              }))
            )
            .sort(
              (left, right) =>
                left.targetDate.localeCompare(right.targetDate) ||
                left.name.localeCompare(right.name)
            ),
          versions: details
        };
        if (cancelled) return;
        setScenarios(data.scenarios);
        setEvents(data.events);
        setVersions((current) => {
          const loadedById = new Map(data.versions.map((version) => [version.id, version]));
          return [...data.versions, ...current.filter((version) => !loadedById.has(version.id))];
        });
        if (!initialWorkspaceLoadedRef.current) {
          initialWorkspaceLoadedRef.current = true;
          const targets = data.scenarios.map((scenario) => scenario.id);
          setTargetScenarioIds(new Set(targets));
          setSelectedScenarioFilter(
            new Set([
              ...targets,
              ...data.versions.flatMap((version) =>
                version.targets.map((target) => target.scenarioId)
              )
            ])
          );
          setSelectedVersionIds(data.versions.length ? new Set([data.versions[0].id]) : new Set());
          setSelectedModelKinds(
            new Set(
              data.versions.flatMap((version) =>
                version.targets.flatMap((target) => target.results.map((result) => result.kind))
              )
            )
          );
          setSelectedMetricIds(
            new Set(
              data.versions.flatMap((version) =>
                version.targets.filter(isNumericPredictionTarget).map((target) => target.metricId)
              )
            )
          );
        }
      } catch (loadError) {
        if (!cancelled && (loadError as { name?: string }).name !== "AbortError") {
          setError(`Could not load Predictions. ${errorMessage(loadError)}`);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [props.orgId, refreshVersion]);

  useEffect(() => {
    if (!includeReality || !realityScenario) return;
    const controller = new AbortController();
    let cancelled = false;
    const source = { orgId: props.orgId, scenarioId: realityScenario.id };
    void fetchTimeseries(props.orgId, realityScenario.id, controller.signal)
      .then((timeseries) => {
        if (!cancelled) setRealityResult({ ...source, timeseries, error: "" });
      })
      .catch((loadError: unknown) => {
        if (!cancelled && (loadError as { name?: string }).name !== "AbortError") {
          setRealityResult({
            ...source,
            timeseries: [],
            error: `Could not load current Reality data. ${errorMessage(loadError)}`
          });
        }
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [includeReality, props.orgId, realityScenario]);

  useEffect(() => {
    let disposed = false;
    let inFlight = false;
    let controller: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const isVisible = () => document.visibilityState !== "hidden";
    const isCurrent = (mutationEpoch: number) =>
      !disposed &&
      currentOrgIdRef.current === props.orgId &&
      controller?.signal.aborted !== true &&
      requestMutationEpochRef.current === mutationEpoch;

    const refreshCompletedVersions = async (
      completed: PredictionRequestSummaryDto[],
      mutationEpoch: number,
      signal: AbortSignal
    ) => {
      const unprocessed = completed.filter(
        (request) => !processedCompletedRequestIdsRef.current.has(request.id)
      );
      if (!unprocessed.length) return;
      const completedIds = unprocessed
        .map((request) => request.completedPredictionId)
        .filter((id): id is string => id !== null);
      if (!completedIds.length) return;

      const savedVersions = await fetchPredictions(props.orgId, signal);
      if (!isCurrent(mutationEpoch)) return;
      const availableIds = new Set(savedVersions.map((version) => version.id));
      const resolvedRequestIds = new Set(
        unprocessed
          .filter(
            (request) =>
              request.completedPredictionId !== null &&
              availableIds.has(request.completedPredictionId)
          )
          .map((request) => request.id)
      );
      if (!resolvedRequestIds.size) return;
      const missingIds = completedIds.filter(
        (id) =>
          availableIds.has(id) &&
          !versionsRef.current.some((version) => version.id === id) &&
          !completedVersionFetchesRef.current.has(id)
      );
      missingIds.forEach((id) => completedVersionFetchesRef.current.add(id));
      try {
        const details = await Promise.all(
          missingIds.map((id) => fetchPrediction(props.orgId, id, signal))
        );
        if (!isCurrent(mutationEpoch)) return;
        if (details.length) {
          setVersions((current) => {
            const existingIds = new Set(current.map((version) => version.id));
            const added = details.filter((version) => !existingIds.has(version.id));
            const next = [...added, ...current];
            versionsRef.current = next;
            return next;
          });
        }
        resolvedRequestIds.forEach((id) => processedCompletedRequestIdsRef.current.add(id));
        const submittedCompletedIds = completed
          .filter(
            (request) =>
              request.completedPredictionId !== null &&
              resolvedRequestIds.has(request.id) &&
              submittedRequestIdsRef.current.has(request.id)
          )
          .map((request) => request.completedPredictionId!);
        if (!submittedCompletedIds.length) return;
        const submittedCompletedIdSet = new Set(submittedCompletedIds);
        const submittedDetails = [
          ...details,
          ...versionsRef.current.filter((version) => submittedCompletedIdSet.has(version.id))
        ].filter(
          (version, index, all) =>
            all.findIndex((candidate) => candidate.id === version.id) === index
        );
        setSelectedVersionIds((current) => new Set([...current, ...submittedCompletedIds]));
        setSelectedScenarioFilter(
          (current) =>
            new Set([
              ...current,
              ...submittedDetails.flatMap((version) =>
                version.targets.map((target) => target.scenarioId)
              )
            ])
        );
        setSelectedModelKinds(
          (current) =>
            new Set([
              ...current,
              ...submittedDetails.flatMap((version) =>
                version.targets.flatMap((target) => target.results.map((result) => result.kind))
              )
            ])
        );
        setSelectedMetricIds(
          (current) =>
            new Set([
              ...current,
              ...submittedDetails.flatMap((version) =>
                version.targets.filter(isNumericPredictionTarget).map((target) => target.metricId)
              )
            ])
        );
      } finally {
        missingIds.forEach((id) => completedVersionFetchesRef.current.delete(id));
      }
    };

    const scheduleNext = () => {
      if (!disposed && isVisible()) {
        timer = setTimeout(() => {
          void poll();
        }, REQUEST_POLL_INTERVAL_MS);
      }
    };

    const poll = async () => {
      if (disposed || !isVisible() || inFlight) return;
      inFlight = true;
      const mutationEpoch = requestMutationEpochRef.current;
      controller = new AbortController();
      try {
        const summaries = await fetchPredictionRequests(props.orgId, controller.signal);
        if (!isCurrent(mutationEpoch)) return;
        setRequestNow(Date.now());
        updateTrackedRequests(summaries);
        setRequestLoading(false);
        setRequestRefreshError("");
        const listedIds = new Set(summaries.map((request) => request.id));
        const missing = [...trackedRequestsRef.current.values()].filter(
          (request) => !listedIds.has(request.id) && !isTerminalRequest(request)
        );
        setPredictionRequests([...summaries, ...missing]);
        let detailError: unknown;
        for (const request of missing) {
          try {
            const detail = await fetchPredictionRequest(props.orgId, request.id, controller.signal);
            if (!isCurrent(mutationEpoch)) return;
            updateTrackedRequests([detail]);
            // Keep the backend's terminal-history order and limit; an active
            // detail response still belongs in Active work.
            setPredictionRequests((current) =>
              isTerminalRequest(detail)
                ? current.filter((item) => item.id !== detail.id)
                : current.map((item) => (item.id === detail.id ? detail : item))
            );
          } catch (error) {
            if (!isCurrent(mutationEpoch)) return;
            detailError = error;
          }
        }
        const completed = new Map(
          [...summaries, ...trackedRequestsRef.current.values()]
            .filter((request) => request.state === "completed")
            .map((request) => [request.id, request])
        );
        await refreshCompletedVersions([...completed.values()], mutationEpoch, controller.signal);
        if (detailError) throw detailError;
      } catch (refreshError) {
        if (isCurrent(mutationEpoch) && (refreshError as { name?: string }).name !== "AbortError") {
          setRequestLoading(false);
          setRequestRefreshError(
            `Could not refresh prediction requests. ${errorMessage(refreshError)}`
          );
        }
      } finally {
        if (controller?.signal.aborted === false) controller = null;
        inFlight = false;
        scheduleNext();
      }
    };

    const onVisibilityChange = () => {
      if (isVisible()) {
        if (timer) clearTimeout(timer);
        timer = null;
        void poll();
      } else {
        if (timer) clearTimeout(timer);
        timer = null;
        controller?.abort();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    void poll();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [props.orgId, updateTrackedRequests]);

  const allModelKinds = useMemo(
    () =>
      sortModelKinds(
        versions.flatMap((version) =>
          version.targets.flatMap((target) => target.results.map((result) => result.kind))
        )
      ),
    [versions]
  );
  const allMetrics = useMemo(() => {
    const metrics = new Map<string, { name: string; unit: string | null }>();
    for (const version of versions)
      for (const target of version.targets) {
        if (!isNumericPredictionTarget(target)) continue;
        metrics.set(target.metricId, { name: target.metricName, unit: target.unit });
      }
    return [...metrics.entries()].sort((left, right) => left[1].name.localeCompare(right[1].name));
  }, [versions]);
  const charts = useMemo(
    () =>
      buildPredictionMetricCharts({
        versions,
        selectedVersionIds,
        selectedScenarioIds: selectedScenarioFilter,
        selectedModelKinds,
        selectedMetricIds,
        scenarioNames,
        startDate: plotStartDate,
        endDate: plotEndDate,
        realityTimeseries: currentReality?.timeseries ?? [],
        includeReality: currentReality !== null && !currentReality.error
      }),
    [
      currentReality,
      plotEndDate,
      plotStartDate,
      scenarioNames,
      selectedMetricIds,
      selectedModelKinds,
      selectedScenarioFilter,
      selectedVersionIds,
      versions
    ]
  );

  function invalidatePreflight() {
    setPreflight(null);
    setFormError("");
    // Without preflight no period input is shown, so an invalid period could not be corrected.
    setManualPeriods((current) =>
      Object.values(current).every(isValidManualSeasonalPeriod)
        ? current
        : Object.fromEntries(
            Object.entries(current).filter(([, period]) => isValidManualSeasonalPeriod(period))
          )
    );
  }

  function selectedRequestModelKinds(): string[] | null {
    if (!requestModelKinds.size) {
      setFormError("Select at least one model.");
      return null;
    }
    return MODEL_KINDS.filter((kind) => requestModelKinds.has(kind));
  }

  function selectedConfidenceLevel(): number | null {
    if (!/^\d+$/.test(confidenceLevel)) {
      setConfidenceLevelError("Enter a whole-number prediction interval level from 50 through 99.");
      return null;
    }
    const value = Number(confidenceLevel);
    if (value < 50 || value > 99) {
      setConfidenceLevelError("Prediction interval level must be from 50 through 99.");
      return null;
    }
    setConfidenceLevelError("");
    return value;
  }

  function updateConfidenceLevel(value: string) {
    setConfidenceLevel(value);
    setConfidenceLevelError("");
    invalidatePreflight();
  }

  function updateStartDate(value: string) {
    setStartDate(value);
    setStartEventId("");
    if (value && (eventById.get(endEventId)?.targetDate ?? "") <= value) setEndEventId("");
    invalidatePreflight();
  }

  function updateEndDate(value: string) {
    setEndDate(value);
    setEndEventId("");
    if (value && (eventById.get(startEventId)?.targetDate ?? "") >= value) setStartEventId("");
    invalidatePreflight();
  }

  function selectStartEvent(value: string) {
    const date = inputDate(eventById.get(value));
    setStartEventId(value);
    setStartDate(date);
    if (date && (eventById.get(endEventId)?.targetDate ?? "") <= date) setEndEventId("");
    invalidatePreflight();
  }

  function selectEndEvent(value: string) {
    const date = inputDate(eventById.get(value));
    setEndEventId(value);
    setEndDate(date);
    if (date && (eventById.get(startEventId)?.targetDate ?? "") >= date) setStartEventId("");
    invalidatePreflight();
  }

  async function handlePreflight() {
    const selectedLevel = selectedConfidenceLevel();
    if (selectedLevel === null) return;
    if (!targetScenarioIds.size)
      return setFormError("Select at least one prediction target scenario.");
    if (!startDate || !endDate) return setFormError("Choose both a start and an end date.");
    if (invalidDates) return setFormError("The start date must be earlier than the end date.");
    const modelKinds = selectedRequestModelKinds();
    if (modelKinds === null) return;
    try {
      setSubmitting(true);
      setFormError("");
      const response = await preflightPredictions(props.orgId, {
        targetScenarioIds: [...targetScenarioIds],
        startDate,
        endDate,
        cutoffMode,
        confidenceLevel: selectedLevel,
        manualSeasonalPeriods: sentManualPeriods,
        modelKinds
      });
      setPreflight(response);
      // Without a seasonal-period kind, preflight reports no periods, so entered ones are kept.
      if (seasonalPeriodSelected)
        setManualPeriods((current) =>
          Object.fromEntries(
            response.metrics
              .filter(usesManualSeasonalPeriod)
              .map((metric) => [
                metric.metricId,
                current[metric.metricId] ?? metric.seasonalPeriod ?? 2
              ])
          )
        );
    } catch (requestError) {
      setFormError(`Preflight failed. ${errorMessage(requestError)}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCreate() {
    const selectedLevel = selectedConfidenceLevel();
    if (selectedLevel === null) return;
    const missingManualPeriod =
      seasonalPeriodSelected &&
      preflight?.metrics.some(
        (metric) =>
          usesManualSeasonalPeriod(metric) &&
          !isValidManualSeasonalPeriod(manualPeriods[metric.metricId] ?? 0)
      );
    if (!preflight) return setFormError("Run preflight before creating a prediction version.");
    if (!preflight.metrics.length)
      return setFormError("Preflight found no forecastable metrics to create.");
    if (!name.trim()) return setFormError("Enter a unique prediction-version name.");
    if (missingManualPeriod)
      return setFormError(
        "Enter every manual seasonal period as a whole number of 2 or more, or clear it and run preflight again to try automatic detection."
      );
    const modelKinds = selectedRequestModelKinds();
    if (modelKinds === null) return;
    try {
      setSubmitting(true);
      setFormError("");
      const created = await createPrediction(props.orgId, {
        name: name.trim(),
        targetScenarioIds: [...targetScenarioIds],
        startDate,
        endDate,
        cutoffMode,
        confidenceLevel: selectedLevel,
        manualSeasonalPeriods: sentManualPeriods,
        modelKinds
      });
      if (currentOrgIdRef.current !== props.orgId) return;
      requestMutationEpochRef.current += 1;
      submittedRequestIdsRef.current.add(created.id);
      trackedRequestsRef.current.set(created.id, created);
      setPredictionRequests((current) => [
        created,
        ...current.filter((request) => request.id !== created.id)
      ]);
      setName("");
      setPreflight(null);
      setRequestNow(Date.now());
      setSubmissionNotices((current) => [created, ...current]);
    } catch (requestError) {
      if (currentOrgIdRef.current === props.orgId) {
        setFormError(`Could not queue prediction. ${errorMessage(requestError)}`);
      }
    } finally {
      if (currentOrgIdRef.current === props.orgId) setSubmitting(false);
    }
  }

  async function handleCancelPredictionRequest(request: PredictionRequestSummaryDto) {
    requestMutationEpochRef.current += 1;
    setRequestActionError("");
    setCancellingRequestIds((current) => new Set(current).add(request.id));
    try {
      const updated = await cancelPredictionRequest(props.orgId, request.id);
      if (currentOrgIdRef.current !== props.orgId) return;
      requestMutationEpochRef.current += 1;
      updateTrackedRequests([updated]);
      setRequestNow(Date.now());
      setPredictionRequests((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
    } catch (requestError) {
      if (currentOrgIdRef.current === props.orgId) {
        setRequestActionError(`Could not update prediction request. ${errorMessage(requestError)}`);
      }
    } finally {
      if (currentOrgIdRef.current === props.orgId) {
        setCancellingRequestIds((current) => {
          const next = new Set(current);
          next.delete(request.id);
          return next;
        });
      }
    }
  }

  if (loading)
    return (
      <section className="predictions-tab" aria-busy="true">
        <h1 className="page-title">Predictions</h1>
        <p role="status">Loading prediction workspace…</p>
      </section>
    );
  if (error)
    return (
      <section className="predictions-tab">
        <h1 className="page-title">Predictions</h1>
        <div className="alert alert--danger" role="alert">
          <p className="alert__title">Predictions could not be loaded</p>
          <p className="alert__text">{error}</p>
          <button
            className="btn btn--secondary"
            type="button"
            onClick={() => setRefreshVersion((current) => current + 1)}
          >
            Try again
          </button>
        </div>
      </section>
    );

  return (
    <section className="predictions-tab" aria-labelledby="predictions-heading">
      <header>
        <p className="eyebrow">Forecasting</p>
        <h1 id="predictions-heading" className="page-title">
          Predictions
        </h1>
        <p className="muted">
          Create immutable, comparable model outputs from each selected scenario's own data. Reality
          can also remain visible as live manually entered comparison data.
        </p>
      </header>
      <div className="predictions-layout">
        <section
          className="detail-card detail-card--spacious predictions-panel"
          aria-labelledby="generation-heading"
        >
          <h2 id="generation-heading">Queue a prediction</h2>
          <label className="form-row">
            <span className="form-label form-label--required">Version name</span>
            <input
              className="input"
              disabled={submitting}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </label>
          <ScenarioMultiSelect
            borderless
            required
            disabled={submitting}
            items={targetScenarios.map((scenario) => [scenario.id, scenario.name])}
            selected={targetScenarioIds}
            onChange={(selected) => {
              setTargetScenarioIds(selected);
              invalidatePreflight();
            }}
          />
          {!targetScenarios.length ? (
            <p className="alert alert--info" role="status">
              No active scenarios are available for prediction.
            </p>
          ) : null}
          <div className="predictions-date-grid">
            <label className="form-row">
              <span className="form-label form-label--required">Start date</span>
              <input
                className="input date-input"
                type="date"
                disabled={submitting}
                value={startDate}
                onChange={(event) => updateStartDate(event.target.value)}
              />
            </label>
            <label className="form-row">
              <span className="form-label form-label--required">End date</span>
              <input
                className="input date-input"
                type="date"
                disabled={submitting}
                value={endDate}
                onChange={(event) => updateEndDate(event.target.value)}
              />
            </label>
            <SearchableEventSelect
              title="Start event"
              disabled={submitting}
              items={availableStartEvents}
              value={startEventId}
              onChange={selectStartEvent}
            />
            <SearchableEventSelect
              title="End event"
              disabled={submitting}
              items={availableEndEvents}
              value={endEventId}
              onChange={selectEndEvent}
            />
          </div>
          {invalidDates ? (
            <p className="alert alert--danger" role="alert">
              The start date must be earlier than the end date.
            </p>
          ) : null}
          <fieldset className="predictions-fieldset" disabled={submitting}>
            <legend className="form-label form-label--required">Observation cutoff</legend>
            <label className="predictions-check">
              <input
                type="radio"
                name="cutoff"
                checked={cutoffMode === "asOfStart"}
                onChange={() => {
                  setCutoffMode("asOfStart");
                  invalidatePreflight();
                }}
              />{" "}
              As of start — excludes observations on and after the first predicted period.
            </label>
            <label className="predictions-check">
              <input
                type="radio"
                name="cutoff"
                checked={cutoffMode === "allCurrentScenario"}
                onChange={() => {
                  setCutoffMode("allCurrentScenario");
                  invalidatePreflight();
                }}
              />{" "}
              All current scenario — retrospective predictions can use later values from the
              selected scenario.
            </label>
          </fieldset>
          <label className="form-row">
            <span className="form-label form-label--required">Prediction interval level</span>
            <input
              aria-label="Prediction interval level"
              aria-describedby={
                confidenceLevelError
                  ? "prediction-interval-help prediction-interval-error"
                  : "prediction-interval-help"
              }
              aria-invalid={confidenceLevelError ? "true" : undefined}
              className="input"
              type="number"
              min="50"
              max="99"
              step="1"
              required
              disabled={submitting}
              value={confidenceLevel}
              onChange={(event) => updateConfidenceLevel(event.target.value)}
            />
            <span id="prediction-interval-help" className="muted">
              50–99%. This is a nominal prediction interval for future observed values; higher
              percentages generally produce wider bands.
            </span>
          </label>
          {confidenceLevelError ? (
            <p id="prediction-interval-error" className="alert alert--danger" role="alert">
              {confidenceLevelError}
            </p>
          ) : null}
          {/* Eligibility depends on models only through whether seasonal-naive or SARIMA is selected
            (ADR-014), and the point limit not at all, so only a change of that class invalidates preflight. */}
          <MultiSelectDropdown
            title="Models"
            borderless
            required
            disabled={submitting}
            items={MODEL_KINDS.map((kind) => [kind, formatModelKind(kind)])}
            selected={requestModelKinds}
            onChange={(selected) => {
              setRequestModelKinds(selected);
              if (selectionUsesSeasonalPeriod(selected) !== seasonalPeriodSelected)
                invalidatePreflight();
              else setFormError("");
            }}
            allLabel="All models"
            allSelectedSummary="All models"
            emptySummary="No models selected"
          />
          <div className="form-actions">
            <button
              className="btn btn--secondary"
              type="button"
              disabled={submitting || invalidDates}
              onClick={() => void handlePreflight()}
            >
              Run preflight
            </button>
            <button
              className="btn btn--primary"
              type="button"
              disabled={submitting || invalidDates || !preflight || !preflight.metrics.length}
              onClick={() => void handleCreate()}
            >
              Queue prediction
            </button>
          </div>
          {formError ? (
            <p className="alert alert--danger" role="alert">
              {formError}
            </p>
          ) : null}
          {submissionNotices.map((notice) => (
            <div
              key={notice.id}
              className={`alert alert--${notice.state === "failed" ? "danger" : "info"} prediction-notice`}
              role={notice.state === "failed" ? "alert" : "status"}
            >
              <button
                className="prediction-notice__dismiss"
                type="button"
                aria-label={`Dismiss prediction request “${notice.name}” notice`}
                onClick={() =>
                  setSubmissionNotices((current) => current.filter((item) => item.id !== notice.id))
                }
              >
                <span aria-hidden="true">×</span>
              </button>
              <p className="alert__text">{requestNoticeMessage(notice)}</p>
            </div>
          ))}
          {preflight ? (
            <PreflightResults
              preflight={preflight}
              showSeasonalPeriods={seasonalPeriodSelected}
              disabled={submitting}
              manualPeriods={manualPeriods}
              onManualPeriodChange={(metricId, value) =>
                setManualPeriods((current) => {
                  // A cleared period is not sent, so the next preflight detects it automatically.
                  if (value !== null) return { ...current, [metricId]: value };
                  return Object.fromEntries(
                    Object.entries(current).filter(([id]) => id !== metricId)
                  );
                })
              }
            />
          ) : null}
        </section>
        <PredictionRequests
          requests={predictionRequests}
          now={requestNow}
          loading={requestLoading}
          refreshError={requestRefreshError}
          actionError={requestActionError}
          cancellingRequestIds={cancellingRequestIds}
          onCancel={(request) => void handleCancelPredictionRequest(request)}
        />
      </div>
      <section
        className="detail-card detail-card--spacious predictions-panel predictions-plots"
        aria-labelledby="plots-heading"
      >
        <h2 id="plots-heading">Compare saved results</h2>
        <div className="predictions-filters">
          <div className="predictions-filter-groups">
            <MultiSelectDropdown
              title="Versions"
              searchable
              borderless
              items={versions.map((version) => [
                version.id,
                `${version.name} (${version.confidenceLevel}% prediction interval)`,
                `Models: ${predictionVersionModelKinds(version).map(formatModelKind).join(", ") || "none"}`
              ])}
              selected={selectedVersionIds}
              onChange={setSelectedVersionIds}
              allLabel="All saved versions"
              allSelectedSummary="All saved versions"
              emptySummary="No saved versions selected"
            />
            <ScenarioMultiSelect
              borderless
              items={comparisonScenarios}
              selected={selectedScenarioFilter}
              onChange={setSelectedScenarioFilter}
            />
            <MultiSelectDropdown
              title="Models and baselines"
              borderless
              items={allModelKinds.map((kind) => [kind, formatModelKind(kind)])}
              selected={selectedModelKinds}
              onChange={setSelectedModelKinds}
              allLabel="All models and baselines"
            />
            <MultiSelectDropdown
              title="Numeric metrics"
              searchable
              borderless
              items={allMetrics.map(([id, metric]) => [
                id,
                `${metric.name} (${metric.unit ?? "no unit"})`
              ])}
              selected={selectedMetricIds}
              onChange={setSelectedMetricIds}
              allLabel="All numeric metrics"
              allSelectedSummary="All numeric metrics"
            />
          </div>
          <div className="predictions-plot-controls">
            <span className="form-label">Plot date range</span>
            <div className="predictions-plot-dates">
              <label className="predictions-date-field">
                Start date
                <input
                  aria-label="Plot start date"
                  className="input date-input"
                  type="date"
                  value={plotStartDate}
                  onChange={(event) => setPlotStartDate(event.target.value)}
                />
              </label>
              <label className="predictions-date-field">
                End date
                <input
                  aria-label="Plot end date"
                  className="input date-input"
                  type="date"
                  value={plotEndDate}
                  onChange={(event) => setPlotEndDate(event.target.value)}
                />
              </label>
            </div>
            <label className="predictions-check">
              <input
                type="checkbox"
                checked={includeReality}
                onChange={(event) => {
                  setIncludeReality(event.target.checked);
                  setRealityResult(null);
                }}
              />{" "}
              Include current Reality (manually entered realized data)
            </label>
          </div>
        </div>
        {currentReality?.error ? (
          <p className="alert alert--danger" role="alert">
            {currentReality.error}
          </p>
        ) : null}
        {includeReality && realityScenario && !currentReality ? (
          <p role="status">Loading current Reality data…</p>
        ) : null}
        {charts.length ? (
          <div className="predictions-chart-grid">
            {charts.map((chart) => (
              <MetricChart
                key={chart.metricId}
                metricName={chart.metricName}
                unit={chart.unit}
                lines={chart.lines}
                missingModelKinds={chart.missingModelKinds}
                notRunModelKinds={chart.notRunModelKinds}
                realityMessage={chart.realityMessage}
              />
            ))}
          </div>
        ) : (
          <div className="empty-state" role="status">
            <p>
              Select saved versions, scenarios, models and metrics with available numeric points to
              plot them.
            </p>
          </div>
        )}
      </section>
    </section>
  );
}

function PredictionRequests(props: {
  requests: PredictionRequestSummaryDto[];
  now: number;
  loading: boolean;
  refreshError: string;
  actionError: string;
  cancellingRequestIds: Set<string>;
  onCancel: (request: PredictionRequestSummaryDto) => void;
}) {
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const historyId = useId();
  const active = props.requests
    .filter(
      (request) =>
        request.state === "queued" || request.state === "running" || request.state === "cancelling"
    )
    .sort(
      (left, right) =>
        left.submittedTime.localeCompare(right.submittedTime) || left.id.localeCompare(right.id)
    );
  const history = props.requests.filter(
    (request) =>
      request.state === "completed" || request.state === "cancelled" || request.state === "failed"
  );

  return (
    <section
      className="detail-card detail-card--spacious predictions-panel prediction-requests"
      aria-labelledby="prediction-requests-heading"
    >
      <h2 id="prediction-requests-heading">Prediction requests</h2>
      <p className="muted">
        Requests continue after you leave this tab. Stopping a calculation discards its calculated
        output.
      </p>
      {props.refreshError ? (
        <p className="alert alert--danger" role="alert">
          {props.refreshError}
        </p>
      ) : null}
      {props.actionError ? (
        <p className="alert alert--danger" role="alert">
          {props.actionError}
        </p>
      ) : null}
      {props.loading ? (
        <p role="status">Loading prediction requests…</p>
      ) : (
        <>
          <section
            className="prediction-requests__group"
            aria-labelledby="active-prediction-requests-heading"
          >
            <h3 id="active-prediction-requests-heading">Active work</h3>
            {active.length ? (
              <div className="prediction-requests__list">
                {active.map((request) => (
                  <PredictionRequestRow
                    key={request.id}
                    request={request}
                    now={props.now}
                    cancelling={props.cancellingRequestIds.has(request.id)}
                    onCancel={props.onCancel}
                  />
                ))}
              </div>
            ) : (
              <p className="empty-state" role="status">
                No active prediction requests.
              </p>
            )}
          </section>
          <section
            className="prediction-requests__group"
            aria-labelledby="recent-prediction-requests-heading"
          >
            <h3 id="recent-prediction-requests-heading">Recent history</h3>
            {history.length ? (
              <div id={historyId} className="prediction-requests__list">
                {(historyExpanded ? history : history.slice(0, 3)).map((request) => (
                  <PredictionRequestRow key={request.id} request={request} now={props.now} />
                ))}
              </div>
            ) : (
              <p className="empty-state" role="status">
                No recent prediction requests.
              </p>
            )}
            {history.length > 3 ? (
              <button
                className="btn btn--secondary"
                type="button"
                aria-expanded={historyExpanded}
                aria-controls={historyId}
                onClick={() => setHistoryExpanded((current) => !current)}
              >
                {historyExpanded ? "Show less" : "Show more"}
              </button>
            ) : null}
          </section>
        </>
      )}
    </section>
  );
}

function PredictionRequestRow(props: {
  request: PredictionRequestSummaryDto;
  now: number;
  cancelling?: boolean;
  onCancel?: (request: PredictionRequestSummaryDto) => void;
}) {
  const action =
    props.request.state === "queued"
      ? "Remove from queue"
      : props.request.state === "running"
        ? "Stop"
        : null;
  const canCancel = action !== null && !props.cancelling && props.request.state !== "cancelling";
  const durations = requestDurations(props.request, props.now);

  return (
    <article className="prediction-request">
      <div className="prediction-request__summary">
        <h4>{props.request.name}</h4>
        <p className="prediction-request__state">{requestStateLabels[props.request.state]}</p>
        {props.request.failureReason ? (
          <p className="prediction-request__failure">{props.request.failureReason}</p>
        ) : null}
        {props.request.state === "cancelling" ? (
          <p className="muted">Calculated output will be discarded.</p>
        ) : null}
        <dl className="prediction-request__timing">
          <div>
            <dt>Queued</dt>
            <dd>
              <time dateTime={props.request.submittedTime}>
                {formatRequestTimestamp(props.request.submittedTime)}
              </time>
            </dd>
          </div>
          <div>
            <dt>Processing started</dt>
            <dd>
              {props.request.startTime ? (
                <time dateTime={props.request.startTime}>
                  {formatRequestTimestamp(props.request.startTime)}
                </time>
              ) : (
                "Not started"
              )}
            </dd>
          </div>
          <div>
            <dt>Finished</dt>
            <dd>
              {props.request.finishTime ? (
                <time dateTime={props.request.finishTime}>
                  {formatRequestTimestamp(props.request.finishTime)}
                </time>
              ) : (
                "Not finished"
              )}
            </dd>
          </div>
          <div>
            <dt>Queue duration</dt>
            <dd>{durations.queue}</dd>
          </div>
          <div>
            <dt>Processing duration</dt>
            <dd>{durations.processing}</dd>
          </div>
        </dl>
      </div>
      {action ? (
        <button
          className="btn btn--secondary"
          type="button"
          disabled={!canCancel}
          onClick={() => props.onCancel?.(props.request)}
        >
          {props.cancelling ? "Stopping…" : action}
        </button>
      ) : null}
    </article>
  );
}

function PreflightResults(props: {
  preflight: PredictionPreflightDto;
  showSeasonalPeriods: boolean;
  disabled: boolean;
  manualPeriods: Record<string, number>;
  onManualPeriodChange: (metricId: string, value: number | null) => void;
}) {
  return (
    <section className="predictions-preflight" aria-live="polite">
      <h3>Preflight eligibility</h3>
      {props.preflight.metrics.length ? (
        props.preflight.metrics.map((metric) => (
          <div
            className="predictions-preflight__row"
            key={`${metric.scenarioId}:${metric.metricId}`}
          >
            <strong>
              {metric.scenarioId} · {metric.metricId}
            </strong>
            <span>
              {metric.status}
              {metric.reason ? ` — ${metric.reason}` : ""}
            </span>
            {!props.showSeasonalPeriods ? null : usesManualSeasonalPeriod(metric) ? (
              <label>
                Manual seasonal period{" "}
                <input
                  aria-label={`Manual seasonal period for ${metric.metricId}`}
                  className="input"
                  type="number"
                  min="2"
                  disabled={props.disabled}
                  value={props.manualPeriods[metric.metricId] ?? ""}
                  onChange={(event) =>
                    props.onManualPeriodChange(
                      metric.metricId,
                      event.target.value === "" ? null : Number(event.target.value)
                    )
                  }
                />
              </label>
            ) : metric.seasonalPeriod ? (
              <span>
                Automatic seasonal period: {metric.seasonalPeriod} ({metric.seasonalPeriodSource})
              </span>
            ) : null}
          </div>
        ))
      ) : (
        <p className="alert alert--info" role="status">
          No forecastable metrics were found for the selected scenarios and date range.
        </p>
      )}
    </section>
  );
}

function useDropdownDismissal(dropdownRef: RefObject<HTMLDetailsElement | null>) {
  useEffect(() => {
    function closeWhenClickedOutside(event: PointerEvent) {
      if (!dropdownRef.current?.contains(event.target as Node)) {
        dropdownRef.current?.removeAttribute("open");
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape" || !dropdownRef.current?.open) return;
      dropdownRef.current.open = false;
      dropdownRef.current.querySelector("summary")?.focus();
    }

    document.addEventListener("pointerdown", closeWhenClickedOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeWhenClickedOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [dropdownRef]);
}

function MultiSelectDropdown(props: {
  title: string;
  // An optional description is shown below its option, outside the accessible name.
  items: Array<[id: string, label: string, description?: string]>;
  selected: Set<string>;
  onChange: (selected: Set<string>) => void;
  searchable?: boolean;
  borderless?: boolean;
  required?: boolean;
  // Disables every option and search field in the dropdown.
  disabled?: boolean;
  allLabel?: string;
  allSelectedSummary?: string;
  emptySummary?: string;
  hideLegend?: boolean;
}) {
  const dropdownRef = useRef<HTMLDetailsElement>(null);
  const descriptionId = useId();
  const [query, setQuery] = useState("");
  useDropdownDismissal(dropdownRef);
  const allSelected = props.items.length > 0 && props.selected.size === props.items.length;
  const summary =
    allSelected && props.allSelectedSummary
      ? props.allSelectedSummary
      : props.selected.size
        ? `${props.selected.size} selected`
        : (props.emptySummary ?? `No ${props.title.toLowerCase()} selected`);
  const filteredItems = props.searchable
    ? props.items.filter(([, label]) =>
        label.toLocaleLowerCase().includes(query.toLocaleLowerCase())
      )
    : props.items;

  return (
    <fieldset
      className={`predictions-fieldset${props.borderless ? " predictions-fieldset--borderless" : ""}`}
      disabled={props.disabled}
    >
      {props.hideLegend ? null : (
        <legend className={`form-label${props.required ? " form-label--required" : ""}`}>
          {props.title}
        </legend>
      )}
      <details ref={dropdownRef} className="predictions-multi-dropdown">
        <summary>{summary}</summary>
        <div className="predictions-multi-dropdown__options">
          {props.searchable ? (
            <input
              className="input"
              type="search"
              aria-label={`Search ${props.title}`}
              placeholder="Type to search..."
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          ) : null}
          <label className="predictions-check">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={(event) =>
                props.onChange(new Set(event.target.checked ? props.items.map(([id]) => id) : []))
              }
            />
            {props.allLabel ?? `All ${props.title.toLowerCase()}`}
          </label>
          {filteredItems.map(([id, label, description], index) => (
            <div className="predictions-check-option" key={id}>
              <label className="predictions-check">
                <input
                  type="checkbox"
                  aria-describedby={description ? `${descriptionId}-${index}` : undefined}
                  checked={props.selected.has(id)}
                  onChange={() => props.onChange(toggleSet(props.selected, id))}
                />{" "}
                {label}
              </label>
              {description ? (
                <small
                  id={`${descriptionId}-${index}`}
                  className="muted predictions-check-option__description"
                >
                  {description}
                </small>
              ) : null}
            </div>
          ))}
          {filteredItems.length === 0 ? <p className="muted">No matching options.</p> : null}
        </div>
      </details>
    </fieldset>
  );
}

function ScenarioMultiSelect(props: {
  borderless?: boolean;
  required?: boolean;
  disabled?: boolean;
  items: Array<[string, string]>;
  selected: Set<string>;
  onChange: (selected: Set<string>) => void;
}) {
  return (
    <MultiSelectDropdown
      title="Target scenarios"
      items={props.items}
      selected={props.selected}
      onChange={props.onChange}
      searchable
      borderless={props.borderless}
      required={props.required}
      disabled={props.disabled}
      allLabel="All active prediction scenarios"
      allSelectedSummary="All active scenarios"
      emptySummary="No scenarios selected"
    />
  );
}

function SearchableEventSelect(props: {
  title: string;
  items: EventOption[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const dropdownRef = useRef<HTMLDetailsElement>(null);
  const [query, setQuery] = useState("");
  useDropdownDismissal(dropdownRef);
  const selected = props.items.find((item) => item.selectionId === props.value);
  const filteredItems = props.items.filter((item) =>
    `${item.targetDate} · ${item.scenarioName} · ${item.name}`
      .toLocaleLowerCase()
      .includes(query.toLocaleLowerCase())
  );

  return (
    <fieldset className="predictions-event-select" disabled={props.disabled}>
      <legend className="form-label">{props.title}</legend>
      <details ref={dropdownRef} className="predictions-multi-dropdown">
        <summary>
          {selected
            ? `${selected.targetDate} · ${selected.scenarioName} · ${selected.name}`
            : "No event selected"}
        </summary>
        <div className="predictions-multi-dropdown__options">
          <input
            className="input"
            type="search"
            aria-label={`Search ${props.title}`}
            placeholder="Type to search..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button
            className="btn btn--ghost predictions-dropdown-option"
            type="button"
            onClick={() => {
              props.onChange("");
              dropdownRef.current?.removeAttribute("open");
            }}
          >
            No event selected
          </button>
          {filteredItems.map((item) => (
            <button
              className="btn btn--ghost predictions-dropdown-option"
              type="button"
              key={item.selectionId}
              onClick={() => {
                props.onChange(item.selectionId);
                dropdownRef.current?.removeAttribute("open");
              }}
            >
              {item.targetDate} · {item.scenarioName} · {item.name}
            </button>
          ))}
          {filteredItems.length === 0 ? <p className="muted">No matching events.</p> : null}
        </div>
      </details>
    </fieldset>
  );
}

function formatSeriesList(items: string[]): string {
  if (items.length < 2) return items[0] ?? "";
  if (items.length === 2) return items.join(" and ");
  return `${items.slice(0, -1).join(", ")}, and ${items.at(-1)}`;
}

function MetricChart(props: {
  metricName: string;
  unit: string;
  lines: PredictionChartLine[];
  missingModelKinds: string[];
  notRunModelKinds: string[];
  realityMessage: string | null;
}) {
  const points = props.lines.flatMap((line) => line.points.map((point) => ({ ...point, line })));
  const dates = [...new Set(points.map((point) => point.date))].sort();
  const values = points.flatMap((point) => [
    point.value,
    ...(point.lowerBound === null || point.upperBound === null
      ? []
      : [point.lowerBound, point.upperBound])
  ]);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const span = max - min || 1;
  const width = 720;
  const height = 260;
  const padding = { top: 38, right: 18, bottom: 34, left: 56 };
  const axisTicks = predictionChartAxisTicks(dates, width - padding.left - padding.right);
  const x = (date: string) =>
    padding.left +
    (dates.length < 2
      ? (width - padding.left - padding.right) / 2
      : (dates.indexOf(date) / (dates.length - 1)) * (width - padding.left - padding.right));
  const y = (value: number) =>
    height - padding.bottom - ((value - min) / span) * (height - padding.top - padding.bottom);
  const lineColor = (line: PredictionChartLine, index: number) =>
    line.kind === "reality" ? "#166534" : lineColors[index % lineColors.length];
  // Dots closer than their radius cannot be hovered separately, so they share hover text.
  const pointRadius = 3;
  const pointTitle = predictionPointTitles(props.lines, props.unit, y, pointRadius);

  return (
    <article className="prediction-chart">
      <header>
        <h3>{props.metricName}</h3>
      </header>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${props.metricName} prediction comparison chart in ${props.unit}`}
      >
        <text className="prediction-chart__unit" x="8" y="18">
          {props.unit}
        </text>
        <line
          className="prediction-chart__axis"
          x1={padding.left}
          x2={padding.left}
          y1={padding.top}
          y2={height - padding.bottom}
        />
        <line
          className="prediction-chart__axis"
          x1={padding.left}
          x2={width - padding.right}
          y1={height - padding.bottom}
          y2={height - padding.bottom}
        />
        <text className="prediction-chart__range" x="4" y={padding.top + 4}>
          {formatPredictionPointValue(max)}
        </text>
        <text className="prediction-chart__range" x="4" y={height - padding.bottom}>
          {formatPredictionPointValue(min)}
        </text>
        {axisTicks
          .filter((tick) => tick.isYearBoundary)
          .map((tick) => (
            <line
              className="prediction-chart__year-boundary"
              key={`year-boundary:${tick.date}`}
              x1={x(tick.date)}
              x2={x(tick.date)}
              y1={padding.top}
              y2={height - padding.bottom}
            />
          ))}
        {axisTicks
          .filter((tick) => tick.showYearLabel)
          .map((tick) => (
            <text
              className="prediction-chart__year"
              key={`year:${tick.date}`}
              x={x(tick.date)}
              y={height - 4}
              textAnchor="middle"
            >
              {tick.year}
            </text>
          ))}
        {props.lines.map((line, index) => {
          const bandPath =
            line.predictionIntervalStatus === "available"
              ? predictionIntervalBandPath(line.points, x, y)
              : null;
          return bandPath ? (
            <path
              className="prediction-chart__interval-band"
              key={`band:${line.id}`}
              fill={lineColor(line, index)}
              d={bandPath}
            >
              <title>{`${line.label}: saved ${line.confidenceLevel}% prediction interval.`}</title>
            </path>
          ) : null;
        })}
        {props.lines.map((line, index) => {
          const path = line.points
            .map(
              (point, pointIndex) => `${pointIndex ? "L" : "M"}${x(point.date)} ${y(point.value)}`
            )
            .join(" ");
          const showDots = line.points.length < 100;
          return (
            <g key={line.id} data-series-id={line.id}>
              <path
                className={
                  line.kind === "reality"
                    ? "prediction-chart__line prediction-chart__line--reality"
                    : "prediction-chart__line"
                }
                stroke={lineColor(line, index)}
                strokeDasharray={line.strokeDasharray}
                d={path}
              >
                <title>{line.provenance}</title>
              </path>
              {line.points.map((point) => (
                <circle
                  key={`${line.id}:${point.date}`}
                  cx={x(point.date)}
                  cy={y(point.value)}
                  r={pointRadius}
                  className={
                    showDots ? "prediction-chart__point" : "prediction-chart__point-hit-target"
                  }
                  fill={showDots ? lineColor(line, index) : "transparent"}
                >
                  <title>{pointTitle(line, point)}</title>
                </circle>
              ))}
            </g>
          );
        })}
        {axisTicks
          .filter((tick) => tick.showDateLabel)
          .map((tick) => (
            <text
              className="prediction-chart__date"
              key={tick.date}
              x={x(tick.date)}
              y={height - 18}
              textAnchor="middle"
            >
              {tick.label}
            </text>
          ))}
      </svg>
      {props.realityMessage ? (
        <p className="prediction-chart__no-results" role="status">
          {props.realityMessage}
        </p>
      ) : null}
      {props.missingModelKinds.length ? (
        <p className="prediction-chart__no-results" role="status">
          No results to show for: {formatSeriesList(props.missingModelKinds.map(formatModelKind))}.
        </p>
      ) : null}
      {props.notRunModelKinds.length ? (
        <p className="prediction-chart__no-results" role="status">
          Not run by the selected versions:{" "}
          {formatSeriesList(props.notRunModelKinds.map(formatModelKind))}.
        </p>
      ) : null}
      <ul className="prediction-chart__legend">
        {props.lines.map((line, index) => (
          <li key={line.id}>
            <svg className="prediction-chart__swatch" viewBox="0 0 28 8" aria-hidden="true">
              <line
                className={
                  line.kind === "reality"
                    ? "prediction-chart__line prediction-chart__line--reality"
                    : "prediction-chart__line"
                }
                x1="0"
                x2="28"
                y1="4"
                y2="4"
                stroke={lineColor(line, index)}
                strokeDasharray={line.strokeDasharray}
              />
            </svg>
            <strong>{line.label}</strong>
            <small>{line.provenance}</small>
          </li>
        ))}
      </ul>
    </article>
  );
}
