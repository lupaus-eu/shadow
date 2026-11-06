import { useEffect, useState } from "react";

import { workspaceMessages, type Locale } from "../i18n";
import { loadAuditEvents, type AuditItem } from "../organization-client";
import { Alert, Badge, Button, EmptyState, Field, Select } from "../ui";
import { formatDateTime, MUTED, ROW, ROWS, Section } from "./Section";

const AUDIT_AREAS = ["", "organization", "shadow", "lane", "category", "label", "event", "series", "occurrence", "support_access"] as const;

export function ActivityLog({ organizationId, locale }: { organizationId: string; locale: Locale }) {
  const text = workspaceMessages(locale).activity;
  const [area, setArea] = useState<(typeof AUDIT_AREAS)[number]>("");
  const [items, setItems] = useState<AuditItem[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  async function load(offset: number, replace: boolean) {
    setFailed(false);
    try {
      const page = await loadAuditEvents(organizationId, { prefix: area || undefined, offset });
      setItems((current) => (replace ? page.items : [...current, ...page.items]));
      setNext(page.next_offset);
    } catch { setFailed(true); }
  }
  useEffect(() => { void load(0, true); }, [organizationId, area]);
  return (
    <Section title={text.title} actions={<Field label={text.area} className="w-64">{(control) => <Select {...control} value={area} onChange={(event) => setArea(event.target.value as (typeof AUDIT_AREAS)[number])}>{AUDIT_AREAS.map((value) => <option key={value} value={value}>{text.areas[value || "all"]}</option>)}</Select>}</Field>}>
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      {items.length === 0 && !failed ? <EmptyState title={text.empty} /> : null}
      {items.length ? (
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
