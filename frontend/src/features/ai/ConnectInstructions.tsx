import { useState } from "react";

type CopyState = { url: string; result: "copied" | "failed" } | null;

// MCP resource URLs are `<PUBLIC_ORIGIN>/api/mcp/<server>`; the SPA is served
// from the public origin, so it builds them from its own origin.
function mcpUrls(origin: string): { read: string; write: string } {
  return { read: `${origin}/api/mcp/read`, write: `${origin}/api/mcp/write` };
}

export default function ConnectInstructions() {
  const urls = mcpUrls(window.location.origin);
  const [copyState, setCopyState] = useState<CopyState>(null);

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopyState({ url, result: "copied" });
    } catch {
      setCopyState({ url, result: "failed" });
    }
  }

  return (
    <section className="ai-panel-connect" aria-labelledby="ai-connect-title">
      <h3 id="ai-connect-title" className="ai-panel__section-title">
        Connect an AI client
      </h3>
      <p className="muted">
        Chat in your own AI client. It reads Schatten through the read connection and proposes
        changes through the write connection; nothing changes until a person applies the change set
        here. Data the client reads is sent to your AI vendor.
      </p>

      <dl className="ai-panel-connect__urls">
        <McpUrl server="read" label="Read" url={urls.read} copyState={copyState} onCopy={copy} />
        <McpUrl
          server="write"
          label="Write (proposals only)"
          url={urls.write}
          copyState={copyState}
          onCopy={copy}
        />
      </dl>

      <h4 className="ai-panel__section-title">Claude Desktop or claude.ai</h4>
      <ol className="ai-panel-connect__steps">
        <li>Open Settings, then Connectors, and add a custom connector.</li>
        <li>Paste the read URL and connect. Repeat with the write URL as a second connector.</li>
        <li>Sign in to Schatten when asked and approve the access.</li>
      </ol>

      <h4 className="ai-panel__section-title">Claude Code</h4>
      <ol className="ai-panel-connect__steps">
        <li>Add both servers:</li>
      </ol>
      <pre className="ai-panel-connect__command">
        <code>
          {`claude mcp add --transport http schatten-read ${urls.read}\nclaude mcp add --transport http schatten-write ${urls.write}`}
        </code>
      </pre>
      <ol className="ai-panel-connect__steps" start={2}>
        <li>
          In Claude Code, run <code className="metadata-code">/mcp</code>, select each server and
          authenticate. Approve the access in Schatten.
        </li>
      </ol>
    </section>
  );
}

function McpUrl(props: {
  server: "read" | "write";
  label: string;
  url: string;
  copyState: CopyState;
  onCopy: (url: string) => Promise<void>;
}) {
  const result = props.copyState?.url === props.url ? props.copyState.result : null;

  return (
    <div className="ai-panel-connect__url">
      <dt>{props.label}</dt>
      <dd>
        <code className="metadata-code">{props.url}</code>
        <button
          className="btn btn--secondary btn--compact"
          type="button"
          aria-label={`Copy ${props.server} URL`}
          onClick={() => void props.onCopy(props.url)}
        >
          {result === "copied" ? "Copied" : "Copy"}
        </button>
        {result === "failed" ? (
          <span className="ai-panel__hint" role="status">
            Copying failed; select the URL and copy it.
          </span>
        ) : null}
      </dd>
    </div>
  );
}
