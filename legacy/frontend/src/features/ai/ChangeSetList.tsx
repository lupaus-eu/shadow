import { useCallback, useEffect, useId, useRef, useState } from "react";
import { fetchAiChangeSets } from "../../api/ai";
import type { AiChangeSetListItemDto } from "../../api/ai";
import type { WorkspaceScenarioSummary } from "../../workspace/WorkspaceSelectionContext";
import ChangeSetStatusBadge from "./ChangeSetStatusBadge";
import { formatAiTimestamp } from "./aiPresentation";
import Alert from "../../components/Alert";

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

// The organisation's change sets, newest first. With a selected scenario it
// shows by default the change sets whose derived scenario reference is that
// scenario plus those without one (they create a scenario or touch several);
// "Show all" lists every change set of the organisation.
export default function ChangeSetList(props: {
  orgId: string;
  scenario: WorkspaceScenarioSummary | null;
  onSelect: (changeSetKey: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const [changeSets, setChangeSets] = useState<AiChangeSetListItemDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const requestController = useRef<AbortController | null>(null);
  const showAllId = useId();
  const scenarioId = props.scenario?.id ?? null;
  const scoped = scenarioId !== null && !showAll;

  const loadChangeSets = useCallback(async () => {
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;

    try {
      setLoading(true);
      setLoadError("");
      const items = await fetchAiChangeSets(
        props.orgId,
        scoped && scenarioId ? { scenarioKey: scenarioId, includeUnscoped: true } : {},
        controller.signal
      );
      if (requestController.current !== controller) return;
      setChangeSets(items);
    } catch (error) {
      if (requestController.current !== controller) return;
      if ((error as { name?: string }).name === "AbortError") return;
      setChangeSets([]);
      setLoadError(messageFromError(error));
    } finally {
      if (requestController.current === controller) {
        requestController.current = null;
        setLoading(false);
      }
    }
  }, [props.orgId, scenarioId, scoped]);

  useEffect(() => {
    async function loadInitialChangeSets() {
      await loadChangeSets();
    }

    void loadInitialChangeSets();
    return () => {
      requestController.current?.abort();
      requestController.current = null;
    };
  }, [loadChangeSets]);

  return (
    <section className="ai-panel-list" aria-labelledby="ai-change-sets-title">
      <div className="ai-panel__section-header">
        <h3 id="ai-change-sets-title" className="ai-panel__section-title">
          Change sets
        </h3>
        <button
          className="btn btn--secondary btn--compact"
          type="button"
          onClick={() => void loadChangeSets()}
          disabled={loading}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {props.scenario ? (
        <div className="ai-panel-list__filter">
          <label className="ai-panel-list__toggle" htmlFor={showAllId}>
            <input
              id={showAllId}
              type="checkbox"
              checked={showAll}
              onChange={(event) => setShowAll(event.target.checked)}
            />
            Show all change sets of the organisation
          </label>
          <p className="muted ai-panel__hint">
            {scoped ? (
              <>
                Showing change sets for <bdi>{props.scenario.name}</bdi> and change sets without a
                single scenario.
              </>
            ) : (
              "Showing every change set of the organisation."
            )}
          </p>
        </div>
      ) : null}

      {loading && changeSets.length === 0 ? <p className="muted">Loading change sets...</p> : null}
      {loadError ? (
        <Alert
          key={loadError}
          variant="danger"
          role="alert"
          title="Change sets API error"
          message={loadError}
          onRetry={() => void loadChangeSets()}
          retryDisabled={loading}
        />
      ) : null}
      {!loading && !loadError && changeSets.length === 0 ? (
        <p className="muted">No change sets.</p>
      ) : null}

      {changeSets.length > 0 ? (
        <ul className="ai-panel-list__items" aria-label="AI change sets">
          {changeSets.map((changeSet) => (
            <li key={changeSet.id} className="ai-panel-list__item">
              <button
                className="ai-panel-list__open"
                type="button"
                onClick={() => props.onSelect(changeSet.id)}
              >
                <span className="ai-panel-list__heading">
                  <bdi className="ai-panel-list__title">{changeSet.title}</bdi>
                  <ChangeSetStatusBadge status={changeSet.status} />
                </span>
                <span className="ai-panel-list__meta">
                  {changeSet.operationCount} operation(s) · <bdi>{changeSet.createdByName}</bdi> ·{" "}
                  {formatAiTimestamp(changeSet.createdTime)}
                </span>
                <span className="ai-panel-list__meta">
                  {changeSet.scenarioKey ? (
                    <>
                      Scenario <code className="metadata-code">{changeSet.scenarioKey}</code>
                    </>
                  ) : (
                    "No single scenario"
                  )}
                </span>
                {changeSet.reviewedVia === "mcp" && changeSet.reviewClientName ? (
                  <span className="ai-panel-list__meta">
                    Reviewed through AI client <bdi>{changeSet.reviewClientName}</bdi> (MCP)
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
