import { useState } from "react";
import { buildApiUrl } from "../../api/client";

type CopyState = { text: string; result: "copied" | "failed" } | null;
type CopyHandler = (text: string) => Promise<void>;

// The Claude Code plugin is installed from the repository marketplace; its
// `.mcp.json` points at the production origin.
const PLUGIN_MARKETPLACE_COMMAND = "/plugin marketplace add reflector-oy/schatten";
const PLUGIN_INSTALL_COMMAND = "/plugin install schatten@schatten";
const PLUGIN_ORIGIN = "https://schatten.lupaus.eu";

// The same `SKILL.md` folders the plugin ships, zipped by the backend.
const SKILLS = [
  { name: "schatten-model-building", label: "Model building" },
  { name: "schatten-timeseries-generation", label: "Timeseries generation" }
];

// MCP resource URLs are `<PUBLIC_ORIGIN>/api/mcp/<server>`; the SPA is served
// from the public origin, so it builds them from its own origin.
function mcpUrls(origin: string): { read: string; write: string } {
  return { read: `${origin}/api/mcp/read`, write: `${origin}/api/mcp/write` };
}

// `changeSetReview`: the write connection can also apply and reject change
// sets (ADR-015 amendment).
export default function ConnectInstructions(props: { changeSetReview: boolean }) {
  const origin = window.location.origin;
  const urls = mcpUrls(origin);
  const [copyState, setCopyState] = useState<CopyState>(null);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopyState({ text, result: "copied" });
    } catch {
      setCopyState({ text, result: "failed" });
    }
  }

  return (
    <section className="ai-panel-connect" aria-labelledby="ai-connect-title">
      <h3 id="ai-connect-title" className="ai-panel__section-title">
        Connect an AI client
      </h3>
      {props.changeSetReview ? (
        <p className="muted">
          Chat in your own AI client. It reads Schatten through the read connection and proposes
          changes through the write connection. Nothing changes until a person applies the change
          set, here or in the chat: when you tell it to, the client can apply or reject a change set
          awaiting review, and it should ask you to approve each call. Data the client reads is sent
          to your AI vendor.
        </p>
      ) : (
        <p className="muted">
          Chat in your own AI client. It reads Schatten through the read connection and proposes
          changes through the write connection; nothing changes until a person applies the change
          set here. Data the client reads is sent to your AI vendor.
        </p>
      )}

      <dl className="ai-panel-connect__urls">
        <McpUrl server="read" label="Read" url={urls.read} copyState={copyState} onCopy={copy} />
        <McpUrl
          server="write"
          label={
            props.changeSetReview ? "Write (propose, apply and reject)" : "Write (proposals only)"
          }
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
      <p className="muted">
        The Schatten plugin adds both servers and the Schatten skills. It needs read access to the
        reflector-oy/schatten GitHub repository.
      </p>
      <ol className="ai-panel-connect__steps">
        <li>Add the repository marketplace:</li>
      </ol>
      <CopyCommand
        label="marketplace command"
        command={PLUGIN_MARKETPLACE_COMMAND}
        copyState={copyState}
        onCopy={copy}
      />
      <ol className="ai-panel-connect__steps" start={2}>
        <li>Install the plugin:</li>
      </ol>
      <CopyCommand
        label="install command"
        command={PLUGIN_INSTALL_COMMAND}
        copyState={copyState}
        onCopy={copy}
      />
      {origin !== PLUGIN_ORIGIN ? (
        <p className="ai-panel__hint">
          The plugin connects to {PLUGIN_ORIGIN}. For this Schatten, also add the servers below; the
          plugin&apos;s skills apply to them too.
        </p>
      ) : null}
      <p className="muted">Or add only the servers:</p>
      <pre className="ai-panel-connect__command">
        <code>
          {`claude mcp add --transport http schatten-read ${urls.read}\nclaude mcp add --transport http schatten-write ${urls.write}`}
        </code>
      </pre>
      <ol className="ai-panel-connect__steps" start={3}>
        <li>
          Whether you installed the plugin or added the servers, run{" "}
          <code className="metadata-code">/mcp</code> in Claude Code, select each Schatten server
          and authenticate. Approve the access in Schatten.
        </li>
      </ol>

      <h4 className="ai-panel__section-title">Skills for claude.ai and Claude Desktop</h4>
      <p className="muted">
        Skills teach your AI client how to build Schatten models and generate timeseries.
      </p>
      <ul className="ai-panel-connect__downloads">
        {SKILLS.map((skill) => (
          <li key={skill.name}>
            <a href={buildApiUrl(`/api/v1/ai/skills/${skill.name}.zip`)} download>
              {skill.label} ({skill.name}.zip)
            </a>
          </li>
        ))}
      </ul>
      <ol className="ai-panel-connect__steps">
        <li>Download both skill zips.</li>
        <li>
          In claude.ai or Claude Desktop, turn on code execution under Settings, Capabilities.
        </li>
        <li>
          Open Customize, then Skills, choose to upload a skill and select a zip. Repeat for the
          other.
        </li>
      </ol>
    </section>
  );
}

function CopyResult(props: { result: "copied" | "failed" | null; failedText: string }) {
  return props.result === "failed" ? (
    <span className="ai-panel__hint" role="status">
      {props.failedText}
    </span>
  ) : null;
}

function copyResult(copyState: CopyState, text: string) {
  return copyState?.text === text ? copyState.result : null;
}

function CopyCommand(props: {
  label: string;
  command: string;
  copyState: CopyState;
  onCopy: CopyHandler;
}) {
  const result = copyResult(props.copyState, props.command);

  return (
    <div className="ai-panel-connect__copy-command">
      <pre className="ai-panel-connect__command">
        <code>{props.command}</code>
      </pre>
      <button
        className="btn btn--secondary btn--compact"
        type="button"
        aria-label={`Copy ${props.label}`}
        onClick={() => void props.onCopy(props.command)}
      >
        {result === "copied" ? "Copied" : "Copy"}
      </button>
      <CopyResult result={result} failedText="Copying failed; select the command and copy it." />
    </div>
  );
}

function McpUrl(props: {
  server: "read" | "write";
  label: string;
  url: string;
  copyState: CopyState;
  onCopy: CopyHandler;
}) {
  const result = copyResult(props.copyState, props.url);

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
        <CopyResult result={result} failedText="Copying failed; select the URL and copy it." />
      </dd>
    </div>
  );
}
