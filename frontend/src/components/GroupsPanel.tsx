import { useEffect, useId, useState } from "react";

import { workspaceMessages, type Locale } from "../i18n";
import {
  addGroupMember,
  createGroup,
  deleteGroup,
  DuplicateNameError,
  GroupConfirmationRequiredError,
  LimitReachedError,
  loadGroups,
  loadMemberships,
  loadOwnGroups,
  removeGroupMember,
  renameGroup,
  type Group,
  type OrganizationMembership,
  type OwnGroup,
} from "../organization-client";
import { Section, INLINE_FORM } from "../admin/Section";
import { Alert, Button, EmptyState, Select, TextInput, useConfirm } from "../ui";

/** Owners and Admins manage Groups of members (Yearclock V2). */
export function GroupsPanel({ organizationId, locale, writable }: { organizationId: string; locale: Locale; writable: boolean }) {
  const text = workspaceMessages(locale).groups;
  const [groups, setGroups] = useState<Group[]>([]);
  const [memberships, setMemberships] = useState<OrganizationMembership[]>([]);
  const [name, setName] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const nameId = useId();
  const confirm = useConfirm();
  const refresh = () => Promise.all([loadGroups(organizationId).then(setGroups), loadMemberships(organizationId).then(setMemberships)]).catch(() => setNotice(text.failed));
  useEffect(() => { void refresh(); }, [organizationId]);
  async function act(action: () => Promise<unknown>) {
    setNotice(null);
    try {
      await action();
    } catch (error) {
      setNotice(error instanceof DuplicateNameError ? text.duplicate : error instanceof LimitReachedError ? text.limit(error.maximum) : text.failed);
    }
    await refresh();
  }
  async function remove(group: Group) {
    setNotice(null);
    try {
      await deleteGroup(organizationId, group);
    } catch (error) {
      if (!(error instanceof GroupConfirmationRequiredError)) { setNotice(text.failed); return; }
      const losing = error.impact.losing_access.map((item) => `${item.name} (${item.yearclock_name})`);
      if (!(await confirm({ title: text.confirmDelete(group.name, error.impact.members, error.impact.yearclocks, losing), confirmLabel: text.delete, destructive: true }))) return;
      try { await deleteGroup(organizationId, group, true); } catch { setNotice(text.failed); }
    }
    await refresh();
  }
  return (
    <>
      <Section title={text.title} description={text.description} className="groups">
        {notice ? <Alert tone="danger" role="alert">{notice}</Alert> : null}
        {!writable ? <Alert tone="info" role="status">{text.readOnly}</Alert> : null}
        {writable ? (
          <form className={INLINE_FORM} onSubmit={(event) => { event.preventDefault(); if (name.trim()) void act(() => createGroup(organizationId, name.trim())).then(() => setName("")); }}>
            <div className="flex min-w-64 flex-1 flex-col gap-1.5"><label htmlFor={nameId} className="text-[13px] font-medium">{text.name}</label><TextInput id={nameId} value={name} maxLength={80} onChange={(event) => setName(event.target.value)} /></div>
            <Button type="submit" variant="primary" disabled={!name.trim()}>{text.create}</Button>
          </form>
        ) : null}
        {groups.length === 0 ? <EmptyState title={text.empty} /> : null}
        <ul className="m-0 grid list-none gap-3 p-0 md:grid-cols-2">
          {groups.map((group) => <GroupRow key={group.id} group={group} memberships={memberships} writable={writable} locale={locale} onRename={(next) => act(() => renameGroup(organizationId, group, next))} onDelete={() => void remove(group)} onAdd={(membershipId) => act(() => addGroupMember(organizationId, group, membershipId))} onRemove={(membershipId) => act(() => removeGroupMember(organizationId, group, membershipId))} />)}
        </ul>
      </Section>
    </>
  );
}

