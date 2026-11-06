import { useEffect, useId, useState } from "react";

import { workspaceMessages, type Locale } from "../i18n";
import { parseAddresses } from "../invitation-addresses";
import { Alert, Button, Choice, Select, TextArea } from "../ui";
import { inviteMany, loadGroups, SeatsNeededError, type BulkInvitationResult, type Group, type OrganizationInvitation } from "../organization-client";

/** Pick Groups that an invited person joins on acceptance. */
export function GroupChoice({ groups, chosen, onChange, legend }: { groups: Group[]; chosen: string[]; onChange: (ids: string[]) => void; legend: string }) {
  if (!groups.length) return null;
  return (
    <fieldset className="m-0 flex flex-wrap items-center gap-x-4 gap-y-1 border-0 p-0">
      <legend className="mb-1 p-0 text-[13px] font-medium">{legend}</legend>
      {groups.map((group) => <Choice key={group.id} checked={chosen.includes(group.id)} onChange={(event) => onChange(event.target.checked ? [...chosen, group.id] : chosen.filter((id) => id !== group.id))} label={group.name} />)}
    </fieldset>
  );
}

export function useGroups(organizationId: string): Group[] {
  const [groups, setGroups] = useState<Group[]>([]);
  useEffect(() => { void loadGroups(organizationId).then(setGroups).catch(() => setGroups([])); }, [organizationId]);
  return groups;
}

/** Invite up to 50 people at once, previewing skips and seats first (Yearclock V2). */
export function BulkInvitations({ organizationId, locale, isOwner, onSent }: { organizationId: string; locale: Locale; isOwner: boolean; onSent: () => void }) {
  const copy = workspaceMessages(locale);
  const text = copy.bulkInvite;
  const groups = useGroups(organizationId);
  const [addresses, setAddresses] = useState("");
  const [role, setRole] = useState<OrganizationInvitation["role"]>("member");
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [preview, setPreview] = useState<BulkInvitationResult | null>(null);
  const [seatsNeeded, setSeatsNeeded] = useState(0);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const ids = { addresses: useId(), role: useId(), hint: useId() };
  const emails = parseAddresses(addresses);
  const changed = (apply: () => void) => { apply(); setPreview(null); setNotice(null); setSeatsNeeded(0); };
  async function send(dryRun: boolean) {
    setNotice(null);
    if (emails.length > 50) { setNotice({ ok: false, text: text.tooMany }); return; }
    try {
      const result = await inviteMany(organizationId, emails, role, groupIds, dryRun);
      if (dryRun) { setPreview(result); setSeatsNeeded(result.seats_needed); return; }
      setPreview(null); setAddresses("");
      setNotice({ ok: true, text: text.sent(result.created) });
      onSent();
    } catch (error) {
      if (error instanceof SeatsNeededError) setSeatsNeeded(error.seats); else setNotice({ ok: false, text: text.failed });
    }
  }
  return (
    <details className="bulk-invitations group rounded-[10px] border border-line">
      <summary className="cursor-pointer px-4 py-3 text-[13px] font-semibold text-ink">{text.title}</summary>
      <div className="flex flex-col gap-3 border-t border-line px-4 py-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={ids.addresses} className="text-[13px] font-medium">{text.addresses}</label>
          <TextArea id={ids.addresses} aria-describedby={ids.hint} rows={4} value={addresses} onChange={(event) => changed(() => setAddresses(event.target.value))} />
          <p id={ids.hint} className="m-0 text-xs text-ink-muted">{text.hint}</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={ids.role} className="text-[13px] font-medium">{text.role}</label>
          <Select id={ids.role} className="w-44" value={role} onChange={(event) => changed(() => setRole(event.target.value as OrganizationInvitation["role"]))}><option value="member">{copy.organizationUser}</option><option value="admin">{copy.administrator}</option>{isOwner ? <option value="owner">{copy.owner}</option> : null}</Select>
        </div>
        <GroupChoice groups={groups} chosen={groupIds} onChange={(next) => changed(() => setGroupIds(next))} legend={text.groups} />
        <div><Button disabled={!emails.length} onClick={() => void send(true)}>{text.preview}</Button></div>
        {preview ? (
          <div role="status" className="flex flex-col gap-2 rounded-[10px] bg-surface-subtle p-3 text-[13px]">
            <p className="m-0 font-medium">{text.willInvite(preview.invite.length)}</p>
            {preview.skipped.length ? <><p className="m-0">{text.skipped}</p><ul className="m-0 list-disc pl-5 text-ink-muted">{preview.skipped.map((item) => <li key={`${item.email}-${item.reason}`}>{item.email} — {text.reasons[item.reason]}</li>)}</ul></> : null}
            {seatsNeeded ? <p className="m-0 font-medium text-warning-ink">{text.seatsNeeded(seatsNeeded)}</p> : preview.invite.length ? <div><Button variant="primary" onClick={() => void send(false)}>{text.send(preview.invite.length)}</Button></div> : null}
          </div>
        ) : seatsNeeded ? <Alert tone="warning" role="alert">{text.seatsNeeded(seatsNeeded)}</Alert> : null}
        {notice ? <p role={notice.ok ? "status" : "alert"} className={notice.ok ? "m-0 text-[13px] text-success-ink" : "m-0 text-[13px] text-danger"}>{notice.text}</p> : null}
      </div>
    </details>
  );
}
