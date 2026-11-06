import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AiApiError,
  approveConsentRequest,
  denyConsentRequest,
  fetchConsentRequest
} from "../../api/ai";
import type { ConsentRequestDto } from "../../api/ai";
import type { UserRole } from "../../api/users";
import { useAuth } from "../../auth/AuthContext";
import { navigateBrowser } from "../../auth/browserNavigation";
import SelfDeclaredClientName from "./SelfDeclaredClientName";
import { aiAccessFromScope, aiScopeLabel, formatAiTimestamp } from "./aiPresentation";
import Alert from "../../components/Alert";

type Decision = "approve" | "deny";

type ConsentState =
  | { kind: "loading" }
  | { kind: "ready"; consent: ConsentRequestDto }
  | { kind: "redirecting"; decision: Decision }
  | { kind: "invalid" }
  | { kind: "expired" }
  | { kind: "decided" }
  | { kind: "error"; message: string };

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

function finalStateFromError(error: unknown): ConsentState | null {
  if (!(error instanceof AiApiError)) return null;
  if (error.code === "AUTHORIZATION_REQUEST_EXPIRED") return { kind: "expired" };
  if (error.code === "AUTHORIZATION_REQUEST_DECIDED") return { kind: "decided" };
  if (error.status === 404) return { kind: "invalid" };
  return null;
}

// The pending request id comes only from this page's own query string. It is
// sent to the consent API and never rendered (ADR-015).
export default function AuthorizePage() {
  const { features } = useAuth();
  const [searchParams] = useSearchParams();
  const requestId = searchParams.get("request") ?? "";

  if (!features.mcp) {
    return (
      <AuthorizeMessage title="AI connections are not available">
        Connecting AI clients is turned off in this Shadow environment. Close this page and
        contact your administrator if you expected it to work.
      </AuthorizeMessage>
    );
  }

  if (!requestId) return <InvalidRequestMessage />;
  return <ConsentRequest key={requestId} requestId={requestId} />;
}

function ConsentRequest(props: { requestId: string }) {
  const { user, features } = useAuth();
  const [state, setState] = useState<ConsentState>({ kind: "loading" });
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [deciding, setDeciding] = useState<Decision | null>(null);
  const [decisionError, setDecisionError] = useState("");
  const decidingRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    async function loadConsentRequest() {
      try {
        const consent = await fetchConsentRequest(props.requestId, controller.signal);
        if (active) setState({ kind: "ready", consent });
      } catch (error) {
        if (!active || (error as { name?: string }).name === "AbortError") return;
        setState(finalStateFromError(error) ?? { kind: "error", message: messageFromError(error) });
      }
    }

    void loadConsentRequest();
    return () => {
      active = false;
      controller.abort();
    };
  }, [props.requestId, loadAttempt]);

  function retryLoad() {
    setState({ kind: "loading" });
    setLoadAttempt((attempt) => attempt + 1);
  }

  async function decide(decision: Decision) {
    if (decidingRef.current) return;
    decidingRef.current = true;
    setDeciding(decision);
    setDecisionError("");

    try {
      const result =
        decision === "approve"
          ? await approveConsentRequest(props.requestId)
          : await denyConsentRequest(props.requestId);
      setState({ kind: "redirecting", decision });
      // The server builds the redirect URL; it is used exactly as returned.
      navigateBrowser(result.redirectUrl);
    } catch (error) {
      decidingRef.current = false;
      setDeciding(null);
      const finalState = finalStateFromError(error);
      if (finalState) setState(finalState);
      else setDecisionError(messageFromError(error));
    }
  }

  if (state.kind === "loading") {
    return (
      <AuthorizeMessage title="Loading authorization request..." busy>
        Checking the AI client&apos;s request.
      </AuthorizeMessage>
    );
  }

  if (state.kind === "invalid") return <InvalidRequestMessage />;

  if (state.kind === "expired") {
    return (
      <AuthorizeMessage title="Authorization request expired">
        This request is no longer valid. Start the connection again from your AI client.
      </AuthorizeMessage>
    );
  }

  if (state.kind === "decided") {
    return (
      <AuthorizeMessage title="Authorization request already decided">
        This request was already approved or denied and cannot be decided again. Start the
        connection again from your AI client if needed.
      </AuthorizeMessage>
    );
  }

  if (state.kind === "redirecting") {
    return (
      <AuthorizeMessage
        title={state.decision === "approve" ? "Access approved" : "Access denied"}
        busy
      >
        Returning to the AI client...
      </AuthorizeMessage>
    );
  }

  if (state.kind === "error") {
    return (
      <AuthorizeMessage
        title="Unable to load authorization request"
        alert
        actions={
          <button className="btn btn--secondary" type="button" onClick={retryLoad}>
            Retry
          </button>
        }
      >
        {state.message}
      </AuthorizeMessage>
    );
  }

  const { consent } = state;
  const busy = deciding !== null;
  // A role without AI access cannot approve; the server would deny anyway.
  const canApprove = aiAccessFromScope(consent.scope) !== "none";

  return (
    <main className="center-page">
      <section className="home-panel ai-authorize" aria-labelledby="ai-authorize-title">
        <p className="eyebrow">Shadow</p>
        <h1 id="ai-authorize-title" className="display-title">
          Connect an AI client
        </h1>
        <p>
          An AI client asks to act as you
          {user ? (
            <>
              {" "}
              (<strong>{user.name}</strong>)
            </>
          ) : null}{" "}
          with your Shadow role.
        </p>

        <dl className="detail-meta">
          <div className="detail-meta__row">
            <dt>Client</dt>
            <dd>
              <SelfDeclaredClientName name={consent.clientName} />
            </dd>
          </div>
          <div className="detail-meta__row">
            <dt>Returns to</dt>
            <dd>
              {consent.redirectIsLoopback ? (
                "A program on this computer"
              ) : (
                <span className="metadata-code">{consent.redirectHost}</span>
              )}
            </dd>
          </div>
          <div className="detail-meta__row">
            <dt>Request expires</dt>
            <dd>{formatAiTimestamp(consent.expiresTime)}</dd>
          </div>
        </dl>

        {consent.redirectIsLoopback ? (
          <div className="alert alert--info" role="note" aria-label="Local program">
            <p className="alert__title">Local program</p>
            <p className="alert__text">
              The authorization code goes to a program on this computer. Local programs cannot be
              verified by name, so approve only if you started this connection yourself.
            </p>
          </div>
        ) : null}

        <section className="ai-authorize__access" aria-labelledby="ai-authorize-access-title">
          <h2 id="ai-authorize-access-title" className="section-title">
            Requested access
          </h2>
          <ScopeExplanation
            scope={consent.scope}
            changeSetReview={features.mcpChangeSetReview}
            role={user?.role}
          />
          {canApprove ? (
            <p>
              Data that the AI client reads from Shadow is sent to your AI vendor. The connection
              lasts for a limited time (30 days by default) unless it is revoked.
            </p>
          ) : null}
        </section>

        {decisionError ? (
          <Alert
            variant="danger"
            role="alert"
            title="Decision failed"
            message={decisionError}
            onDismiss={() => setDecisionError("")}
          />
        ) : null}

        <div className="form-actions">
          <button
            className="btn btn--secondary"
            type="button"
            onClick={() => void decide("deny")}
            disabled={busy}
          >
            {deciding === "deny" ? "Denying..." : "Deny"}
          </button>
          {canApprove ? (
            <button
              className="btn btn--primary"
              type="button"
              onClick={() => void decide("approve")}
              disabled={busy}
            >
              {deciding === "approve" ? "Approving..." : "Approve"}
            </button>
          ) : null}
        </div>
      </section>
    </main>
  );
}

