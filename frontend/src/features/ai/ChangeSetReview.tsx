import { useCallback, useEffect, useId, useRef, useState } from "react";
import { AiApiError, applyAiChangeSet, fetchAiChangeSet, rejectAiChangeSet } from "../../api/ai";
import type {
  AiChangeSetApplyDto,
  AiChangeSetDetailDto,
  AiChangeSetOperationDto
} from "../../api/ai";
import ChangeSetStatusBadge from "./ChangeSetStatusBadge";
import SelfDeclaredClientName from "./SelfDeclaredClientName";
import Sparkline from "./Sparkline";
import { changeSetStatusLabel, formatAiTimestamp } from "./aiPresentation";
import {
  changeSetNames,
  describeOperation,
  formatFieldValue,
  operationTargets,
  operationValues,
  patchedFields
} from "./changeSetOperations";
import type { ChangeSetNames, OperationValue } from "./changeSetOperations";
import Alert from "../../components/Alert";

const MAX_VALUE_ROWS = 1_000;

type ReviewAction = "apply" | "reject";

type ReviewNotice =
  | { kind: "stale" }
  | { kind: "busy"; action: ReviewAction; message: string }
  | { kind: "conflict"; message: string }
  | { kind: "error"; message: string }
  | { kind: "applied"; result: AiChangeSetApplyDto }
  | { kind: "rejected" };

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function isMissingTarget(operation: AiChangeSetOperationDto): boolean {
  return operation.replaces?.missing === true;
}

// A retryable error leaves the change set untouched: `apply_in_progress` while
// another transaction (normally a concurrent apply) holds it, or a `503`.
function busyMessage(error: AiApiError): string | null {
  if (error.status === 409 && error.code === "apply_in_progress") {
    return "The change set is busy, normally because another apply is running. Nothing was changed.";
  }
  if (error.status === 503) {
    return "The server was busy and nothing was changed.";
  }
  return null;
}

