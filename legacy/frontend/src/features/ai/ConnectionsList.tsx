import { useCallback, useEffect, useId, useRef, useState } from "react";
import { AiApiError, fetchAiConnections, revokeAiConnection } from "../../api/ai";
import type { AiConnectionDto } from "../../api/ai";
import SelfDeclaredClientName from "./SelfDeclaredClientName";
import { aiScopeLabel, formatAiTimestamp } from "./aiPresentation";
import Alert from "../../components/Alert";

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

// Lists the signed-in User's active MCP grants. It does not depend on
// `features.mcp`: the connections API stays registered while MCP is disabled,
// so grants stay revocable (ADR-015 incident procedure). `changeSetReview`
// labels a grant with write access as able to apply and reject change sets.
export default function ConnectionsList(props: { changeSetReview?: boolean }) {
  const [connections, setConnections] = useState<AiConnectionDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [confirmingKey, setConfirmingKey] = useState<string | null>(null);
  const [revokingKey, setRevokingKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");
  const requestController = useRef<AbortController | null>(null);

  const loadConnections = useCallback(async () => {
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;

    try {
      setLoading(true);
      setLoadError("");
      const items = await fetchAiConnections(controller.signal);
      if (requestController.current !== controller) return;
      setConnections(items);
    } catch (error) {
      if (requestController.current !== controller) return;
      if ((error as { name?: string }).name === "AbortError") return;
      setLoadError(messageFromError(error));
    } finally {
      if (requestController.current === controller) {
        requestController.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    async function loadInitialConnections() {
      await loadConnections();
    }

    void loadInitialConnections();
    return () => {
      requestController.current?.abort();
      requestController.current = null;
    };
  }, [loadConnections]);

  function refresh() {
    setConfirmingKey(null);
    setActionError("");
    setActionSuccess("");
    void loadConnections();
  }

  function startRevoke(grantKey: string) {
    setConfirmingKey(grantKey);
    setActionError("");
    setActionSuccess("");
  }

  async function confirmRevoke(grantKey: string) {
    try {
      setRevokingKey(grantKey);
      setActionError("");
      setActionSuccess("");
      await revokeAiConnection(grantKey);
      setConnections((items) => items.filter((item) => item.grantKey !== grantKey));
      setConfirmingKey(null);
      setActionSuccess("The connection was revoked. The AI client can no longer use it.");
    } catch (error) {
      if (error instanceof AiApiError && error.status === 404) {
        setConnections((items) => items.filter((item) => item.grantKey !== grantKey));
        setConfirmingKey(null);
        setActionSuccess("The connection had already been revoked or had expired.");
        return;
      }
      setActionError(messageFromError(error));
    } finally {
      setRevokingKey(null);
    }
  }

  const busy = loading || revokingKey !== null;

  return (
    <section className="ai-connections" aria-labelledby="ai-connections-title">
      <div className="ai-connections__header">
        <h2 id="ai-connections-title" className="section-title">
          Connected AI clients
        </h2>
        <button
          className="btn btn--secondary btn--compact"
          type="button"
          onClick={refresh}
          disabled={busy}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {loading && connections.length === 0 ? <p className="muted">Loading connections...</p> : null}
      {loadError ? (
        <Alert
          key={loadError}
          variant="danger"
          role="alert"
          title="Connections API error"
          message={loadError}
          onRetry={refresh}
          retryDisabled={loading}
        />
      ) : null}
      {!loading && !loadError && connections.length === 0 ? (
        <p className="muted">No connected AI clients.</p>
      ) : null}
      {actionError ? (
        <Alert
          variant="danger"
          role="alert"
          title="Revocation failed"
          message={actionError}
          onDismiss={() => setActionError("")}
        />
      ) : null}
      {actionSuccess ? (
        <Alert
          variant="info"
          role="status"
          title="Connection revoked"
          message={actionSuccess}
          onDismiss={() => setActionSuccess("")}
        />
      ) : null}

      {connections.length > 0 ? (
        <ul className="ai-connections__list" aria-label="AI connections">
          {connections.map((connection) => (
            <ConnectionRow
              key={connection.grantKey}
              connection={connection}
              changeSetReview={props.changeSetReview ?? false}
              confirming={confirmingKey === connection.grantKey}
              revoking={revokingKey === connection.grantKey}
              disabled={busy}
              onRevoke={() => startRevoke(connection.grantKey)}
              onCancel={() => setConfirmingKey(null)}
              onConfirm={() => void confirmRevoke(connection.grantKey)}
            />
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function ConnectionRow(props: {
  connection: AiConnectionDto;
  changeSetReview: boolean;
  confirming: boolean;
  revoking: boolean;
  disabled: boolean;
  onRevoke: () => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const titleId = useId();
  const confirmationId = useId();
  const { connection } = props;

  return (
    <li className="ai-connection" aria-labelledby={titleId}>
      <div id={titleId} className="ai-connection__title">
        <SelfDeclaredClientName name={connection.clientName} />
        <span className="badge badge--neutral">
          {aiScopeLabel(connection.scope, props.changeSetReview)}
        </span>
      </div>
      <dl className="detail-meta">
        <div className="detail-meta__row">
          <dt>Client ID</dt>
          <dd className="metadata-code">{connection.clientId}</dd>
        </div>
        <div className="detail-meta__row">
          <dt>Scope</dt>
          <dd className="metadata-code">{connection.scope}</dd>
        </div>
        <div className="detail-meta__row">
          <dt>Connected</dt>
          <dd>{formatAiTimestamp(connection.createdTime)}</dd>
        </div>
        <div className="detail-meta__row">
          <dt>Last used</dt>
          <dd>{connection.lastUsedTime ? formatAiTimestamp(connection.lastUsedTime) : "Never"}</dd>
        </div>
        <div className="detail-meta__row">
          <dt>Expires</dt>
          <dd>{formatAiTimestamp(connection.expiresTime)}</dd>
        </div>
      </dl>
      {!props.confirming ? (
        <div className="form-actions">
          <button
            className="btn btn--secondary btn--compact"
            type="button"
            onClick={props.onRevoke}
            disabled={props.disabled}
            aria-describedby={titleId}
          >
            Revoke
          </button>
        </div>
      ) : (
        <div className="delete-confirmation" role="alertdialog" aria-labelledby={confirmationId}>
          <p id={confirmationId}>
            Revoke this connection? The AI client loses access immediately and must be connected
            again to use Shadow.
          </p>
          <div className="form-actions">
            <button
              className="btn btn--secondary btn--compact"
              type="button"
              onClick={props.onCancel}
              disabled={props.disabled}
            >
              Cancel
            </button>
            <button
              className="btn btn--danger btn--compact"
              type="button"
              onClick={props.onConfirm}
              disabled={props.disabled}
            >
              {props.revoking ? "Revoking..." : "Confirm revoke"}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
