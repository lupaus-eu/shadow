import { Fragment, useEffect, useState } from "react";

import { describeSource } from "../access-sources";
import { BulkInvitations, GroupChoice, useGroups } from "../components/BulkInvitations";
import { messages, workspaceMessages, type Locale } from "../i18n";
import {
  changeMembershipRole,
  inviteOrganizationUser,
  loadInvitations,
  loadMemberships,
  loadPersonAccess,
  leaveOrganization,
  removeMembership,
  resendInvitation,
  revokeInvitation,
  transferOwnership,
  type OrganizationInvitation,
  type OrganizationMembership,
  type PersonAccess,
} from "../organization-client";
import { useNavigate } from "react-router";

import { useAccount } from "../shell/AppShell";
import { Alert, Badge, Button, Choice, Dialog, EmptyState, Field, Select, Table, TextInput, useConfirm, useToast } from "../ui";
import { INLINE_FORM, MUTED, ROW, ROWS, Section } from "./Section";

export function Invitations({ organizationId, locale, isOwner }: { organizationId: string; locale: Locale; isOwner: boolean }) {
  const copy = workspaceMessages(locale);
  const admin = messages(locale).shell.admin;
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrganizationInvitation["role"]>("member");
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const groups = useGroups(organizationId);
  const [invitations, setInvitations] = useState<OrganizationInvitation[]>([]);
  const [failed, setFailed] = useState(false);
  const refresh = () => void loadInvitations(organizationId).then(setInvitations).catch(() => setFailed(true));
  useEffect(refresh, [organizationId]);
  async function invite() {
    setFailed(false);
    try { await inviteOrganizationUser(organizationId, email, role, groupIds); setEmail(""); setGroupIds([]); refresh(); } catch { setFailed(true); }
  }
  async function act(action: () => Promise<unknown>) {
    setFailed(false);
    try { await action(); } catch { setFailed(true); }
    refresh();
  }
  const roleName = (value: OrganizationInvitation["role"]) => (value === "owner" ? copy.owner : value === "admin" ? copy.administrator : copy.organizationUser);
  return (
    <Section title={copy.invitationTitle} description={copy.invitationDescription}>
      <form className={INLINE_FORM} onSubmit={(event) => { event.preventDefault(); if (email) void invite(); }}>
        <Field label={copy.email} className="min-w-64 flex-1">{(control) => <TextInput {...control} type="email" value={email} onChange={(event) => setEmail(event.target.value)} />}</Field>
        <Field label={copy.role} className="w-44">{(control) => <Select {...control} value={role} onChange={(event) => setRole(event.target.value as OrganizationInvitation["role"])}><option value="member">{copy.organizationUser}</option><option value="admin">{copy.administrator}</option>{isOwner ? <option value="owner">{copy.owner}</option> : null}</Select>}</Field>
        <Button type="submit" variant="primary" disabled={!email}>{copy.sendInvitation}</Button>
      </form>
      <GroupChoice groups={groups} chosen={groupIds} onChange={setGroupIds} legend={copy.bulkInvite.groups} />
      {failed ? <Alert tone="danger" role="alert">{copy.invitationFailed}</Alert> : null}
      <BulkInvitations organizationId={organizationId} locale={locale} isOwner={isOwner} onSent={refresh} />
      <h3 className="m-0 text-[13px] font-semibold">{admin.pendingInvitations}</h3>
      {invitations.length === 0 ? <p className={MUTED}>{admin.noInvitations}</p> : (
        <ul className={ROWS} aria-label={admin.pendingInvitations}>
          {invitations.map((invitation) => (
            <li key={invitation.id} className={ROW}>
              <span className="min-w-0 flex-1 truncate font-medium">{invitation.email}</span>
              <span className={MUTED}>{roleName(invitation.role)}</span>
              <Badge tone={invitation.status === "pending" ? "info" : invitation.status === "accepted" ? "success" : "neutral"}>{admin.invitationStatus[invitation.status]}</Badge>
              {invitation.status === "pending" ? (
                <span className="flex gap-2">
                  <Button size="sm" onClick={() => void act(() => resendInvitation(organizationId, invitation))}>{copy.resend}</Button>
                  <Button size="sm" variant="ghost" onClick={() => void act(() => revokeInvitation(organizationId, invitation))}>{copy.revoke}</Button>
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function Memberships({ organizationId, locale, isOwner, readOnly, onChanged }: { organizationId: string; locale: Locale; isOwner: boolean; readOnly: boolean; onChanged?: () => void }) {
  const confirm = useConfirm();
  const toast = useToast();
  const navigate = useNavigate();
  const { userAccount } = useAccount();
  const [transferring, setTransferring] = useState(false);
  const [leaving, setLeaving] = useState<OrganizationMembership | null>(null);
  const text = workspaceMessages(locale).membership;
  const admin = messages(locale).shell.admin;
  const overview = workspaceMessages(locale).accessOverview;
  const [memberships, setMemberships] = useState<OrganizationMembership[]>([]);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<PersonAccess | null>(null);
  const refresh = () => void loadMemberships(organizationId).then(setMemberships).catch(() => setFailed(true));
  useEffect(refresh, [organizationId]);
  const ownerCount = memberships.filter((item) => item.role === "owner").length;
  async function changeRole(membership: OrganizationMembership, role: OrganizationMembership["role"]) {
    setFailed(false);
    if (role === "owner" && !(await confirm({ title: text.ownerConfirm(membership.display_name || membership.email), confirmLabel: text.makeOwner }))) { refresh(); return; }
    try { await changeMembershipRole(organizationId, membership, role); refresh(); } catch { setFailed(true); }
  }
  async function startLeaving(membership: OrganizationMembership) {
    if (membership.role === "owner" && ownerCount === 1) { setLeaving(membership); return; }
    if (await confirm({ title: text.leaveDialog.title, confirmLabel: text.leaveDialog.confirmPlain, destructive: true })) await leave(membership);
  }
  const candidates = memberships.filter((item) => item.role !== "owner");
  const me = memberships.find((item) => item.user_account_id === userAccount.id);
  async function leave(membership: OrganizationMembership, successor?: string) {
    setFailed(false);
    try {
      const outcome = await leaveOrganization(organizationId, membership.id, successor);
      if (outcome === "left") { setLeaving(null); toast(text.leaveDialog.done); navigate("/"); return; }
      setLeaving(membership);
      if (outcome === "last_member") setFailed(false);
    } catch { setFailed(true); }
  }
  async function showAccess(membership: OrganizationMembership) {
    if (open?.person.membership_id === membership.id) { setOpen(null); return; }
    try { setOpen(await loadPersonAccess(organizationId, membership.id)); } catch { setFailed(true); }
  }
  async function remove(membership: OrganizationMembership) {
    setFailed(false);
    const name = membership.display_name || membership.email;
    let lost: string[] = [];
    try { lost = (await loadPersonAccess(organizationId, membership.id)).yearclocks.filter((item) => !item.sources.some((source) => source.kind === "role")).map((item) => `${item.name} (${overview.sources.roles[item.role]})`); } catch { /* the confirmation still asks */ }
    if (!(await confirm({ title: overview.confirmRemove(name, lost), confirmLabel: text.remove, destructive: true }))) return;
    try { await removeMembership(organizationId, membership); setOpen(null); refresh(); } catch { setFailed(true); }
  }
  return (
    <Section title={text.title} actions={isOwner && !readOnly ? <Button onClick={() => setTransferring(true)}>{text.transfer.action}</Button> : undefined}>
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      {memberships.length === 0 && !failed ? <EmptyState title={text.title} /> : (
        <Table caption={text.title}>
          <thead><tr><th scope="col">{admin.name}</th><th scope="col">{admin.role}</th><th scope="col" className="text-right">{admin.actions}</th></tr></thead>
          <tbody>
            {memberships.map((membership) => {
              const name = membership.display_name || membership.email;
              const finalOwner = membership.role === "owner" && ownerCount === 1;
              const manageable = !readOnly && !finalOwner && (isOwner || membership.role !== "owner");
              const expanded = open?.person.membership_id === membership.id;
              return (
                <Fragment key={membership.id}>
                  <tr>
                    <td>
                      <div className="flex flex-col"><strong className="font-semibold">{name}</strong> <span className={MUTED}>{membership.email}</span></div>
                      {finalOwner ? <p className="m-0 mt-1 text-xs text-ink-muted">{text.finalOwner}</p> : null}
                    </td>
                    <td>
                      {manageable ? (
                        <label><span className="sr-only">{`${text.title}: ${name}`}</span><Select className="w-40" value={membership.role} onChange={(event) => void changeRole(membership, event.target.value as OrganizationMembership["role"])}>{isOwner ? <option value="owner">{text.owner}</option> : null}<option value="admin">{text.admin}</option><option value="member">{text.member}</option></Select></label>
                      ) : <span>{text[membership.role]}</span>}
                    </td>
                    <td>
                      <div className="flex justify-end gap-2">
                        <Button size="sm" aria-expanded={expanded} aria-label={overview.accessFor(name)} onClick={() => void showAccess(membership)}>{overview.access}</Button>
                        {manageable && membership.id !== me?.id ? <Button size="sm" variant="ghost-danger" aria-label={`${text.remove} ${name}`} onClick={() => void remove(membership)}>{text.remove}</Button> : null}
                        {!readOnly && membership.id === me?.id ? <Button size="sm" variant="ghost-danger" aria-label={`${text.leave} ${name}`} onClick={() => void startLeaving(membership)}>{text.leave}</Button> : null}
                      </div>
                    </td>
                  </tr>
                  {expanded && open ? (
                    <tr>
                      <td colSpan={3} className="bg-surface-subtle">
                        <section aria-label={overview.accessFor(name)} className="access-overview">
                          {open.yearclocks.length ? (
                            <ul className="m-0 flex list-none flex-col gap-2 p-0">
                              {open.yearclocks.map((item) => (
                                <li key={item.id}>
                                  <strong>{item.name}</strong>{item.archived ? ` (${overview.archived})` : ""} — {overview.sources.roles[item.role]}
                                  <ul className="m-0 list-disc pl-5 text-[13px] text-ink-muted">{item.sources.map((source, index) => <li key={index}>{describeSource(source, overview.sources)}</li>)}</ul>
                                </li>
                              ))}
                            </ul>
                          ) : <p className="m-0">{overview.none}</p>}
                        </section>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </Table>
      )}
      <TransferDialog open={transferring} onOpenChange={setTransferring} candidates={candidates} locale={locale} onTransfer={async (membership, keep) => { try { await transferOwnership(organizationId, membership, keep); setTransferring(false); toast(text.transfer.done(membership.display_name || membership.email)); refresh(); onChanged?.(); return true; } catch { setFailed(true); return false; } }} />
      <Dialog open={leaving !== null} onOpenChange={(open) => { if (!open) setLeaving(null); }} title={text.leaveDialog.title} description={text.leaveDialog.description}>
        {leaving ? <LeaveChoice candidates={candidates} locale={locale} onLeave={(successor) => void leave(leaving, successor)} onCancel={() => setLeaving(null)} /> : null}
      </Dialog>
    </Section>
  );
}

function TransferDialog({ open, onOpenChange, candidates, locale, onTransfer }: { open: boolean; onOpenChange: (open: boolean) => void; candidates: OrganizationMembership[]; locale: Locale; onTransfer: (membership: OrganizationMembership, keepOwner: boolean) => Promise<boolean> }) {
  const text = workspaceMessages(locale).membership;
  const [choice, setChoice] = useState("");
  const [keep, setKeep] = useState(false);
  const [busy, setBusy] = useState(false);
  const target = candidates.find((item) => item.id === choice);
  async function submit() {
    if (!target) return;
    setBusy(true);
    const done = await onTransfer(target, keep);
    setBusy(false);
    if (done) { setChoice(""); setKeep(false); }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={text.transfer.title} description={text.transfer.description}
      footer={<><Button onClick={() => onOpenChange(false)}>{messages(locale).overlay.cancel}</Button><Button variant="primary" disabled={!target || busy} onClick={() => void submit()}>{text.transfer.confirm}</Button></>}>
      {candidates.length === 0 ? <p className="m-0 text-[13px]">{text.transfer.none}</p> : (
        <div className="flex flex-col gap-3">
          <Field label={text.transfer.person}>{(control) => <Select {...control} value={choice} onChange={(event) => setChoice(event.target.value)}><option value="">{text.transfer.choose}</option>{candidates.map((item) => <option key={item.id} value={item.id}>{`${item.display_name || item.email} (${text[item.role]})`}</option>)}</Select>}</Field>
          <Choice type="checkbox" checked={keep} onChange={(event) => setKeep(event.target.checked)} label={text.transfer.keep} />
          <p className="m-0 text-xs text-ink-muted">{text.transfer.keepHint}</p>
          <p className="m-0 text-xs text-ink-muted">{text.transfer.billing}</p>
        </div>
      )}
    </Dialog>
  );
}

/** The only Owner leaves by naming a successor; with nobody else there is nothing to hand over to. */
function LeaveChoice({ candidates, locale, onLeave, onCancel }: { candidates: OrganizationMembership[]; locale: Locale; onLeave: (successor: string) => void; onCancel: () => void }) {
  const text = workspaceMessages(locale).membership.leaveDialog;
  const [choice, setChoice] = useState("");
  if (candidates.length === 0) return <div className="flex flex-col gap-3"><Alert tone="warning"><p className="m-0">{text.onlyMember}</p></Alert><div><Button onClick={onCancel}>{messages(locale).overlay.cancel}</Button></div></div>;
  return (
    <div className="flex flex-col gap-3">
      <p className="m-0 text-[13px]">{text.successor}</p>
      <Field label={workspaceMessages(locale).membership.transfer.person}>{(control) => <Select {...control} value={choice} onChange={(event) => setChoice(event.target.value)}><option value="">{text.choose}</option>{candidates.map((item) => <option key={item.id} value={item.id}>{`${item.display_name || item.email} (${workspaceMessages(locale).membership[item.role]})`}</option>)}</Select>}</Field>
      <div className="flex justify-end gap-2"><Button onClick={onCancel}>{messages(locale).overlay.cancel}</Button><Button variant="danger" disabled={!choice} onClick={() => onLeave(choice)}>{text.confirm}</Button></div>
    </div>
  );
}
