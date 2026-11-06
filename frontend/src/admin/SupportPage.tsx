import { useEffect, useState } from "react";

import { workspaceMessages, type Locale } from "../i18n";
import { decideSupportAccess, loadSupportAccess, type SupportAccessRequest } from "../organization-client";
import { Alert, Badge, Button, EmptyState, TextInput, type Tone } from "../ui";
import { formatDateTime, MUTED, ROW, ROWS, Section } from "./Section";

const TONE: Record<SupportAccessRequest["status"], Tone> = { pending: "warning", approved: "success", rejected: "neutral", revoked: "neutral", expired: "neutral" };

export function SupportAccess({ organizationId, locale }: { organizationId: string; locale: Locale }) {
  const text = workspaceMessages(locale).support;
  const [requests, setRequests] = useState<SupportAccessRequest[]>([]);
  const [hours, setHours] = useState<Record<string, number>>({});
  const [failed, setFailed] = useState(false);
  const refresh = () => void loadSupportAccess(organizationId).then(setRequests).catch(() => setFailed(true));
  useEffect(refresh, [organizationId]);
  async function decide(item: SupportAccessRequest, decision: "approve" | "reject" | "revoke") {
    setFailed(false);
    try { await decideSupportAccess(organizationId, item.id, decision, hours[item.id] ?? item.requested_hours); refresh(); } catch { setFailed(true); }
  }
  return (
    <Section title={text.title} description={text.description} className="support-access">
      <p className={`m-0 ${MUTED}`}>{text.organizationId}: <code className="rounded-[4px] bg-surface-sunken px-1.5 py-0.5 text-xs text-ink">{organizationId}</code></p>
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      {requests.length === 0 ? <EmptyState title={text.empty} /> : (
        <ul className={ROWS}>
          {requests.map((item) => (
            <li key={item.id} className={ROW}>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span><strong className="font-semibold">{`${text.case} ${item.case_reference}`}</strong> · {text.scope[item.scope]} · <Badge tone={TONE[item.status]}>{text.status[item.status]}</Badge>{item.status === "approved" && item.expires_at ? ` ${text.until(formatDateTime(locale, item.expires_at))}` : ""}</span>
                <span className={MUTED}>{`${text.requestedBy} ${item.requested_by}`} · {text.requestedHours(item.requested_hours)}</span>
              </div>
              {item.status === "pending" ? (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex items-center gap-2 text-[13px]">{text.hours} <TextInput type="number" className="w-20" min={1} max={item.requested_hours} value={hours[item.id] ?? item.requested_hours} onChange={(event) => setHours({ ...hours, [item.id]: Math.min(item.requested_hours, Math.max(1, Number(event.target.value) || 1)) })} /></label>
                  <Button variant="primary" size="sm" onClick={() => void decide(item, "approve")}>{text.approve}</Button>
                  <Button size="sm" onClick={() => void decide(item, "reject")}>{text.reject}</Button>
                </div>
              ) : null}
              {item.status === "approved" ? <Button size="sm" variant="ghost-danger" onClick={() => void decide(item, "revoke")}>{text.revoke}</Button> : null}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
