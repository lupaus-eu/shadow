import { useState } from "react";

import { messages, workspaceMessages, type Locale } from "../i18n";
import { requestOrganizationDeletion, type OrganizationWorkspace } from "../organization-client";
import { Alert, Button, Choice, useToast } from "../ui";
import { MUTED, Section } from "./Section";

export function OrganizationDetails({ workspace, locale }: { workspace: OrganizationWorkspace; locale: Locale }) {
  const admin = messages(locale).shell.admin;
  const support = workspaceMessages(locale).support;
  const rows: Array<[string, string]> = [[admin.organizationName, workspace.organization.name], [admin.timeZone, workspace.organization.time_zone], [support.organizationId, workspace.organization.id]];
  return (
    <Section title={admin.details}>
      <dl className="m-0 grid gap-3 sm:grid-cols-[200px_1fr]">
        {rows.map(([label, value]) => <div key={label} className="contents"><dt className={MUTED}>{label}</dt><dd className="m-0 text-[13px] font-medium break-all">{value}</dd></div>)}
      </dl>
    </Section>
  );
}

/** Deleting the Organization, in the Owner's danger zone. */
export function OrganizationDeletion({ organizationId, name, locale }: { organizationId: string; name: string; locale: Locale }) {
  const text = workspaceMessages(locale).deletion;
  const admin = messages(locale).shell.admin;
  const [confirmed, setConfirmed] = useState(false);
  const [failed, setFailed] = useState(false);
  async function remove() {
    setFailed(false);
    try { await requestOrganizationDeletion(organizationId); window.location.assign("/"); } catch { setFailed(true); }
  }
  return (
    <Section title={admin.dangerZone} tone="danger" className="organization-deletion">
      <div className="flex flex-col gap-3">
        <h3 className="m-0 text-[13px] font-semibold">{text.title}</h3>
        <p className={`m-0 ${MUTED}`}>{text.description}</p>
        <Choice checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} label={text.confirm(name)} />
        <div><Button variant="danger" disabled={!confirmed} onClick={() => void remove()}>{text.request}</Button></div>
        {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      </div>
    </Section>
  );
}
