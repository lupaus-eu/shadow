import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { fetchOrgStates } from "../api/scenarios";
import type { OrgStateDto } from "../api/scenarios";
import { useWorkspaceSelection } from "../workspace/WorkspaceSelectionContext";

function sortOrgStates(items: OrgStateDto[]): OrgStateDto[] {
  return [...items].sort((left, right) =>
    left.targetDate.localeCompare(right.targetDate)
  );
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

export default function OrgStateDropdown(props: { orgId: string }) {
  const {
    selectedScenario,
    selectedOrgState,
    setSelectedOrgState
  } = useWorkspaceSelection();
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const focusFirstOptionRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [orgStates, setOrgStates] = useState<OrgStateDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [retryVersion, setRetryVersion] = useState(0);

  const resetOptions = useCallback(() => {
    setOrgStates([]);
    setLoading(false);
    setLoadError("");
  }, []);

  const closeDropdown = useCallback(
    (restoreFocus: boolean) => {
      focusFirstOptionRef.current = false;
      setOpen(false);
      resetOptions();
      if (restoreFocus) queueMicrotask(() => triggerRef.current?.focus());
    },
    [resetOptions]
  );

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      if (
        event.target instanceof Node &&
        !rootRef.current?.contains(event.target)
      ) {
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
    const scenarioId = selectedScenario?.id;
    if (!open || !scenarioId) return;
    const activeScenarioId = scenarioId;
    const controller = new AbortController();
    let ignore = false;

    async function loadOrgStates() {
      try {
        setLoading(true);
        setLoadError("");
        setOrgStates([]);
        const items = sortOrgStates(
          await fetchOrgStates(props.orgId, activeScenarioId, controller.signal)
        );
        if (ignore) return;
        setOrgStates(items);
      } catch (error) {
        if (ignore || (error as { name?: string }).name === "AbortError") return;
        setOrgStates([]);
        setLoadError(messageFromError(error));
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    void loadOrgStates();
    return () => {
      ignore = true;
      controller.abort();
    };
  }, [open, props.orgId, retryVersion, selectedScenario?.id]);

  useEffect(() => {
    if (!open || !focusFirstOptionRef.current || orgStates.length === 0) return;
    focusFirstOptionRef.current = false;
    panelRef.current
      ?.querySelector<HTMLButtonElement>("[data-org-state-option]")
      ?.focus();
  }, [open, orgStates]);

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== "ArrowDown" || !selectedScenario) return;
    event.preventDefault();
    focusFirstOptionRef.current = true;
    setOpen(true);
  }

  function selectOrgState(orgState: OrgStateDto) {
    if (orgState.id !== selectedOrgState?.id) {
      setSelectedOrgState({
        id: orgState.id,
        name: orgState.name,
        targetDate: orgState.targetDate
      });
    }
    closeDropdown(false);
  }

  const displayedValue = selectedOrgState
    ? `${selectedOrgState.name} (${selectedOrgState.targetDate})`
    : "None";

  return (
    <div className="context-dropdown org-state-dropdown" ref={rootRef}>
      <button
        ref={triggerRef}
        className="context-chip context-chip--interactive context-dropdown__trigger"
        type="button"
        title={`Org state: ${displayedValue}`}
        aria-label="Change org state"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        disabled={!selectedScenario}
        onClick={() => {
          if (!selectedScenario) return;
          if (open) closeDropdown(false);
          else setOpen(true);
        }}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="context-chip__label" aria-hidden="true">
          Org state
        </span>
        <span className="context-chip__value">{displayedValue}</span>
        <ChevronIcon />
      </button>

      {open ? (
        <div
          id={panelId}
          className="context-dropdown__panel org-state-dropdown__panel"
          role="dialog"
          aria-label="Org state selector"
          ref={panelRef}
        >
          <p className="eyebrow context-dropdown__heading">Org states</p>
          {loading ? (
            <p className="muted context-dropdown__message">
              Loading org states...
            </p>
          ) : null}
          {!loading && !loadError && orgStates.length === 0 ? (
            <p className="muted context-dropdown__message">
              No org states available.
            </p>
          ) : null}
          {loadError ? (
            <div
              className="alert alert--danger context-dropdown__alert"
              role="alert"
            >
              <p className="alert__title">Org state load error</p>
              <p className="alert__text">{loadError}</p>
              <button
                className="btn btn--secondary"
                type="button"
                onClick={() => setRetryVersion((value) => value + 1)}
              >
                Retry
              </button>
            </div>
          ) : null}
          <div className="context-dropdown__options">
            {orgStates.map((orgState) => {
              const isActive = orgState.id === selectedOrgState?.id;
              return (
                <button
                  key={orgState.id}
                  className={`context-dropdown__option${
                    isActive ? " context-dropdown__option--selected" : ""
                  }`}
                  type="button"
                  data-org-state-option
                  aria-current={isActive ? "true" : undefined}
                  onClick={() => selectOrgState(orgState)}
                >
                  <span className="context-dropdown__option-copy">
                    <span className="context-dropdown__option-name">
                      {orgState.name}
                    </span>
                    <span className="context-dropdown__option-meta">
                      {orgState.targetDate}
                    </span>
                  </span>
                  {isActive ? (
                    <span className="context-dropdown__status">Active</span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ChevronIcon() {
  return (
    <svg
      className="context-dropdown__chevron"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path d="m7 10 5 5 5-5" />
    </svg>
  );
}