function GroupRow({ group, memberships, writable, locale, onRename, onDelete, onAdd, onRemove }: { group: Group; memberships: OrganizationMembership[]; writable: boolean; locale: Locale; onRename: (name: string) => Promise<void>; onDelete: () => void; onAdd: (membershipId: string) => Promise<void>; onRemove: (membershipId: string) => Promise<void> }) {
  const text = workspaceMessages(locale).groups;
  const [name, setName] = useState(group.name);
  const [candidate, setCandidate] = useState("");
  useEffect(() => setName(group.name), [group.name]);
  const ids = { name: useId(), member: useId() };
  const outside = memberships.filter((membership) => !group.members.some((member) => member.membership_id === membership.id));
  return (
    <li>
      <section aria-label={group.name} className="flex h-full flex-col gap-3 rounded-[10px] border border-line p-4">
        <h3 className="m-0 flex items-baseline gap-2 text-sm font-semibold">{group.name} <span className="text-xs font-normal text-ink-muted">{text.members(group.members.length)}</span></h3>
        {writable ? (
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor={ids.name} className="sr-only">{`${text.name}: ${group.name}`}</label>
            <TextInput id={ids.name} className="min-w-40 flex-1" value={name} maxLength={80} onChange={(event) => setName(event.target.value)} />
            <Button size="sm" disabled={!name.trim() || name.trim() === group.name} onClick={() => void onRename(name.trim())}>{text.rename}</Button>
            <Button size="sm" variant="ghost-danger" aria-label={`${text.delete}: ${group.name}`} onClick={onDelete}>{text.delete}</Button>
          </div>
        ) : null}
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {group.members.map((member) => (
            <li key={member.membership_id} className="flex items-center gap-2 text-[13px]">
              <span className="flex-1">{member.name}</span>
              {writable ? <Button size="sm" variant="ghost" aria-label={`${text.remove(member.name)}: ${group.name}`} onClick={() => void onRemove(member.membership_id)}>{text.remove(member.name)}</Button> : null}
            </li>
          ))}
        </ul>
        {writable && outside.length ? (
          <div className="mt-auto flex flex-wrap items-end gap-2">
            <div className="flex min-w-40 flex-1 flex-col gap-1.5">
              <label htmlFor={ids.member} className="text-xs font-medium">{`${text.addMember}: ${group.name}`}</label>
              <Select id={ids.member} value={candidate} onChange={(event) => setCandidate(event.target.value)}>
                <option value="">—</option>
                {outside.map((membership) => <option key={membership.id} value={membership.id}>{membership.display_name || membership.email}</option>)}
              </Select>
            </div>
            <Button size="sm" disabled={!candidate} onClick={() => void onAdd(candidate).then(() => setCandidate(""))}>{text.add}</Button>
          </div>
        ) : null}
      </section>
    </li>
  );
}

/** Every member sees the Groups they belong to and the access each gives. */
export function MyGroups({ organizationId, locale }: { organizationId: string; locale: Locale }) {
  const text = workspaceMessages(locale).myGroups;
  const roles = workspaceMessages(locale).access;
  const [groups, setGroups] = useState<OwnGroup[] | null>(null);
  useEffect(() => { void loadOwnGroups(organizationId).then(setGroups).catch(() => setGroups([])); }, [organizationId]);
  if (!groups || groups.length === 0) return null;
  return (
    <Section title={text.title}>
      <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2">
        {groups.map((group) => (
          <li key={group.id} className="rounded-[10px] border border-line p-3">
            <strong className="text-sm font-semibold">{group.name}</strong>
            {group.access.length ? <ul className="m-0 mt-1 list-none p-0 text-[13px] text-ink-muted">{group.access.map((item) => <li key={item.yearclock_id}>{text.access(item.yearclock_name, item.role === "editor" ? roles.editor : roles.viewer)}</li>)}</ul> : <p className="m-0 mt-1 text-xs text-ink-muted">{text.noAccess}</p>}
          </li>
        ))}
      </ul>
    </Section>
  );
}
