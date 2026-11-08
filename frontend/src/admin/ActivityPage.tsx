import { useEffect, useState } from "react";

import { workspaceMessages, type Locale } from "../i18n";
import { loadAuditEvents, loadMcpCalls, type AuditItem, type McpCallItem } from "../organization-client";
import { Alert, Badge, Button, EmptyState, Field, Select } from "../ui";
import { formatDateTime, MUTED, ROW, ROWS, Section } from "./Section";

const AUDIT_AREAS = ["", "organization", "shadow", "lane", "category", "label", "change", "event", "series", "occurrence", "support_access", "agent_calls"] as const;

export function ActivityLog({ organizationId, locale }: { organizationId: string; locale: Locale }) {
  const text = workspaceMessages(locale).activity;
  const [area, setArea] = useState<(typeof AUDIT_AREAS)[number]>("");
  const [items, setItems] = useState<AuditItem[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [calls, setCalls] = useState<McpCallItem[]>([]);
  const [failed, setFailed] = useState(false);
  const agentCalls = area === "agent_calls";
  async function load(offset: number, replace: boolean) {
    setFailed(false);
    try {
      if (agentCalls) {
        const page = await loadMcpCalls(organizationId, { offset });
        setCalls((current) => (replace ? page.items : [...current, ...page.items]));
        setNext(page.next_offset);
        return;
      }
      const page = await loadAuditEvents(organizationId, { prefix: area || undefined, offset });
      setItems((current) => (replace ? page.items : [...current, ...page.items]));
      setNext(page.next_offset);
    } catch { setFailed(true); }
  }
  useEffect(() => { void load(0, true); }, [organizationId, area]);
  return (
    <Section title={text.title} actions={<Field label={text.area} className="w-64">{(control) => <Select {...control} value={area} onChange={(event) => setArea(event.target.value as (typeof AUDIT_AREAS)[number])}>{AUDIT_AREAS.map((value) => <option key={value} value={value}>{text.areas[value || "all"]}</option>)}</Select>}</Field>}>
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      {agentCalls ? <p className={`${MUTED} m-0`}>{text.agentCalls.note}</p> : null}
      {(agentCalls ? calls.length : items.length) === 0 && !failed ? <EmptyState title={text.empty} /> : null}
      {agentCalls && calls.length ? (
        <ol aria-label={text.areas.agent_calls} className={ROWS}>
          {calls.map((call) => (
            <li key={call.id} className={ROW}>
              <time dateTime={call.occurred_at} className={`${MUTED} w-40 shrink-0 tabular-nums`}>{formatDateTime(locale, call.occurred_at)}</time>
              <span className="flex-1 text-[13px]"><code className="rounded-[4px] bg-surface-sunken px-1.5 py-0.5 text-xs">{call.tool}</code> · {call.person ?? text.system} · {call.mcp_client}</span>
              <Badge>{text.agentCalls.kinds[call.kind]}</Badge>
              <Badge tone={call.outcome === "ok" ? undefined : "warning"}>{text.agentCalls.outcomes[call.outcome]}</Badge>
            </li>
          ))}
        </ol>
      ) : null}
      {!agentCalls && items.length ? (
        <ol aria-label={text.title} className={ROWS}>
          {items.map((item) => (
            <li key={item.id} className={ROW}>
              <time dateTime={item.occurred_at} className={`${MUTED} w-40 shrink-0 tabular-nums`}>{formatDateTime(locale, item.occurred_at)}</time>
              <span className="flex-1 text-[13px]"><code className="rounded-[4px] bg-surface-sunken px-1.5 py-0.5 text-xs">{item.action}</code> {item.actor ? `· ${item.actor}` : `· ${text.system}`}</span>
              {item.support_access_id ? <Badge tone="warning">{text.viaSupport}</Badge> : null}
            </li>
          ))}
        </ol>
      ) : null}
      {next !== null ? <div><Button onClick={() => void load(next, false)}>{text.more}</Button></div> : null}
    </Section>
  );
}
