import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SubmitEvent } from "react";
import {
  ApiError,
  cleanOrgStates,
  copyScenario,
  createOrgState,
  deleteOrgState,
  deleteScenario,
  fetchOrgStates,
  fetchScenario,
  fetchScenarios,
  updateOrgState,
  updateScenario
} from "../../api/scenarios";
import type { OrgStateDto, ScenarioDto } from "../../api/scenarios";
import {
  type WorkspaceOrgStateSummary,
  useWorkspaceSelection
} from "../../workspace/WorkspaceSelectionContext";

type DetailMode = "scenario" | "state";
type ScenarioAction = "edit" | "delete" | null;

function sortOrgStates(items: OrgStateDto[]): OrgStateDto[] {
  return [...items].sort((a, b) => a.targetDate.localeCompare(b.targetDate));
}

function scenarioRowKey(scenario: ScenarioDto, index: number): string {
  return `${scenario.id || "scenario"}:${scenario.name}:${index}`;
}

function orgStateRowKey(orgState: OrgStateDto, index: number): string {
  return `${orgState.id || "org-state"}:${orgState.targetDate}:${index}`;
}

function orgStateSummary(orgState: OrgStateDto): WorkspaceOrgStateSummary {
  return {
    id: orgState.id,
    name: orgState.name,
    targetDate: orgState.targetDate
  };
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function scenarioCountText(count: number): string {
  return `${count} scenario(s)`;
}

function cleanOrgStatesErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return "The selected scenario could not be found. Refresh scenarios and try again.";
    }
    if (error.status === 409) {
      return "Protected scenarios cannot be cleaned.";
    }
    if (error.status >= 500) {
      return "The server could not clean states right now. Try again later.";
    }
  }

  return "Could not clean states. Try again.";
}

