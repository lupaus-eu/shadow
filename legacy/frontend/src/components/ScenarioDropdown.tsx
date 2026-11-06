import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { fetchOrgStates, fetchScenarios } from "../api/scenarios";
import type { OrgStateDto, ScenarioDto } from "../api/scenarios";
import { useWorkspaceSelection } from "../workspace/WorkspaceSelectionContext";
import Alert from "./Alert";

function sortOrgStates(items: OrgStateDto[]): OrgStateDto[] {
  return [...items].sort((left, right) => left.targetDate.localeCompare(right.targetDate));
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

export default function ScenarioDropdown(props: { orgId: string }) {
  const { selectedScenario, selectedOrgState, setWorkspaceSelection } = useWorkspaceSelection();
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const focusFirstOptionRef = useRef(false);

  const [open, setOpen] = useState(false);
  const [scenarios, setScenarios] = useState<ScenarioDto[]>([]);
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [scenarioError, setScenarioError] = useState("");
  const [scenarioRetry, setScenarioRetry] = useState(0);
  const [draftScenarioId, setDraftScenarioId] = useState("");
  const [orgStates, setOrgStates] = useState<OrgStateDto[]>([]);
  const [loadingOrgStates, setLoadingOrgStates] = useState(false);
  const [orgStateError, setOrgStateError] = useState("");
  const [orgStateRetry, setOrgStateRetry] = useState(0);
  const [draftOrgStateId, setDraftOrgStateId] = useState("");

  const resetDraft = useCallback(() => {
    setScenarios([]);
    setLoadingScenarios(false);
    setScenarioError("");
    setDraftScenarioId("");
    setOrgStates([]);
    setLoadingOrgStates(false);
    setOrgStateError("");
    setDraftOrgStateId("");
  }, []);

  const closeDropdown = useCallback(
    (restoreFocus: boolean) => {
      focusFirstOptionRef.current = false;
      setOpen(false);
      resetDraft();
      if (restoreFocus) queueMicrotask(() => triggerRef.current?.focus());
    },
    [resetDraft]
  );

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) {
        closeDropdown(false);
      }
    }

    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeDropdown(true);
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [closeDropdown, open]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let ignore = false;

    async function loadScenarios() {
      try {
        setLoadingScenarios(true);
        setScenarioError("");
        const items = await fetchScenarios(props.orgId, controller.signal);
        if (ignore) return;
        setScenarios(items);
        const activeScenario = selectedScenario
          ? items.find((item) => item.id === selectedScenario.id)
          : null;
        setDraftScenarioId(activeScenario?.id ?? items[0]?.id ?? "");
      } catch (error) {
        if (ignore || (error as { name?: string }).name === "AbortError") return;
        setScenarios([]);
        setDraftScenarioId("");
        setScenarioError(messageFromError(error));
      } finally {
        if (!ignore) setLoadingScenarios(false);
      }
    }

    void loadScenarios();
    return () => {
      ignore = true;
      controller.abort();
    };
  }, [open, props.orgId, scenarioRetry, selectedScenario]);

  useEffect(() => {
    if (!open || !draftScenarioId) return;
    const controller = new AbortController();
    let ignore = false;
    const activeDraftScenarioId = draftScenarioId;

    async function loadOrgStates() {
      try {
        setLoadingOrgStates(true);
        setOrgStateError("");
        setOrgStates([]);
        setDraftOrgStateId("");
        const items = sortOrgStates(
          await fetchOrgStates(props.orgId, activeDraftScenarioId, controller.signal)
        );
        if (ignore) return;
        setOrgStates(items);
        const activeOrgState =
          selectedScenario?.id === activeDraftScenarioId && selectedOrgState
            ? items.find((item) => item.id === selectedOrgState.id)
            : null;
        setDraftOrgStateId(activeOrgState?.id ?? items[0]?.id ?? "");
      } catch (error) {
        if (ignore || (error as { name?: string }).name === "AbortError") return;
        setOrgStates([]);
        setDraftOrgStateId("");
        setOrgStateError(messageFromError(error));
      } finally {
        if (!ignore) setLoadingOrgStates(false);
      }
    }

    void loadOrgStates();
    return () => {
      ignore = true;
      controller.abort();
    };
  }, [draftScenarioId, open, orgStateRetry, props.orgId, selectedOrgState, selectedScenario?.id]);

  function chooseDraftScenario(scenarioId: string) {
    if (scenarioId === draftScenarioId) return;
    setOrgStates([]);
    setDraftOrgStateId("");
    setOrgStateError("");
    setDraftScenarioId(scenarioId);
  }

  useEffect(() => {
    if (!open || !focusFirstOptionRef.current || scenarios.length === 0) return;
    focusFirstOptionRef.current = false;
    panelRef.current?.querySelector<HTMLButtonElement>("[data-scenario-option]")?.focus();
  }, [open, scenarios]);

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    focusFirstOptionRef.current = true;
    setOpen(true);
  }

  function commitSelection() {
    const scenario = scenarios.find((item) => item.id === draftScenarioId);
    const orgState = orgStates.find((item) => item.id === draftOrgStateId);
    if (!scenario || !orgState || loadingScenarios || loadingOrgStates) return;

    if (scenario.id !== selectedScenario?.id || orgState.id !== selectedOrgState?.id) {
      setWorkspaceSelection(
        { id: scenario.id, name: scenario.name },
        {
          id: orgState.id,
          name: orgState.name,
          targetDate: orgState.targetDate
        }
      );
    }
    closeDropdown(false);
  }

  const displayedName = selectedScenario?.name ?? "None";
  const canCommit = Boolean(
    draftScenarioId && draftOrgStateId && !loadingScenarios && !loadingOrgStates
  );

  return (
    <div className="dropdown-shell context-dropdown scenario-dropdown" ref={rootRef}>
      <button
        ref={triggerRef}
        className="context-chip context-chip--interactive dropdown-trigger context-dropdown__trigger"
        type="button"
        title={`Scenario: ${displayedName}`}
        aria-label="Change scenario"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => (open ? closeDropdown(false) : setOpen(true))}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="context-chip__label" aria-hidden="true">
          Scenario
        </span>
        <span className="context-chip__value">{displayedName}</span>
        <ChevronIcon />
      </button>

      {open ? (
        <div
          id={panelId}
          className="dropdown-panel scenario-dropdown__panel"
          role="dialog"
          aria-label="Scenario and org state selector"
          ref={panelRef}
        >
          <div className="scenario-dropdown__columns">
            <section className="scenario-dropdown__column" aria-label="Scenarios">
              <p className="eyebrow context-dropdown__heading">Scenarios</p>
              {loadingScenarios ? (
                <p className="muted context-dropdown__message">Loading scenarios...</p>
              ) : null}
              {!loadingScenarios && !scenarioError && scenarios.length === 0 ? (
                <p className="muted context-dropdown__message">No scenarios available.</p>
              ) : null}
              {scenarioError ? (
                <LoadError
                  title="Scenario load error"
                  message={scenarioError}
                  onRetry={() => setScenarioRetry((value) => value + 1)}
                />
              ) : null}
              <div className="context-dropdown__options">
                {scenarios.map((scenario) => {
                  const isActive = scenario.id === selectedScenario?.id;
                  const isDraft = scenario.id === draftScenarioId;
                  return (
                    <button
                      key={scenario.id}
                      className={`dropdown-option context-dropdown__option${
                        isDraft ? " context-dropdown__option--selected" : ""
                      }`}
                      type="button"
                      data-scenario-option
                      aria-pressed={isDraft}
                      onClick={() => chooseDraftScenario(scenario.id)}
                    >
                      <span className="context-dropdown__option-name">{scenario.name}</span>
                      {isActive ? <span className="context-dropdown__status">Active</span> : null}
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="scenario-dropdown__column" aria-label="Scenario org states">
              <p className="eyebrow context-dropdown__heading">Org states</p>
              {loadingOrgStates ? (
                <p className="muted context-dropdown__message">Loading org states...</p>
              ) : null}
              {!loadingOrgStates && draftScenarioId && !orgStateError && orgStates.length === 0 ? (
                <p className="muted context-dropdown__message">No org states available.</p>
              ) : null}
              {orgStateError ? (
                <LoadError
                  title="Org state load error"
                  message={orgStateError}
                  onRetry={() => setOrgStateRetry((value) => value + 1)}
                />
              ) : null}
              <div className="context-dropdown__options">
                {orgStates.map((orgState) => {
                  const isActive =
                    draftScenarioId === selectedScenario?.id &&
                    orgState.id === selectedOrgState?.id;
                  const isDraft = orgState.id === draftOrgStateId;
                  return (
                    <button
                      key={orgState.id}
                      className={`dropdown-option context-dropdown__option${
                        isDraft ? " context-dropdown__option--selected" : ""
                      }`}
                      type="button"
                      aria-pressed={isDraft}
                      onClick={() => setDraftOrgStateId(orgState.id)}
                    >
                      <span className="context-dropdown__option-copy">
                        <span className="context-dropdown__option-name">{orgState.name}</span>
                        <span className="context-dropdown__option-meta">{orgState.targetDate}</span>
                      </span>
                      {isActive ? <span className="context-dropdown__status">Active</span> : null}
                    </button>
                  );
                })}
              </div>
            </section>
          </div>

          <div className="context-dropdown__footer">
            <button
              className="btn btn--primary"
              type="button"
              disabled={!canCommit}
              onClick={commitSelection}
            >
              Select
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function LoadError(props: { title: string; message: string; onRetry: () => void }) {
  return (
    <Alert
      key={props.message}
      variant="danger"
      role="alert"
      className="context-dropdown__alert"
      title={props.title}
      message={props.message}
      onRetry={props.onRetry}
    />
  );
}

function ChevronIcon() {
  return (
    <svg className="dropdown-chevron" viewBox="0 0 24 24" aria-hidden="true">
      <path d="m7 10 5 5 5-5" />
    </svg>
  );
}