// The scope is the set the grant will hold: read, or read and write, narrowed
// to the User's role. An empty set means the role allows no AI access. With MCP
// change-set review on, write access can also apply and reject submitted
// change sets (ADR-015 amendment).
function ScopeExplanation(props: { scope: string; changeSetReview: boolean; role?: UserRole }) {
  const access = aiAccessFromScope(props.scope);

  if (access === "none") {
    return (
      <div className="ai-authorize__scope">
        <h3 className="secondary-title">{aiScopeLabel(props.scope)}</h3>
        <p>
          Your Shadow role
          {props.role ? <> ({props.role === "admin" ? "Admin" : "Consultant"})</> : null} does not
          allow AI clients to connect, so this request cannot be approved. Deny it to return to the
          AI client, and ask your administrator if you need AI access.
        </p>
      </div>
    );
  }

  if (access === null) {
    return (
      <div className="ai-authorize__scope">
        <h3 className="secondary-title">Unknown access</h3>
        <p>
          The client requests access that this page cannot describe (
          <span className="metadata-code">{props.scope}</span>). Deny the request if you are unsure.
        </p>
      </div>
    );
  }

  const readText =
    "The AI client can read the organisations, scenarios, model structure, timeseries, events " +
    "and AI change sets that you can see in Shadow.";

  return (
    <div className="ai-authorize__scope">
      <h3 className="secondary-title">{aiScopeLabel(props.scope, props.changeSetReview)}</h3>
      {access === "read" ? (
        <p>{readText} It cannot change anything.</p>
      ) : (
        <>
          <p>{readText}</p>
          {props.changeSetReview ? (
            <p>
              It can also propose changes as change sets and, when you tell it to, apply or reject
              change sets awaiting review on your behalf, including change sets that other people
              proposed. Applying a change set changes Shadow data, and you are recorded as its
              reviewer. Your AI client should ask you to approve each apply or reject.
            </p>
          ) : (
            <p>
              It can also propose changes as change sets. Changes are proposed only: nothing in
              Shadow changes until a person reviews and applies the change set in Shadow.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function InvalidRequestMessage() {
  return (
    <AuthorizeMessage title="Authorization request not found">
      This link is invalid or the request no longer exists. Start the connection again from your AI
      client.
    </AuthorizeMessage>
  );
}

function AuthorizeMessage(props: {
  title: string;
  busy?: boolean;
  alert?: boolean;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="center-page" aria-busy={props.busy ? "true" : undefined}>
      <section className="home-panel ai-authorize" aria-labelledby="ai-authorize-title">
        <p className="eyebrow">Shadow</p>
        <h1 id="ai-authorize-title" className="display-title">
          {props.title}
        </h1>
        <p className="muted" role={props.alert ? "alert" : undefined}>
          {props.children}
        </p>
        {props.actions ? <div className="form-actions">{props.actions}</div> : null}
      </section>
    </main>
  );
}