function todayDateValue(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function ScenariosTab(props: { orgId: string }) {
  const { selectedScenario, setSelectedScenario, selectedOrgState, setSelectedOrgState } =
    useWorkspaceSelection();
  const selectedScenarioIdRef = useRef<string | null>(selectedScenario?.id ?? null);
  const selectedOrgStateIdRef = useRef<string | null>(selectedOrgState?.id ?? null);
  const forkSourceScenarioIdRef = useRef("");
  const hydratedScenarioIdRef = useRef<string | null>(null);
  const hydratedOrgStateIdRef = useRef<string | null>(null);

  const [scenarios, setScenarios] = useState<ScenarioDto[]>([]);
  const [orgStates, setOrgStates] = useState<OrgStateDto[]>([]);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [loadingOrgStates, setLoadingOrgStates] = useState(false);
  const [scenarioError, setScenarioError] = useState("");
  const [orgStateError, setOrgStateError] = useState("");
  const [saving, setSaving] = useState(false);

  const [detailMode, setDetailMode] = useState<DetailMode>("scenario");
  const [scenarioAction, setScenarioAction] = useState<ScenarioAction>(null);

  const [scenarioEditName, setScenarioEditName] = useState("");
  const [scenarioEditDescription, setScenarioEditDescription] = useState("");
  const [scenarioDeleteConfirmation, setScenarioDeleteConfirmation] = useState("");
  const [scenarioActionError, setScenarioActionError] = useState("");

  const [forkName, setForkName] = useState("");
  const [forkDescription, setForkDescription] = useState("");
  const [forkSourceScenarioId, setForkSourceScenarioId] = useState("");
  const [forkSourceOrgStates, setForkSourceOrgStates] = useState<OrgStateDto[]>([]);
  const [forkSourceOrgStateId, setForkSourceOrgStateId] = useState("");
  const [loadingForkSourceOrgStates, setLoadingForkSourceOrgStates] = useState(false);
  const [forkError, setForkError] = useState("");

  const [stateCreateName, setStateCreateName] = useState("");
  const [stateCreateDescription, setStateCreateDescription] = useState("");
  const [stateCreateTargetDate, setStateCreateTargetDate] = useState(todayDateValue);
  const [stateCreateError, setStateCreateError] = useState("");

  const [stateEditName, setStateEditName] = useState("");
  const [stateEditDescription, setStateEditDescription] = useState("");
  const [stateEditTargetDate, setStateEditTargetDate] = useState("");
  const [orgStateDeleteConfirmation, setOrgStateDeleteConfirmation] = useState("");
  const [orgStateActionError, setOrgStateActionError] = useState("");

  const [cleanConfirming, setCleanConfirming] = useState(false);
  const [cleaningStates, setCleaningStates] = useState(false);
  const [cleanMessage, setCleanMessage] = useState("");
  const [cleanError, setCleanError] = useState("");

  const selectedScenarioDto = useMemo(
    () => scenarios.find((scenario) => scenario.id === selectedScenario?.id) ?? null,
    [scenarios, selectedScenario?.id]
  );
  const selectedOrgStateDto = useMemo(
    () => orgStates.find((orgState) => orgState.id === selectedOrgState?.id) ?? null,
    [orgStates, selectedOrgState?.id]
  );
  const forkSourceScenarioDto = useMemo(
    () => scenarios.find((scenario) => scenario.id === forkSourceScenarioId) ?? null,
    [forkSourceScenarioId, scenarios]
  );
  const availableForkSourceOrgStates =
    forkSourceScenarioId === selectedScenarioDto?.id ? orgStates : forkSourceOrgStates;
  const forkSourceOrgStateDto = useMemo(
    () =>
      availableForkSourceOrgStates.find((orgState) => orgState.id === forkSourceOrgStateId) ?? null,
    [availableForkSourceOrgStates, forkSourceOrgStateId]
  );

  useEffect(() => {
    selectedScenarioIdRef.current = selectedScenario?.id ?? null;
  }, [selectedScenario?.id]);

  useEffect(() => {
    selectedOrgStateIdRef.current = selectedOrgState?.id ?? null;
  }, [selectedOrgState?.id]);

  const applySelectedOrgState = useCallback(
    (orgState: OrgStateDto | null) => {
      selectedOrgStateIdRef.current = orgState?.id ?? null;
      hydratedOrgStateIdRef.current = orgState?.id ?? null;
      setSelectedOrgState(orgState ? orgStateSummary(orgState) : null);
      setStateEditName(orgState?.name ?? "");
      setStateEditDescription(orgState?.description ?? "");
      setStateEditTargetDate(orgState?.targetDate ?? "");
      if (forkSourceScenarioIdRef.current === selectedScenarioIdRef.current) {
        setForkSourceOrgStateId(orgState?.id ?? "");
      }
      setOrgStateActionError("");
      setOrgStateDeleteConfirmation("");
    },
    [setSelectedOrgState]
  );

  const applySelectedScenario = useCallback(
    (scenario: ScenarioDto | null, options?: { preserveOrgState?: boolean }) => {
      selectedScenarioIdRef.current = scenario?.id ?? null;
      hydratedScenarioIdRef.current = scenario?.id ?? null;
      forkSourceScenarioIdRef.current = scenario?.id ?? "";
      setForkSourceScenarioId(scenario?.id ?? "");
      setForkSourceOrgStates([]);
      setLoadingForkSourceOrgStates(false);
      setSelectedScenario(scenario ? { id: scenario.id, name: scenario.name } : null);
      if (!options?.preserveOrgState) {
        applySelectedOrgState(null);
      }
      setDetailMode("scenario");
      setScenarioEditName(scenario?.name ?? "");
      setScenarioEditDescription(scenario?.description ?? "");
      setForkName(scenario ? `Fork of ${scenario.name}` : "");
      setForkDescription(scenario?.description ?? "");
      setScenarioAction(null);
      setScenarioActionError("");
      setScenarioDeleteConfirmation("");
      setOrgStateActionError("");
      setOrgStateDeleteConfirmation("");
      setForkError("");
      setStateCreateError("");
      setCleanConfirming(false);
      setCleanMessage("");
      setCleanError("");
    },
    [applySelectedOrgState, setSelectedScenario]
  );

  useEffect(() => {
    const scenarioId = selectedScenario?.id ?? null;
    if (hydratedScenarioIdRef.current === scenarioId) return;
    const scenario = scenarioId ? (scenarios.find((item) => item.id === scenarioId) ?? null) : null;
    if (scenarioId && !scenario) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      hydratedScenarioIdRef.current = scenarioId;
      forkSourceScenarioIdRef.current = scenarioId ?? "";
      setForkSourceScenarioId(scenarioId ?? "");
      setForkSourceOrgStates([]);
      setLoadingForkSourceOrgStates(false);
      setScenarioEditName(scenario?.name ?? "");
      setScenarioEditDescription(scenario?.description ?? "");
      setForkName(scenario ? `Fork of ${scenario.name}` : "");
      setForkDescription(scenario?.description ?? "");
      setScenarioAction(null);
      setScenarioActionError("");
      setScenarioDeleteConfirmation("");
      setForkError("");
      setCleanConfirming(false);
      setCleanMessage("");
      setCleanError("");
    });
    return () => {
      cancelled = true;
    };
  }, [scenarios, selectedScenario?.id]);

  useEffect(() => {
    const orgStateId = selectedOrgState?.id ?? null;
    if (hydratedOrgStateIdRef.current === orgStateId) return;
    const orgState = orgStateId ? (orgStates.find((item) => item.id === orgStateId) ?? null) : null;
    if (orgStateId && !orgState) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      hydratedOrgStateIdRef.current = orgStateId;
      setStateEditName(orgState?.name ?? "");
      setStateEditDescription(orgState?.description ?? "");
      setStateEditTargetDate(orgState?.targetDate ?? "");
      if (forkSourceScenarioIdRef.current === selectedScenarioIdRef.current) {
        setForkSourceOrgStateId(orgState?.id ?? "");
      }
      setOrgStateActionError("");
      setOrgStateDeleteConfirmation("");
    });
    return () => {
      cancelled = true;
    };
  }, [orgStates, selectedOrgState?.id]);

  const reconcileLoadedScenarios = useCallback(
    (items: ScenarioDto[]) => {
      const storedScenarioId = selectedScenarioIdRef.current;
      const storedScenario = storedScenarioId
        ? (items.find((scenario) => scenario.id === storedScenarioId) ?? null)
        : null;
      const nextScenario = storedScenario ?? items[0] ?? null;

      applySelectedScenario(nextScenario, {
        preserveOrgState: Boolean(storedScenario)
      });
    },
    [applySelectedScenario]
  );

  const loadScenarios = useCallback(
    async (signal?: AbortSignal) => {
      try {
        setLoadingScenarios(true);
        setScenarioError("");
        const items = await fetchScenarios(props.orgId, signal);
        setScenarios(items);
        reconcileLoadedScenarios(items);
      } catch (error) {
        const err = error as { name?: string };
        if (err.name === "AbortError") return;
        setScenarioError(messageFromError(error));
      } finally {
        setLoadingScenarios(false);
      }
    },
    [props.orgId, reconcileLoadedScenarios]
  );

  useEffect(() => {
    const ac = new AbortController();
    let ignore = false;

    async function loadInitialScenarios() {
      try {
        setLoadingScenarios(true);
        setScenarioError("");
        const items = await fetchScenarios(props.orgId, ac.signal);
        if (ignore) return;
        setScenarios(items);
        reconcileLoadedScenarios(items);
      } catch (error) {
        const err = error as { name?: string };
        if (ignore || err.name === "AbortError") return;
        setScenarioError(messageFromError(error));
      } finally {
        if (!ignore) setLoadingScenarios(false);
      }
    }

    void loadInitialScenarios();

    return () => {
      ignore = true;
      ac.abort();
    };
  }, [props.orgId, reconcileLoadedScenarios]);

  useEffect(() => {
    const scenarioId = selectedScenario?.id;
    if (!scenarioId) return;
    const activeScenarioId = scenarioId;

    const ac = new AbortController();
    let ignore = false;

    async function loadScenarioOrgStates() {
      try {
        setLoadingOrgStates(true);
        setOrgStateError("");
        setOrgStates([]);
        const items = sortOrgStates(await fetchOrgStates(props.orgId, activeScenarioId, ac.signal));
        if (ignore) return;
        setOrgStates(items);
        const selectedOrgStateId = selectedOrgStateIdRef.current;
        const stillSelected = selectedOrgStateId
          ? items.find((orgState) => orgState.id === selectedOrgStateId)
          : null;
        const nextOrgState = stillSelected ?? items[0] ?? null;
        applySelectedOrgState(nextOrgState);
      } catch (error) {
        const err = error as { name?: string };
        if (ignore || err.name === "AbortError") return;
        setOrgStateError(messageFromError(error));
      } finally {
        if (!ignore) setLoadingOrgStates(false);
      }
    }

    void loadScenarioOrgStates();

    return () => {
      ignore = true;
      ac.abort();
    };
  }, [applySelectedOrgState, props.orgId, selectedScenario?.id]);

  useEffect(() => {
    if (!forkSourceScenarioId || forkSourceScenarioId === selectedScenario?.id) {
      return;
    }
    const activeForkSourceScenarioId = forkSourceScenarioId;
    const ac = new AbortController();
    let ignore = false;

    async function loadForkSourceOrgStates() {
      try {
        setLoadingForkSourceOrgStates(true);
        setForkError("");
        setForkSourceOrgStates([]);
        setForkSourceOrgStateId("");
        const items = sortOrgStates(
          await fetchOrgStates(props.orgId, activeForkSourceScenarioId, ac.signal)
        );
        if (ignore) return;
        setForkSourceOrgStates(items);
        setForkSourceOrgStateId(items[0]?.id ?? "");
      } catch (error) {
        const err = error as { name?: string };
        if (ignore || err.name === "AbortError") return;
        setForkError(`Could not load source states. ${messageFromError(error)}`);
      } finally {
        if (!ignore) setLoadingForkSourceOrgStates(false);
      }
    }

    void loadForkSourceOrgStates();

    return () => {
      ignore = true;
      ac.abort();
    };
  }, [forkSourceScenarioId, props.orgId, selectedScenario?.id]);

  function resetScenarioActionState() {
    setScenarioAction(null);
    setScenarioActionError("");
    setScenarioDeleteConfirmation("");
  }

  function resetOrgStateActionState() {
    setOrgStateActionError("");
    setOrgStateDeleteConfirmation("");
  }

  function selectScenario(scenario: ScenarioDto) {
    applySelectedScenario(scenario);
  }

  function selectForkSourceScenario(scenario: ScenarioDto) {
    forkSourceScenarioIdRef.current = scenario.id;
    setForkSourceScenarioId(scenario.id);
    setForkSourceOrgStates([]);
    setLoadingForkSourceOrgStates(false);
    setForkSourceOrgStateId(
      scenario.id === selectedScenarioDto?.id
        ? (selectedOrgStateDto?.id ?? orgStates[0]?.id ?? "")
        : ""
    );
    setForkName(`Fork of ${scenario.name}`);
    setForkDescription(scenario.description);
    setForkError("");
  }

  function selectOrgState(orgState: OrgStateDto) {
    applySelectedOrgState(orgState);
    setDetailMode("state");
    setStateCreateError("");
  }

  function openScenarioEdit() {
    if (!selectedScenarioDto) return;
    setScenarioAction("edit");
    setScenarioEditName(selectedScenarioDto.name);
    setScenarioEditDescription(selectedScenarioDto.description);
    setScenarioActionError("");
    setScenarioDeleteConfirmation("");
  }

  function openScenarioDelete() {
    if (!selectedScenarioDto || selectedScenarioDto.protected) return;
    setScenarioAction("delete");
    setScenarioActionError("");
    setScenarioDeleteConfirmation("");
  }

  function hasDuplicateTargetDate(targetDate: string, currentId?: string) {
    return orgStates.some(
      (orgState) => orgState.targetDate === targetDate && orgState.id !== currentId
    );
  }

  async function refreshScenariosAndStates() {
    if (!selectedScenario?.id) {
      await loadScenarios();
      return;
    }

    try {
      setLoadingScenarios(true);
      setLoadingOrgStates(true);
      setScenarioError("");
      setOrgStateError("");
      const [updatedScenario, updatedOrgStates] = await Promise.all([
        fetchScenario(props.orgId, selectedScenario.id),
        fetchOrgStates(props.orgId, selectedScenario.id)
      ]);
      const sortedOrgStates = sortOrgStates(updatedOrgStates);
      setScenarios((current) =>
        current.map((scenario) => (scenario.id === updatedScenario.id ? updatedScenario : scenario))
      );
      setSelectedScenario({
        id: updatedScenario.id,
        name: updatedScenario.name
      });
      setScenarioEditName(updatedScenario.name);
      setScenarioEditDescription(updatedScenario.description);
      if (forkSourceScenarioIdRef.current === updatedScenario.id) {
        setForkName(`Fork of ${updatedScenario.name}`);
        setForkDescription(updatedScenario.description);
      }
      setOrgStates(sortedOrgStates);
      const stillSelected = sortedOrgStates.find(
        (orgState) => orgState.id === selectedOrgState?.id
      );
      const nextOrgState = stillSelected ?? sortedOrgStates[0] ?? null;
      applySelectedOrgState(nextOrgState);
    } catch (error) {
      const message = messageFromError(error);
      setScenarioError(message);
      setOrgStateError(message);
    } finally {
      setLoadingScenarios(false);
      setLoadingOrgStates(false);
    }
  }

  async function onScenarioEditSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedScenarioDto) return;
    const name = scenarioEditName.trim();
    if (!name) {
      setScenarioActionError("Scenario name is required.");
      return;
    }

    try {
      setSaving(true);
      setScenarioActionError("");
      const updated = await updateScenario(props.orgId, selectedScenarioDto.id, {
        name,
        description: scenarioEditDescription.trim()
      });
      setScenarios((current) =>
        current.map((scenario) => (scenario.id === updated.id ? updated : scenario))
      );
      setSelectedScenario({ id: updated.id, name: updated.name });
      setScenarioEditName(updated.name);
      setScenarioEditDescription(updated.description);
      if (forkSourceScenarioIdRef.current === updated.id) {
        setForkName(`Fork of ${updated.name}`);
        setForkDescription(updated.description);
      }
      setScenarioAction(null);
    } catch (error) {
      setScenarioActionError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onForkSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!forkSourceScenarioDto) return;
    if (!forkSourceOrgStateDto) {
      setForkError("Select an org state to choose the fork target date.");
      return;
    }

    const name = forkName.trim();
    try {
      setSaving(true);
      setForkError("");
      const created = await copyScenario(props.orgId, {
        sourceScenarioId: forkSourceScenarioDto.id,
        sourceOrgStateId: forkSourceOrgStateDto.id,
        ...(name ? { name } : {}),
        description: forkDescription.trim()
      });
      setScenarios((current) => [...current, created]);
      setSelectedScenario({ id: created.id, name: created.name });
      setSelectedOrgState(null);
      setScenarioEditName(created.name);
      setScenarioEditDescription(created.description);
      setForkName(`Fork of ${created.name}`);
      setForkDescription(created.description);
      forkSourceScenarioIdRef.current = created.id;
      setForkSourceScenarioId(created.id);
      setForkSourceOrgStates([]);
      setForkSourceOrgStateId("");
      setDetailMode("scenario");
    } catch (error) {
      setForkError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onScenarioDeleteSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !selectedScenarioDto ||
      selectedScenarioDto.protected ||
      scenarioDeleteConfirmation !== "DELETE"
    ) {
      return;
    }

    try {
      setSaving(true);
      setScenarioActionError("");
      await deleteScenario(props.orgId, selectedScenarioDto.id);
      setScenarios((current) =>
        current.filter((scenario) => scenario.id !== selectedScenarioDto.id)
      );
      selectedScenarioIdRef.current = null;
      setSelectedScenario(null);
      setSelectedOrgState(null);
      setOrgStates([]);
      setScenarioEditName("");
      setScenarioEditDescription("");
      setForkName("");
      setForkDescription("");
      forkSourceScenarioIdRef.current = "";
      setForkSourceScenarioId("");
      setForkSourceOrgStates([]);
      setForkSourceOrgStateId("");
      setScenarioAction(null);
    } catch (error) {
      setScenarioActionError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onOrgStateCreateSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedScenarioDto) return;
    const name = stateCreateName.trim();
    if (!name) {
      setStateCreateError("Org state name is required.");
      return;
    }
    if (!stateCreateTargetDate) {
      setStateCreateError("Target date is required.");
      return;
    }
    if (hasDuplicateTargetDate(stateCreateTargetDate)) {
      setStateCreateError("Target date must be unique within the scenario.");
      return;
    }

    try {
      setSaving(true);
      setStateCreateError("");
      const created = await createOrgState(props.orgId, selectedScenarioDto.id, {
        name,
        description: stateCreateDescription.trim(),
        targetDate: stateCreateTargetDate
      });
      setOrgStates((current) => sortOrgStates([...current, created]));
      selectOrgState(created);
      setStateCreateName("");
      setStateCreateDescription("");
      setStateCreateTargetDate(todayDateValue());
    } catch (error) {
      setStateCreateError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onOrgStateEditSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedScenarioDto || !selectedOrgStateDto) return;
    const name = stateEditName.trim();
    if (!name) {
      setOrgStateActionError("Org state name is required.");
      return;
    }
    if (!stateEditTargetDate) {
      setOrgStateActionError("Target date is required.");
      return;
    }
    if (hasDuplicateTargetDate(stateEditTargetDate, selectedOrgStateDto.id)) {
      setOrgStateActionError("Target date must be unique within the scenario.");
      return;
    }

    try {
      setSaving(true);
      setOrgStateActionError("");
      const updated = await updateOrgState(
        props.orgId,
        selectedScenarioDto.id,
        selectedOrgStateDto.id,
        {
          name,
          description: stateEditDescription.trim(),
          targetDate: stateEditTargetDate
        }
      );
      setOrgStates((current) =>
        sortOrgStates(current.map((orgState) => (orgState.id === updated.id ? updated : orgState)))
      );
      selectOrgState(updated);
    } catch (error) {
      setOrgStateActionError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onOrgStateDeleteSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedScenarioDto || !selectedOrgStateDto || orgStateDeleteConfirmation !== "DELETE") {
      return;
    }

    try {
      setSaving(true);
      setOrgStateActionError("");
      await deleteOrgState(props.orgId, selectedScenarioDto.id, selectedOrgStateDto.id);
      const remainingOrgStates = orgStates.filter(
        (orgState) => orgState.id !== selectedOrgStateDto.id
      );
      setOrgStates(remainingOrgStates);
      applySelectedOrgState(remainingOrgStates[0] ?? null);
    } catch (error) {
      setOrgStateActionError(messageFromError(error));
    } finally {
      setSaving(false);
    }
  }

  function openCleanConfirmation() {
    if (!selectedScenarioDto || selectedScenarioDto.protected || cleaningStates) {
      return;
    }
    setCleanConfirming(true);
    setCleanMessage("");
    setCleanError("");
  }

  async function onCleanStatesConfirm() {
    if (!selectedScenarioDto || selectedScenarioDto.protected || cleaningStates) {
      return;
    }

    try {
      setCleaningStates(true);
      setCleanError("");
      setCleanMessage("");
      const response = await cleanOrgStates(props.orgId, selectedScenarioDto.id);
      await refreshScenariosAndStates();
      setCleanMessage(`Cleaned ${response.cleaned} state(s).`);
      setCleanConfirming(false);
    } catch (error) {
      setCleanError(cleanOrgStatesErrorMessage(error));
    } finally {
      setCleaningStates(false);
    }
  }

  const refreshDisabled = loadingScenarios || loadingOrgStates;
  const cleanDisabled = !selectedScenarioDto || selectedScenarioDto.protected || cleaningStates;

  return (
    <div className="management-tab">
      <section className="tab-toolbar" aria-label="Scenario overview">
        <div className="tab-toolbar__title">
          <h1 className="page-title">Scenarios</h1>
          <span className="tab-toolbar__count">{scenarioCountText(scenarios.length)}</span>
        </div>
        <button
          className="btn btn--secondary"
          type="button"
          onClick={() => void refreshScenariosAndStates()}
          disabled={refreshDisabled}
        >
          {refreshDisabled ? "Refreshing..." : "Refresh"}
        </button>
      </section>

      <div className="main-detail-layout">
        <aside className="main-detail-sidebar" aria-label="Scenario and org state selection">
          <section className="sidebar-section">
            <h3 className="secondary-title">Scenarios</h3>
            {loadingScenarios ? <p className="muted">Loading scenarios...</p> : null}
            {scenarioError ? (
              <div className="alert alert--danger" role="alert">
                <p className="alert__title">Scenario API error</p>
                <p className="alert__text">{scenarioError}</p>
              </div>
            ) : null}

            {!loadingScenarios && !scenarioError && scenarios.length === 0 ? (
              <p className="muted">No scenarios available.</p>
            ) : null}

            <div className="entity-list" aria-label="Scenario list">
              {scenarios.map((scenario, index) => {
                const isSelected = scenario.id === selectedScenario?.id;
                return (
                  <div
                    key={scenarioRowKey(scenario, index)}
                    className={`scenario-list-item${
                      isSelected ? " scenario-list-item--selected" : ""
                    }`}
                  >
                    <button
                      className={`entity-row${isSelected ? " entity-row--selected" : ""}`}
                      type="button"
                      onClick={() => selectScenario(scenario)}
                      aria-pressed={isSelected}
                    >
                      <span className="entity-row__main">
                        <span className="entity-row__title">{scenario.name}</span>
                        <ScenarioProtectionBadge protected={scenario.protected} />
                      </span>
                    </button>
                    {isSelected ? (
                      <InlineOrgStateList
                        orgStates={orgStates}
                        selectedOrgStateId={selectedOrgState?.id ?? null}
                        loading={loadingOrgStates}
                        error={orgStateError}
                        onSelectOrgState={selectOrgState}
                      />
                    ) : null}
                  </div>
                );
              })}
            </div>

            {!selectedScenarioDto ? (
              <p className="muted">Select a scenario to view org states.</p>
            ) : null}
          </section>
        </aside>

        <section className="detail-workspace" aria-label="Selected item">
          <div className="detail-mode-switch-panel">
            <div className="detail-mode-switch" aria-label="Detail view">
              <button
                className={`detail-mode-switch__button${
                  detailMode === "scenario" ? " detail-mode-switch__button--active" : ""
                }`}
                type="button"
                onClick={() => setDetailMode("scenario")}
                aria-pressed={detailMode === "scenario"}
              >
                Scenario
              </button>
              <button
                className={`detail-mode-switch__button${
                  detailMode === "state" ? " detail-mode-switch__button--active" : ""
                }`}
                type="button"
                onClick={() => setDetailMode("state")}
                aria-pressed={detailMode === "state"}
              >
                State
              </button>
            </div>
            <button
              className="btn btn--secondary detail-mode-switch-panel__action"
              type="button"
              onClick={openCleanConfirmation}
              disabled={cleanDisabled}
            >
              {cleaningStates ? "Cleaning..." : "Clean states"}
            </button>
          </div>

          <CleanStatesFeedback
            scenario={selectedScenarioDto}
            confirming={cleanConfirming}
            cleaning={cleaningStates}
            message={cleanMessage}
            error={cleanError}
            onConfirm={() => void onCleanStatesConfirm()}
            onCancel={() => setCleanConfirming(false)}
          />

          {detailMode === "scenario" ? (
            <div className="detail-grid">
              <ScenarioDetail
                scenario={selectedScenarioDto}
                action={scenarioAction}
                editName={scenarioEditName}
                editDescription={scenarioEditDescription}
                deleteConfirmation={scenarioDeleteConfirmation}
                error={scenarioActionError}
                saving={saving}
                onEditNameChange={setScenarioEditName}
                onEditDescriptionChange={setScenarioEditDescription}
                onDeleteConfirmationChange={setScenarioDeleteConfirmation}
                onOpenEdit={openScenarioEdit}
                onOpenDelete={openScenarioDelete}
                onCancel={resetScenarioActionState}
                onEditSubmit={onScenarioEditSubmit}
                onDeleteSubmit={onScenarioDeleteSubmit}
              />
              <ForkScenarioForm
                scenarios={scenarios}
                orgStates={availableForkSourceOrgStates}
                scenario={forkSourceScenarioDto}
                orgState={forkSourceOrgStateDto}
                name={forkName}
                description={forkDescription}
                error={forkError}
                saving={saving}
                loadingOrgStates={
                  forkSourceScenarioId === selectedScenarioDto?.id
                    ? loadingOrgStates
                    : loadingForkSourceOrgStates
                }
                onSourceScenarioChange={selectForkSourceScenario}
                onSourceOrgStateChange={(orgState) => setForkSourceOrgStateId(orgState.id)}
                onNameChange={setForkName}
                onDescriptionChange={setForkDescription}
                onSubmit={onForkSubmit}
              />
            </div>
          ) : (
            <div className="detail-grid">
              <OrgStateDetail
                scenario={selectedScenarioDto}
                orgState={selectedOrgStateDto}
                editName={stateEditName}
                editDescription={stateEditDescription}
                editTargetDate={stateEditTargetDate}
                deleteConfirmation={orgStateDeleteConfirmation}
                error={orgStateActionError}
                saving={saving}
                onEditNameChange={setStateEditName}
                onEditDescriptionChange={setStateEditDescription}
                onEditTargetDateChange={setStateEditTargetDate}
                onDeleteConfirmationChange={setOrgStateDeleteConfirmation}
                onCancel={resetOrgStateActionState}
                onEditSubmit={onOrgStateEditSubmit}
                onDeleteSubmit={onOrgStateDeleteSubmit}
              />
              <CreateOrgStateForm
                scenario={selectedScenarioDto}
                name={stateCreateName}
                description={stateCreateDescription}
                targetDate={stateCreateTargetDate}
                error={stateCreateError}
                saving={saving}
                onNameChange={setStateCreateName}
                onDescriptionChange={setStateCreateDescription}
                onTargetDateChange={setStateCreateTargetDate}
                onSubmit={onOrgStateCreateSubmit}
              />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function CleanStatesFeedback(props: {
  scenario: ScenarioDto | null;
  confirming: boolean;
  cleaning: boolean;
  message: string;
  error: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!props.confirming && !props.message && !props.error) return null;

  return (
    <div className="clean-states-panel">
      {props.confirming ? (
        <div className="action-panel" role="group" aria-label="Clean states confirmation">
          <p className="muted">
            Clean organisation states for {props.scenario?.name ?? "the selected scenario"}?
          </p>
          <div className="form-actions">
            <button
              className="btn btn--danger"
              type="button"
              onClick={props.onConfirm}
              disabled={props.cleaning}
            >
              {props.cleaning ? "Cleaning..." : "Confirm clean states"}
            </button>
            <button
              className="btn btn--secondary"
              type="button"
              onClick={props.onCancel}
              disabled={props.cleaning}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      {props.message ? (
        <div className="alert alert--info" role="status">
          <p className="alert__title">States cleaned</p>
          <p className="alert__text">{props.message}</p>
        </div>
      ) : null}
      <ActionError message={props.error} />
    </div>
  );
}

function InlineOrgStateList(props: {
  orgStates: OrgStateDto[];
  selectedOrgStateId: string | null;
  loading: boolean;
  error: string;
  onSelectOrgState: (orgState: OrgStateDto) => void;
}) {
  return (
    <div className="scenario-inline-states">
      <p className="eyebrow scenario-inline-states__heading">STATES</p>
      {props.loading ? <p className="muted">Loading org states...</p> : null}
      {props.error ? (
        <div className="alert alert--danger" role="alert">
          <p className="alert__title">Org state API error</p>
          <p className="alert__text">{props.error}</p>
        </div>
      ) : null}

      {!props.loading && !props.error && props.orgStates.length === 0 ? (
        <p className="muted">No org states available.</p>
      ) : null}

      <div className="entity-list" aria-label="Org state list">
        {props.orgStates.map((orgState, index) => {
          const isSelected = orgState.id === props.selectedOrgStateId;
          return (
            <button
              key={orgStateRowKey(orgState, index)}
              className={`entity-row entity-row--compact${
                isSelected ? " entity-row--selected" : ""
              }`}
              type="button"
              onClick={() => props.onSelectOrgState(orgState)}
              aria-pressed={isSelected}
            >
              <span className="entity-row__main">
                <span className="entity-row__title">{orgState.name}</span>
              </span>
              <span className="entity-row__date">{orgState.targetDate}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ScenarioDetail(props: {
  scenario: ScenarioDto | null;
  action: ScenarioAction;
  editName: string;
  editDescription: string;
  deleteConfirmation: string;
  error: string;
  saving: boolean;
  onEditNameChange: (value: string) => void;
  onEditDescriptionChange: (value: string) => void;
  onDeleteConfirmationChange: (value: string) => void;
  onOpenEdit: () => void;
  onOpenDelete: () => void;
  onCancel: () => void;
  onEditSubmit: (event: SubmitEvent<HTMLFormElement>) => void;
  onDeleteSubmit: (event: SubmitEvent<HTMLFormElement>) => void;
}) {
  const editedScenarioName = props.editName.trim();
  const editedScenarioDescription = props.editDescription.trim();
  const scenarioHasChanges = props.scenario
    ? editedScenarioName !== props.scenario.name ||
      editedScenarioDescription !== props.scenario.description
    : false;
  const saveScenarioDisabled = !props.scenario || !editedScenarioName || !scenarioHasChanges;

  return (
    <section className="detail-card" aria-labelledby="selected-scenario-title">
      <div className="detail-card__header">
        <h2 id="selected-scenario-title" className="section-title">
          Selected scenario
        </h2>
      </div>

      {!props.scenario ? (
        <p className="muted">Select a scenario in the side panel.</p>
      ) : (
        <>
          <form onSubmit={props.onEditSubmit}>
            <ScenarioFields
              idPrefix="scenario-edit"
              name={props.editName}
              description={props.editDescription}
              onNameChange={props.onEditNameChange}
              onDescriptionChange={props.onEditDescriptionChange}
            />
            <ActionError message={props.error} />
            <ActionButtons
              submitLabel="Save scenario"
              saving={props.saving}
              onCancel={props.onCancel}
              disabled={saveScenarioDisabled}
            />
          </form>
          <div>
            <ScenarioProtectionBadge protected={props.scenario.protected} />
          </div>
          {props.scenario.protected ? (
            <p className="muted">Protected scenario cannot be deleted.</p>
          ) : (
            <form onSubmit={props.onDeleteSubmit}>
              <label className="form-label" htmlFor="scenario-delete-confirm">
                Confirmation
              </label>
              <input
                id="scenario-delete-confirm"
                className="input"
                placeholder="Type DELETE to confirm"
                value={props.deleteConfirmation}
                onChange={(event) => props.onDeleteConfirmationChange(event.target.value)}
                autoComplete="off"
              />
              <ActionError message={props.error} />
              <div className="form-actions">
                <button
                  className="btn btn--danger"
                  type="submit"
                  disabled={props.saving || props.deleteConfirmation !== "DELETE"}
                >
                  {props.saving ? "Deleting..." : "Delete scenario"}
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}

function ScenarioProtectionBadge(props: { protected: boolean }) {
  return (
    <span className={`badge ${props.protected ? "badge--neutral" : "badge--accent"}`}>
      {props.protected ? "Protected" : "Not protected"}
    </span>
  );
}

function ForkScenarioForm(props: {
  scenarios: ScenarioDto[];
  orgStates: OrgStateDto[];
  scenario: ScenarioDto | null;
  orgState: OrgStateDto | null;
  name: string;
  description: string;
  error: string;
  saving: boolean;
  loadingOrgStates: boolean;
  onSourceScenarioChange: (scenario: ScenarioDto) => void;
  onSourceOrgStateChange: (orgState: OrgStateDto) => void;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onSubmit: (event: SubmitEvent<HTMLFormElement>) => void;
}) {
  const disabled = !props.scenario || !props.orgState || props.saving;

  return (
    <form className="detail-card" aria-labelledby="fork-scenario-title" onSubmit={props.onSubmit}>
      <div className="detail-card__header">
        <h2 id="fork-scenario-title" className="section-title">
          Fork from existing
        </h2>
      </div>
      <label className="form-label form-label--required" htmlFor="fork-source-scenario">
        Source scenario
      </label>
      <select
        id="fork-source-scenario"
        className="select"
        value={props.scenario?.id ?? ""}
        onChange={(event) => {
          const scenario = props.scenarios.find((item) => item.id === event.target.value);
          if (scenario) props.onSourceScenarioChange(scenario);
        }}
        disabled={props.scenarios.length === 0 || props.saving}
      >
        <option value="" disabled>
          Select scenario
        </option>
        {props.scenarios.map((scenario, index) => (
          <option key={scenarioRowKey(scenario, index)} value={scenario.id}>
            {scenario.name}
          </option>
        ))}
      </select>
      <label className="form-label form-label--required" htmlFor="fork-source-state">
        Source state
      </label>
      <select
        id="fork-source-state"
        className="select"
        value={props.orgState?.id ?? ""}
        onChange={(event) => {
          const orgState = props.orgStates.find((item) => item.id === event.target.value);
          if (orgState) props.onSourceOrgStateChange(orgState);
        }}
        disabled={!props.scenario || props.loadingOrgStates || props.saving}
      >
        <option value="" disabled>
          {props.loadingOrgStates ? "Loading states..." : "Select state"}
        </option>
        {props.orgStates.map((orgState, index) => (
          <option key={orgStateRowKey(orgState, index)} value={orgState.id}>
            {orgState.name} ({orgState.targetDate})
          </option>
        ))}
      </select>
      <ScenarioFields
        idPrefix="fork-scenario"
        name={props.name}
        description={props.description}
        onNameChange={props.onNameChange}
        onDescriptionChange={props.onDescriptionChange}
        disabled={!props.scenario}
        optionalLabels
      />
      <ActionError message={props.error} />
      <div className="form-actions">
        <button className="btn btn--primary" type="submit" disabled={disabled}>
          {props.saving ? "Saving..." : "Fork scenario"}
        </button>
      </div>
    </form>
  );
}

function OrgStateDetail(props: {
  scenario: ScenarioDto | null;
  orgState: OrgStateDto | null;
  editName: string;
  editDescription: string;
  editTargetDate: string;
  deleteConfirmation: string;
  error: string;
  saving: boolean;
  onEditNameChange: (value: string) => void;
  onEditDescriptionChange: (value: string) => void;
  onEditTargetDateChange: (value: string) => void;
  onDeleteConfirmationChange: (value: string) => void;
  onCancel: () => void;
  onEditSubmit: (event: SubmitEvent<HTMLFormElement>) => void;
  onDeleteSubmit: (event: SubmitEvent<HTMLFormElement>) => void;
}) {
  const editedOrgStateName = props.editName.trim();
  const editedOrgStateDescription = props.editDescription.trim();
  const orgStateHasChanges = props.orgState
    ? editedOrgStateName !== props.orgState.name ||
      editedOrgStateDescription !== props.orgState.description ||
      props.editTargetDate !== props.orgState.targetDate
    : false;
  const saveOrgStateDisabled =
    !props.orgState || !editedOrgStateName || !props.editTargetDate || !orgStateHasChanges;

  return (
    <section className="detail-card" aria-labelledby="selected-state-title">
      <div className="detail-card__header">
        <p className="eyebrow">Selected state</p>
        <h2 id="selected-state-title" className="section-title">
          {props.orgState ? props.orgState.name : "No state selected"}
        </h2>
      </div>

      {!props.scenario ? (
        <p className="muted">Select a scenario before working with states.</p>
      ) : !props.orgState ? (
        <p className="muted">Select a state in the side panel.</p>
      ) : (
        <>
          <form onSubmit={props.onEditSubmit}>
            <OrgStateFields
              idPrefix="org-state-edit"
              name={props.editName}
              description={props.editDescription}
              targetDate={props.editTargetDate}
              onNameChange={props.onEditNameChange}
              onDescriptionChange={props.onEditDescriptionChange}
              onTargetDateChange={props.onEditTargetDateChange}
            />
            <ActionError message={props.error} />
            <ActionButtons
              submitLabel="Save state"
              saving={props.saving}
              onCancel={props.onCancel}
              disabled={saveOrgStateDisabled}
            />
          </form>
          <form className="destructive-action-section" onSubmit={props.onDeleteSubmit}>
            <label className="form-label" htmlFor="org-state-delete-confirm">
              Confirmation
            </label>
            <input
              id="org-state-delete-confirm"
              className="input"
              placeholder="Type DELETE to confirm"
              value={props.deleteConfirmation}
              onChange={(event) => props.onDeleteConfirmationChange(event.target.value)}
              autoComplete="off"
            />
            <div className="form-actions">
              <button
                className="btn btn--danger"
                type="submit"
                disabled={props.saving || props.deleteConfirmation !== "DELETE"}
              >
                {props.saving ? "Deleting..." : "Delete state"}
              </button>
            </div>
          </form>
        </>
      )}
    </section>
  );
}

function CreateOrgStateForm(props: {
  scenario: ScenarioDto | null;
  name: string;
  description: string;
  targetDate: string;
  error: string;
  saving: boolean;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onTargetDateChange: (value: string) => void;
  onSubmit: (event: SubmitEvent<HTMLFormElement>) => void;
}) {
  return (
    <form className="detail-card" aria-labelledby="create-state-title" onSubmit={props.onSubmit}>
      <div className="detail-card__header">
        <h2 id="create-state-title" className="section-title">
          Create state
        </h2>
      </div>
      <p className="muted">
        {props.scenario
          ? `Create a state in ${props.scenario.name}.`
          : "Select a scenario before creating a state."}
      </p>
      <OrgStateFields
        idPrefix="org-state-create"
        name={props.name}
        targetDate={props.targetDate}
        description={props.description}
        onNameChange={props.onNameChange}
        onDescriptionChange={props.onDescriptionChange}
        onTargetDateChange={props.onTargetDateChange}
        disabled={!props.scenario}
      />
      <ActionError message={props.error} />
      <div className="form-actions">
        <button
          className="btn btn--primary"
          type="submit"
          disabled={!props.scenario || !props.name.trim() || !props.targetDate || props.saving}
        >
          {props.saving ? "Saving..." : "Create state"}
        </button>
      </div>
    </form>
  );
}

function ScenarioFields(props: {
  idPrefix: string;
  name: string;
  description: string;
  disabled?: boolean;
  optionalLabels?: boolean;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
}) {
  const nameId = `${props.idPrefix}-name`;
  const descriptionId = `${props.idPrefix}-description`;

  return (
    <>
      <label
        className={`form-label${props.optionalLabels ? "" : " form-label--required"}`}
        htmlFor={nameId}
      >
        Name
        {props.optionalLabels ? <span className="form-label__hint">(optional)</span> : null}
      </label>
      <input
        id={nameId}
        className="input"
        value={props.name}
        onChange={(event) => props.onNameChange(event.target.value)}
        disabled={props.disabled}
      />
      <label className="form-label" htmlFor={descriptionId}>
        Description
        {props.optionalLabels ? <span className="form-label__hint">(optional)</span> : null}
      </label>
      <textarea
        id={descriptionId}
        className="textarea"
        value={props.description}
        onChange={(event) => props.onDescriptionChange(event.target.value)}
        disabled={props.disabled}
      />
    </>
  );
}

function OrgStateFields(props: {
  idPrefix: string;
  name: string;
  targetDate: string;
  description: string;
  disabled?: boolean;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onTargetDateChange: (value: string) => void;
}) {
  const nameId = `${props.idPrefix}-name`;
  const descriptionId = `${props.idPrefix}-description`;
  const targetDateId = `${props.idPrefix}-target-date`;

  return (
    <>
      <label className="form-label form-label--required" htmlFor={nameId}>
        Name
      </label>
      <input
        id={nameId}
        className="input"
        value={props.name}
        onChange={(event) => props.onNameChange(event.target.value)}
        disabled={props.disabled}
      />
      <label className="form-label form-label--required" htmlFor={targetDateId}>
        Target date
      </label>
      <input
        id={targetDateId}
        className="input date-input"
        type="date"
        value={props.targetDate}
        onChange={(event) => props.onTargetDateChange(event.target.value)}
        disabled={props.disabled}
      />
      <label className="form-label" htmlFor={descriptionId}>
        Description
      </label>
      <textarea
        id={descriptionId}
        className="textarea"
        value={props.description}
        onChange={(event) => props.onDescriptionChange(event.target.value)}
        disabled={props.disabled}
      />
    </>
  );
}

function ActionError(props: { message: string }) {
  if (!props.message) return null;
  return (
    <div className="alert alert--danger" role="alert">
      <p className="alert__title">Action error</p>
      <p className="alert__text">{props.message}</p>
    </div>
  );
}

function ActionButtons(props: {
  submitLabel: string;
  saving: boolean;
  disabled?: boolean;
  onCancel: () => void;
}) {
  return (
    <div className="form-actions">
      <button className="btn btn--primary" type="submit" disabled={props.saving || props.disabled}>
        {props.saving ? "Saving..." : props.submitLabel}
      </button>
    </div>
  );
}
