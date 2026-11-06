import { useEffect, useState } from "react";

import { workspaceMessages, type Locale } from "../i18n";
import { loadMcpConnection, revealMcpSecret, setMcpEnabled, type McpConnection } from "../organization-client";
import { Alert, Badge, Button } from "../ui";
import { MUTED, Section } from "./Section";

const VALUE = "min-w-0 flex-1 break-all rounded-[6px] bg-surface-sunken px-2 py-1 font-mono text-[13px] text-ink";

function CopyRow({ label, value, copyLabel, copiedLabel }: { label: string; value: string; copyLabel: string; copiedLabel: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(value); setCopied(true); } catch { setCopied(false); }
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="w-36 shrink-0 text-[13px] font-semibold">{label}</span>
      <code className={VALUE}>{value}</code>
      <Button size="sm" onClick={() => void copy()}>{copied ? copiedLabel : copyLabel}</Button>
    </div>
  );
}

/** How to connect an agent, and the Organization's switch for agent access (Owners and Admins). */
export function ConnectAgent({ organizationId, locale }: { organizationId: string; locale: Locale }) {
  const text = workspaceMessages(locale).agents;
  const [connection, setConnection] = useState<McpConnection | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
    void loadMcpConnection(organizationId).then(setConnection).catch(() => setFailed(true));
  }, [organizationId]);

  async function toggleSecret() {
    if (secret !== null) { setSecret(null); return; }
    try { setSecret(await revealMcpSecret(organizationId)); setFailed(false); } catch { setFailed(true); }
  }
  async function toggleAccess(enabled: boolean) {
    setFailed(false);
    try { setConnection(await setMcpEnabled(organizationId, enabled)); } catch { setFailed(true); }
  }

  if (failed && connection === null) return <Alert tone="danger" role="alert">{text.failed}</Alert>;
  if (connection === null) return null;
  const available = connection.interface_available;
  return (
    <>
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      <Section title={text.title} description={text.description}>
        {!available ? <Alert tone="warning" role="status">{text.unavailable}</Alert> : (
          <>
            <div className="flex flex-col gap-2">
              <CopyRow label={text.serverUrl} value={connection.server_url} copyLabel={text.copy} copiedLabel={text.copied} />
              <CopyRow label={text.clientId} value={connection.client_id} copyLabel={text.copy} copiedLabel={text.copied} />
              <div className="flex flex-wrap items-center gap-2">
                <span className="w-36 shrink-0 text-[13px] font-semibold">{text.clientSecret}</span>
                {secret !== null ? <code className={VALUE}>{secret}</code> : <span className={`flex-1 ${MUTED}`}>{connection.secret_configured ? "••••••••••••" : text.secretMissing}</span>}
                {connection.secret_configured ? <Button size="sm" onClick={() => void toggleSecret()}>{secret !== null ? text.hideSecret : text.showSecret}</Button> : null}
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <h3 className="m-0 text-[13px] font-semibold">{text.stepsTitle}</h3>
              <ol className={`m-0 list-decimal pl-5 ${MUTED}`}>{text.steps.map((step) => <li key={step}>{step}</li>)}</ol>
            </div>
            <p className={`m-0 ${MUTED}`}>{text.responsibility}</p>
          </>
        )}
      </Section>
      {available ? (
        <Section title={text.switchTitle} description={text.switchDescription} actions={
          <>
            <Badge tone={connection.enabled && !connection.platform_blocked ? "success" : "neutral"}>{connection.enabled && !connection.platform_blocked ? text.on : text.off}</Badge>
            {!connection.platform_blocked ? <Button size="sm" variant={connection.enabled ? "ghost-danger" : "primary"} onClick={() => void toggleAccess(!connection.enabled)}>{connection.enabled ? text.turnOff : text.turnOn}</Button> : null}
          </>
        }>
          {connection.platform_blocked ? <Alert tone="warning" role="status">{text.blocked}</Alert> : null}
        </Section>
      ) : null}
    </>
  );
}