// Reviews one change set. The replacement flags come from the detail, which
// recomputes them against current data; apply sends back the shown review's
// `reviewFingerprint`, so data that changed since the review loaded is
// reported as `review_stale` instead of being replaced unseen.
export default function ChangeSetReview(props: {
  orgId: string;
  changeSetKey: string;
  unsavedMetricRows: number;
  onBack: () => void;
  onApplied: (result: AiChangeSetApplyDto) => void;
}) {
  const [detail, setDetail] = useState<AiChangeSetDetailDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [confirming, setConfirming] = useState<ReviewAction | null>(null);
  const [pending, setPending] = useState<ReviewAction | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const [notice, setNotice] = useState<ReviewNotice | null>(null);
  const requestController = useRef<AbortController | null>(null);
  const titleId = useId();
  const applyTextId = useId();
  const noteId = useId();

  const loadDetail = useCallback(async () => {
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;

    try {
      setLoading(true);
      setLoadError("");
      const item = await fetchAiChangeSet(props.orgId, props.changeSetKey, controller.signal);
      if (requestController.current !== controller) return;
      setDetail(item);
    } catch (error) {
      if (requestController.current !== controller) return;
      if ((error as { name?: string }).name === "AbortError") return;
      setLoadError(
        error instanceof AiApiError && error.status === 404
          ? "This change set does not exist in this organisation."
          : messageFromError(error)
      );
    } finally {
      if (requestController.current === controller) {
        requestController.current = null;
        setLoading(false);
      }
    }
  }, [props.changeSetKey, props.orgId]);

  useEffect(() => {
    async function loadInitialDetail() {
      await loadDetail();
    }

    void loadInitialDetail();
    return () => {
      requestController.current?.abort();
      requestController.current = null;
    };
  }, [loadDetail]);

  function startAction(action: ReviewAction) {
    setConfirming(action);
    setNotice(null);
  }

  function cancelAction() {
    setConfirming(null);
    setRejectNote("");
  }

  async function apply(reviewFingerprint: string) {
    try {
      setPending("apply");
      setNotice(null);
      const result = await applyAiChangeSet(props.orgId, props.changeSetKey, reviewFingerprint);
      setDetail((current) => (current ? { ...current, ...result.changeSet } : current));
      setConfirming(null);
      setNotice({ kind: "applied", result });
      props.onApplied(result);
    } catch (error) {
      if (error instanceof AiApiError) {
        if (error.status === 409 && error.code === "review_stale") {
          // The replaced data changed: show the recomputed review and require
          // a fresh confirmation.
          setConfirming(null);
          await loadDetail();
          setNotice({ kind: "stale" });
          return;
        }
        const busy = busyMessage(error);
        if (busy) {
          // Retryable: keep the shown review and its fingerprint.
          setConfirming(null);
          setNotice({ kind: "busy", action: "apply", message: busy });
          return;
        }
        if (error.status === 409) {
          // Terminal: the change set is no longer submitted (or the apply
          // failed and marked it failed). Show its current status.
          setConfirming(null);
          await loadDetail();
          setNotice({ kind: "conflict", message: error.message });
          return;
        }
      }
      setNotice({ kind: "error", message: messageFromError(error) });
    } finally {
      setPending(null);
    }
  }

  async function reject() {
    try {
      setPending("reject");
      setNotice(null);
      const item = await rejectAiChangeSet(
        props.orgId,
        props.changeSetKey,
        rejectNote.trim() || null
      );
      setDetail((current) => (current ? { ...current, ...item } : current));
      setConfirming(null);
      setRejectNote("");
      setNotice({ kind: "rejected" });
    } catch (error) {
      if (error instanceof AiApiError) {
        const busy = busyMessage(error);
        if (busy) {
          // Keeps the note for "Try again".
          setConfirming(null);
          setNotice({ kind: "busy", action: "reject", message: busy });
          return;
        }
        if (error.status === 409) {
          setConfirming(null);
          setRejectNote("");
          await loadDetail();
          setNotice({ kind: "conflict", message: error.message });
          return;
        }
      }
      setNotice({ kind: "error", message: messageFromError(error) });
    } finally {
      setPending(null);
    }
  }

  function retry(action: ReviewAction) {
    if (action === "apply" && detail) void apply(detail.reviewFingerprint);
    if (action === "reject") void reject();
  }

  const names = detail ? changeSetNames(detail.operations) : null;
  const replacingCount = detail
    ? detail.operations.filter((operation) => operation.replacesExisting).length
    : 0;
  const missingCount = detail ? detail.operations.filter(isMissingTarget).length : 0;
  const busy = pending !== null || loading;

  return (
    <section className="ai-panel-review" aria-labelledby={titleId} aria-busy={loading}>
      <div className="ai-panel__section-header">
        <button className="btn btn--secondary btn--compact" type="button" onClick={props.onBack}>
          Back to change sets
        </button>
        <button
          className="btn btn--secondary btn--compact"
          type="button"
          onClick={() => void loadDetail()}
          disabled={busy}
        >
          {loading ? "Reloading..." : "Reload"}
        </button>
      </div>

      {loading && !detail ? <p className="muted">Loading change set...</p> : null}
      {loadError ? (
        <Alert
          key={loadError}
          variant="danger"
          role="alert"
          title="Change set API error"
          message={loadError}
          onRetry={() => void loadDetail()}
          retryDisabled={loading}
        />
      ) : null}

      {detail && names ? (
        <>
          <div className="ai-panel-review__header">
            <h3 id={titleId} className="ai-panel-review__title">
              <bdi>{detail.title}</bdi>
            </h3>
            <ChangeSetStatusBadge status={detail.status} />
          </div>
          {detail.rationale ? (
            <p className="ai-panel-review__rationale">
              <bdi>{detail.rationale}</bdi>
            </p>
          ) : null}

          <dl className="detail-meta">
            <div className="detail-meta__row">
              <dt>Change set</dt>
              <dd className="metadata-code">{detail.id}</dd>
            </div>
            <div className="detail-meta__row">
              <dt>Scenario</dt>
              <dd>
                {detail.scenarioKey ? (
                  <code className="metadata-code">{detail.scenarioKey}</code>
                ) : (
                  "No single scenario"
                )}
              </dd>
            </div>
            <div className="detail-meta__row">
              <dt>Created by</dt>
              <dd>
                <bdi>{detail.createdByName}</bdi>, {formatAiTimestamp(detail.createdTime)}
              </dd>
            </div>
            <div className="detail-meta__row">
              <dt>AI client</dt>
              <dd className="ai-panel-review__client">
                <code className="metadata-code">{detail.clientId}</code>
                <SelfDeclaredClientName name={detail.clientName} />
              </dd>
            </div>
            {detail.reviewedByName && detail.reviewedTime ? (
              <div className="detail-meta__row">
                <dt>Reviewed by</dt>
                <dd>
                  <bdi>{detail.reviewedByName}</bdi>, {formatAiTimestamp(detail.reviewedTime)}
                </dd>
              </div>
            ) : null}
            {detail.reviewedVia === "mcp" && detail.reviewClientId && detail.reviewClientName ? (
              <div className="detail-meta__row">
                <dt>Reviewed through</dt>
                <dd className="ai-panel-review__client">
                  AI client (MCP) <code className="metadata-code">{detail.reviewClientId}</code>
                  <SelfDeclaredClientName name={detail.reviewClientName} />
                </dd>
              </div>
            ) : null}
            {detail.reviewNote ? (
              <div className="detail-meta__row">
                <dt>Review note</dt>
                <dd>
                  <bdi>{detail.reviewNote}</bdi>
                </dd>
              </div>
            ) : null}
          </dl>

          <ReviewNoticeView
            notice={notice}
            status={detail.status}
            pending={pending}
            onRetry={retry}
            onDismiss={() => setNotice(null)}
          />

          <ValidationErrors detail={detail} />

          <h4 className="ai-panel__section-title">Operations ({detail.operations.length})</h4>
          <ol className="ai-panel-operations" aria-label="Change set operations">
            {detail.operations.map((operation) => (
              <OperationItem key={operation.position} operation={operation} names={names} />
            ))}
          </ol>

          {detail.status === "submitted" ? (
            <div className="ai-panel-review__actions">
              <ReplacementSummary
                replacingCount={replacingCount}
                missingCount={missingCount}
                operationCount={detail.operations.length}
              />
              {confirming === "apply" ? (
                <div
                  className="delete-confirmation"
                  role="alertdialog"
                  aria-label="Confirm apply"
                  aria-describedby={applyTextId}
                >
                  <p id={applyTextId}>
                    Apply all {detail.operations.length} operation(s) to Shadow?
                    {replacingCount > 0
                      ? ` ${replacingCount} of them replace existing data.`
                      : ""}{" "}
                    The changes are applied together or not at all.
                    {props.unsavedMetricRows > 0
                      ? ` The metrics grid has unsaved changes in ${props.unsavedMetricRows} timeserie(s); the grid reloads after the apply and discards them. Save them first to keep them.`
                      : ""}
                  </p>
                  <div className="form-actions">
                    <button
                      className="btn btn--secondary btn--compact"
                      type="button"
                      onClick={cancelAction}
                      disabled={busy}
                    >
                      Cancel
                    </button>
                    <button
                      className="btn btn--primary btn--compact"
                      type="button"
                      onClick={() => void apply(detail.reviewFingerprint)}
                      disabled={busy}
                    >
                      {pending === "apply" ? "Applying..." : "Confirm apply"}
                    </button>
                  </div>
                </div>
              ) : confirming === "reject" ? (
                <div className="delete-confirmation" role="alertdialog" aria-label="Confirm reject">
                  <label className="form-label" htmlFor={noteId}>
                    Note (optional)
                  </label>
                  <textarea
                    id={noteId}
                    className="input ai-panel-review__note"
                    value={rejectNote}
                    maxLength={2000}
                    rows={3}
                    disabled={busy}
                    onChange={(event) => setRejectNote(event.target.value)}
                  />
                  <p>Reject this change set? Nothing is applied and it cannot be applied later.</p>
                  <div className="form-actions">
                    <button
                      className="btn btn--secondary btn--compact"
                      type="button"
                      onClick={cancelAction}
                      disabled={busy}
                    >
                      Cancel
                    </button>
                    <button
                      className="btn btn--danger btn--compact"
                      type="button"
                      onClick={() => void reject()}
                      disabled={busy}
                    >
                      {pending === "reject" ? "Rejecting..." : "Confirm reject"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="form-actions">
                  <button
                    className="btn btn--primary btn--compact"
                    type="button"
                    onClick={() => startAction("apply")}
                    disabled={busy}
                  >
                    Apply
                  </button>
                  <button
                    className="btn btn--secondary btn--compact"
                    type="button"
                    onClick={() => startAction("reject")}
                    disabled={busy}
                  >
                    Reject
                  </button>
                </div>
              )}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function ReviewNoticeView(props: {
  notice: ReviewNotice | null;
  status: AiChangeSetDetailDto["status"];
  pending: ReviewAction | null;
  onRetry: (action: ReviewAction) => void;
  onDismiss: () => void;
}) {
  const { notice } = props;
  if (!notice) return null;

  if (notice.kind === "applied") {
    const changed = notice.result.operations.filter((operation) => operation.key);
    const refs = Object.entries(notice.result.refs);
    return (
      <Alert
        variant="info"
        role="status"
        title="Change set applied"
        message="The metrics grid was reloaded. Created or changed keys:"
        onDismiss={props.onDismiss}
      >
        <ul className="ai-panel-review__keys" aria-label="Created or changed keys">
          {changed.map((operation) => (
            <li key={operation.position}>
              #{operation.position} {operation.opType}:{" "}
              <code className="metadata-code">{operation.key}</code>
              {operation.scenarioKey && operation.scenarioKey !== operation.key ? (
                <>
                  {" "}
                  in scenario <code className="metadata-code">{operation.scenarioKey}</code>
                </>
              ) : null}
            </li>
          ))}
          {refs.map(([symbol, key]) => (
            <li key={symbol}>
              <code className="metadata-code">{symbol}</code> ={" "}
              <code className="metadata-code">{key}</code>
            </li>
          ))}
        </ul>
      </Alert>
    );
  }

  if (notice.kind === "rejected") {
    return (
      <Alert
        variant="info"
        role="status"
        title="Change set rejected"
        message="Nothing was applied."
        onDismiss={props.onDismiss}
      />
    );
  }

  if (notice.kind === "stale") {
    return (
      <Alert
        variant="danger"
        role="alert"
        title="The replaced data changed"
        message={
          "The data this change set replaces changed after the review was loaded, so nothing " +
          "was applied. The review now shows the current data; check the warnings and confirm again."
        }
        onDismiss={props.onDismiss}
      />
    );
  }

  if (notice.kind === "busy") {
    return (
      <Alert
        variant="danger"
        role="alert"
        title={notice.action === "apply" ? "Apply did not run" : "Reject did not run"}
        message={`${notice.message} Try again shortly.`}
        onDismiss={props.onDismiss}
      >
        <div className="form-actions">
          <button
            className="btn btn--secondary btn--compact"
            type="button"
            onClick={() => props.onRetry(notice.action)}
            disabled={props.pending !== null}
          >
            Try again
          </button>
        </div>
      </Alert>
    );
  }

  if (notice.kind === "conflict") {
    return (
      <Alert
        variant="danger"
        role="alert"
        title={`The change set is ${changeSetStatusLabel(props.status).toLowerCase()}`}
        message={notice.message}
        onDismiss={props.onDismiss}
      />
    );
  }

  return (
    <Alert
      variant="danger"
      role="alert"
      title="Review action failed"
      message={notice.message}
      onDismiss={props.onDismiss}
    />
  );
}

function ReplacementSummary(props: {
  replacingCount: number;
  missingCount: number;
  operationCount: number;
}) {
  return (
    <div className="ai-panel-review__summary" aria-label="Apply summary">
      <p>
        {props.replacingCount > 0 ? (
          <>
            <span className="badge ai-panel-badge ai-panel-badge--warning">Replaces data</span>{" "}
            {props.replacingCount} of {props.operationCount} operation(s) replace existing data.
          </>
        ) : (
          "No operation replaces existing data."
        )}
      </p>
      {props.missingCount > 0 ? (
        <p>
          <span className="badge ai-panel-badge ai-panel-badge--danger">Target missing</span>{" "}
          {props.missingCount} operation(s) target data that no longer exists. Apply will fail
          re-validation.
        </p>
      ) : null}
    </div>
  );
}

function validationErrorsKey(
  operationErrors: AiChangeSetOperationDto[],
  applyErrorMessage: string
): string {
  return JSON.stringify([
    applyErrorMessage,
    operationErrors.map((operation) => [operation.position, operation.error?.message])
  ]);
}

function ValidationErrors(props: { detail: AiChangeSetDetailDto }) {
  const { detail } = props;
  const operationErrors = detail.operations.filter((operation) => operation.error);
  const applyError =
    detail.appliedResult?.status === "failed" ? (detail.appliedResult.error ?? null) : null;
  if (operationErrors.length === 0 && !applyError && detail.validationResult?.ok !== false) {
    return null;
  }

  // The errors come from the loaded change set, so the alert hides itself until they change.
  return (
    <Alert
      key={validationErrorsKey(operationErrors, applyError?.message ?? "")}
      variant="danger"
      role="region"
      ariaLabel="Validation errors"
      title="Validation errors"
    >
      {applyError ? (
        <p className="alert__text">
          Apply failed
          {detail.appliedResult?.step ? ` in step ${detail.appliedResult.step}` : ""}:{" "}
          {applyError.message}
        </p>
      ) : null}
      {operationErrors.length > 0 ? (
        <ul className="ai-panel-review__errors">
          {operationErrors.map((operation) => (
            <li key={operation.position}>
              #{operation.position} {operation.type}: {operation.error?.message}
            </li>
          ))}
        </ul>
      ) : !applyError ? (
        <p className="alert__text">The latest validation of this change set failed.</p>
      ) : null}
    </Alert>
  );
}

function OperationItem(props: { operation: AiChangeSetOperationDto; names: ChangeSetNames }) {
  const { operation } = props;
  const titleId = useId();
  const description = describeOperation(operation, props.names);
  const values = operationValues(operation);
  const fields = patchedFields(operation);
  const missing = isMissingTarget(operation);
  const replaces = operation.replaces;

  return (
    <li
      className={`ai-panel-operation${
        operation.replacesExisting ? " ai-panel-operation--replaces" : ""
      }${missing ? " ai-panel-operation--missing" : ""}`}
      aria-labelledby={titleId}
    >
      <p id={titleId} className="ai-panel-operation__title">
        <span className="ai-panel-operation__position">#{operation.position}</span>{" "}
        {description.action}{" "}
        {description.subjects.map((subject, index) => (
          <span key={index}>
            {index > 0 ? " → " : null}
            <bdi className="ai-panel-operation__subject">{subject}</bdi>
          </span>
        ))}
        {description.qualifier ? (
          <>
            {" "}
            (<bdi>{description.qualifier}</bdi>)
          </>
        ) : null}
      </p>

      {operation.replacesExisting || missing ? (
        <div className="ai-panel-operation__badges">
          {operation.replacesExisting ? (
            <span className="badge ai-panel-badge ai-panel-badge--warning">
              Replaces existing data
            </span>
          ) : null}
          {missing ? (
            <span className="badge ai-panel-badge ai-panel-badge--danger">Target missing</span>
          ) : null}
        </div>
      ) : null}

      <p className="ai-panel-operation__targets">
        <code className="metadata-code">{operation.type}</code>
        {operationTargets(operation).map(([label, value]) => (
          <span key={label}>
            {" "}
            · {label} <code className="metadata-code">{value}</code>
          </span>
        ))}
      </p>

      {missing ? (
        <p className="ai-panel-operation__missing">
          The target was deleted after the change set was submitted
          {replaces?.message ? `: ${replaces.message}` : "."} Apply will fail re-validation.
        </p>
      ) : null}

      {operation.replacesExisting && replaces?.kind === "timeserie" && !missing ? (
        <p className="ai-panel-operation__replaces">
          Replaces {replaces.valueCount ?? 0} existing value(s)
          {replaces.firstDate && replaces.lastDate
            ? ` from ${replaces.firstDate} to ${replaces.lastDate}`
            : ""}
          .
        </p>
      ) : null}

      {fields.length > 0 ? (
        <table className="ai-panel-table" aria-label="Patched fields">
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">Current</th>
              <th scope="col">Proposed</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((field) => (
              <tr key={field.field}>
                <th scope="row">{field.field}</th>
                <td>
                  <bdi>{formatFieldValue(field.current)}</bdi>
                </td>
                <td>
                  <bdi>{formatFieldValue(field.proposed)}</bdi>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {operation.type === "generate_timeserie_values" && operation.frozenValues && !values ? (
        <p className="muted">
          {operation.frozenValues.valueCount} generated value(s)
          {operation.frozenValues.firstDate && operation.frozenValues.lastDate
            ? ` from ${operation.frozenValues.firstDate} to ${operation.frozenValues.lastDate}`
            : ""}
          ; too many to show here.
        </p>
      ) : null}

      {values ? <TimeserieValues values={values} subject={description.subjects[0] ?? ""} /> : null}

      {operation.error ? (
        <p className="ai-panel-operation__error">
          {operation.error.code}: {operation.error.message}
        </p>
      ) : null}
    </li>
  );
}

function TimeserieValues(props: { values: OperationValue[]; subject: string }) {
  const shown = props.values.slice(0, MAX_VALUE_ROWS);

  return (
    <div className="ai-panel-values">
      <Sparkline values={props.values} />
      {props.values.length > 0 ? (
        <div className="ai-panel-values__scroll">
          <table className="ai-panel-table" aria-label={`Values of ${props.subject}`}>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Value</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((item, index) => (
                <tr key={`${index}:${item.date}`}>
                  <td>
                    <time dateTime={item.date}>{item.date}</time>
                  </td>
                  <td>{String(item.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No values; the timeserie's values are cleared.</p>
      )}
      {props.values.length > shown.length ? (
        <p className="muted">
          Showing the first {shown.length} of {props.values.length} values.
        </p>
      ) : null}
    </div>
  );
}
