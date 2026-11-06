import { useEffect, useId, useState } from "react";

import { describeSource } from "../access-sources";
import { messages, workspaceMessages, type Locale, type WorkspaceMessages } from "../i18n";
import {
  archiveYearclock,
  ConfirmationRequiredError,
  createYearclock,
  deleteYearclock,
  grantGroupAccess,
  grantYearclockAccess,
  loadGroupGrants,
  loadGroups,
  loadManagedYearclocks,
  loadMemberships,
  loadYearclockAccess,
  loadYearclockPeople,
  recoverYearclock,
  renameYearclock,
  reorderYearclocks,
  revokeGroupAccess,
  revokeYearclockAccess,
  setOrganizationAccess,
  type Group,
  type GroupGrant,
  type ManagedYearclock,
  type OrganizationAccess,
  type OrganizationMembership,
  type YearclockAccessGrant,
  type YearclockPeople,
} from "../organization-client";
import { Alert, Badge, Button, Field, Select, TextInput, useConfirm } from "../ui";
import { formatDate, INLINE_FORM, MUTED, ROW, ROWS, Section } from "./Section";

export function YearclockManagement({ organizationId, locale, revision, onChanged }: { organizationId: string; locale: Locale; revision: number; onChanged: () => void }) {
  const text = workspaceMessages(locale).management;
  const admin = messages(locale).shell.admin;
  const confirm = useConfirm();
  const [yearclocks, setYearclocks] = useState<ManagedYearclock[]>([]);
  const [name, setName] = useState("");
  const [failed, setFailed] = useState(false);
  const refresh = () => void loadManagedYearclocks(organizationId).then(setYearclocks).catch(() => setFailed(true));
  useEffect(refresh, [organizationId, revision]);
  async function act(action: () => Promise<unknown>) { setFailed(false); try { await action(); onChanged(); } catch { setFailed(true); } }
  const current = yearclocks.filter((clock) => !clock.deleted_at);
  const deleted = yearclocks.filter((clock) => clock.deleted_at);
  const activeClocks = current.filter((clock) => !clock.archived_at);
  async function remove(clock: ManagedYearclock) { if (await confirm({ title: text.confirmDelete(clock.name), confirmLabel: text.delete, destructive: true })) void act(() => deleteYearclock(organizationId, clock)); }
  function moveClock(index: number, delta: number) { const ids = activeClocks.map((clock) => clock.id); [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]]; void act(() => reorderYearclocks(organizationId, activeClocks, ids)); }
  return (
    <>
      <Section title={text.title}>
        <form className={INLINE_FORM} onSubmit={(event) => { event.preventDefault(); if (name.trim()) void act(() => createYearclock(organizationId, name.trim())).then(() => setName("")); }}>
          <Field label={text.newClock} className="min-w-64 flex-1">{(control) => <TextInput {...control} maxLength={200} value={name} onChange={(event) => setName(event.target.value)} />}</Field>
          <Button type="submit" variant="primary" disabled={!name.trim()}>{text.create}</Button>
        </form>
        {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
        {current.length === 0 ? <p className={MUTED}>{admin.noYearclocks}</p> : null}
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {current.map((clock) => {
            const activeIndex = activeClocks.findIndex((item) => item.id === clock.id);
            return (
              <li key={`${clock.id}-${clock.version}`}>
                <YearclockSettings organizationId={organizationId} locale={locale} clock={clock} text={text} onRename={(item, nextName) => act(() => renameYearclock(organizationId, item, nextName))} onArchive={(item, restore) => act(() => archiveYearclock(organizationId, item, restore))} onDelete={() => remove(clock)} onUp={activeIndex > 0 ? () => moveClock(activeIndex, -1) : undefined} onDown={activeIndex >= 0 && activeIndex < activeClocks.length - 1 ? () => moveClock(activeIndex, 1) : undefined} onChanged={() => { refresh(); onChanged(); }} />
              </li>
            );
          })}
        </ul>
      </Section>
      {deleted.length ? (
        <Section title={text.deletedTitle}>
          <ul className={ROWS}>
            {deleted.map((clock) => (
              <li key={clock.id} className={ROW}>
                <span className="flex-1"><span className="font-medium">{clock.name}</span> — <span className={MUTED}>{text.recoverableUntil(formatDate(locale, clock.purge_after!))}</span></span>
                <Button size="sm" aria-label={`${text.recover}: ${clock.name}`} onClick={() => void act(() => recoverYearclock(organizationId, clock))}>{text.recover}</Button>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </>
  );
}

function YearclockSettings({ organizationId, locale, clock, text, onRename, onArchive, onDelete, onUp, onDown, onChanged }: { organizationId: string; locale: Locale; clock: ManagedYearclock; text: WorkspaceMessages["management"]; onChanged: () => void; onRename: (clock: ManagedYearclock, name: string) => Promise<void>; onArchive: (clock: ManagedYearclock, restore?: boolean) => Promise<void>; onDelete: () => void; onUp?: () => void; onDown?: () => void }) {
  const [clockName, setClockName] = useState(clock.name);
  return (
    <article aria-label={clock.name} className="flex flex-col gap-4 rounded-[10px] border border-line p-4">
      <div className="flex flex-wrap items-end gap-2">
        <Field label={text.name} className="min-w-56 flex-1">{(control) => <TextInput {...control} maxLength={200} value={clockName} onChange={(event) => setClockName(event.target.value)} />}</Field>
        <Button disabled={!clockName.trim()} onClick={() => void onRename(clock, clockName.trim())}>{text.rename}</Button>
        <Button onClick={() => void onArchive(clock, Boolean(clock.archived_at))}>{clock.archived_at ? text.restore : text.archive}</Button>
        {onUp ? <Button variant="ghost" aria-label={`${text.up}: ${clock.name}`} onClick={onUp}>{text.up}</Button> : null}
        {onDown ? <Button variant="ghost" aria-label={`${text.down}: ${clock.name}`} onClick={onDown}>{text.down}</Button> : null}
        <Button variant="ghost-danger" aria-label={`${text.delete}: ${clock.name}`} onClick={onDelete}>{text.delete}</Button>
      </div>
      {clock.archived_at ? <p className="m-0"><Badge>{text.archived}</Badge></p> : null}
      {!clock.archived_at ? <YearclockAccess organizationId={organizationId} clock={clock} locale={locale} onChanged={onChanged} /> : null}
    </article>
  );
}

function YearclockAccess({ organizationId, clock, locale, onChanged }: { organizationId: string; clock: ManagedYearclock; locale: Locale; onChanged: () => void }) {
  const confirm = useConfirm();
  const text = workspaceMessages(locale).access;
  const overview = workspaceMessages(locale).accessOverview;
  const yearclockId = clock.id;
  const ids = { everyone: useId(), group: useId(), person: useId() };
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupGrants, setGroupGrants] = useState<GroupGrant[]>([]);
  const [groupId, setGroupId] = useState("");
  const [groupRole, setGroupRole] = useState<GroupGrant["role"]>("viewer");
  const [people, setPeople] = useState<YearclockPeople | null>(null);
  const [memberships, setMemberships] = useState<OrganizationMembership[]>([]);
  const [grants, setGrants] = useState<YearclockAccessGrant[]>([]);
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<YearclockAccessGrant["role"]>("viewer");
  const [failed, setFailed] = useState(false);
  const refreshGroups = () => { void loadGroups(organizationId).then(setGroups).catch(() => setFailed(true)); void loadGroupGrants(organizationId, yearclockId).then(setGroupGrants).catch(() => setFailed(true)); };
  const refresh = () => { void loadMemberships(organizationId).then(setMemberships).catch(() => setFailed(true)); void loadYearclockAccess(organizationId, yearclockId).then(setGrants).catch(() => setFailed(true)); };
  useEffect(refreshGroups, [organizationId, yearclockId]);
  useEffect(refresh, [organizationId, yearclockId]);
  async function toggleWho() { if (people) { setPeople(null); return; } try { setPeople(await loadYearclockPeople(organizationId, yearclockId)); } catch { setFailed(true); } }
  async function groupAct(action: () => Promise<unknown>) { setFailed(false); try { await action(); } catch { setFailed(true); } refreshGroups(); }
  async function share(next: OrganizationAccess) {
    setFailed(false);
    try {
      await setOrganizationAccess(organizationId, clock, next);
      onChanged();
    } catch (error) {
      if (error instanceof ConfirmationRequiredError && (await confirm({ title: text.confirmEveryoneEditor(error.members), confirmLabel: text.giveEditAccess }))) {
        try { await setOrganizationAccess(organizationId, clock, next, true); onChanged(); } catch { setFailed(true); }
      } else if (!(error instanceof ConfirmationRequiredError)) setFailed(true);
    }
  }
  async function grant() { try { await grantYearclockAccess(organizationId, yearclockId, userId, role); refresh(); } catch { setFailed(true); } }
  async function revoke(userAccountId: string) { const item = grants.find((grantItem) => grantItem.user_account_id === userAccountId); if (!item) return; try { await revokeYearclockAccess(organizationId, yearclockId, item); refresh(); } catch { setFailed(true); } }
  const roleName = (value: "editor" | "viewer") => (value === "editor" ? text.editor : text.viewer);
  return (
    <section aria-label={text.title} className="flex flex-col gap-3 border-t border-line pt-4">
      <h3 className="m-0 text-[13px] font-semibold">{text.title}</h3>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={ids.everyone} className="text-[13px] font-medium">{text.everyone}</label>
        <Select id={ids.everyone} className="max-w-xs" value={clock.organization_access ?? "none"} onChange={(event) => void share(event.target.value as OrganizationAccess)}><option value="none">{text.noAccess}</option><option value="viewer">{text.viewer}</option><option value="editor">{text.editor}</option></Select>
        <p className="m-0 text-xs text-ink-muted">{text.everyoneNote}</p>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex min-w-48 flex-col gap-1.5"><span className="sr-only">{text.title}</span><Select value={userId} onChange={(event) => setUserId(event.target.value)}><option value="">—</option>{memberships.filter((membership) => membership.role === "member").map((membership) => <option key={membership.id} value={membership.user_account_id}>{membership.display_name || membership.email}</option>)}</Select></label>
        <Select aria-label={text.role} className="w-32" value={role} onChange={(event) => setRole(event.target.value as YearclockAccessGrant["role"])}><option value="editor">{text.editor}</option><option value="viewer">{text.viewer}</option></Select>
        <Button disabled={!userId} onClick={() => void grant()}>{text.grant}</Button>
      </div>
      {failed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      {grants.length ? (
        <ul className={ROWS}>
          {grants.map((item) => { const member = memberships.find((membership) => membership.user_account_id === item.user_account_id); return (
            <li key={item.id} className={ROW}><span className="flex-1">{member ? member.display_name || member.email : item.user_account_id} — {roleName(item.role)}</span><Button size="sm" variant="ghost" onClick={() => void revoke(item.user_account_id)}>{text.revoke}</Button></li>
          ); })}
        </ul>
      ) : null}
      {groups.length ? (
        <div className="flex flex-col gap-2">
          <h4 className="m-0 text-[13px] font-semibold">{text.groups}</h4>
          {groupGrants.length ? (
            <ul className={ROWS}>
              {groupGrants.map((item) => (
                <li key={item.group_id} className={ROW}>
                  <span className="flex-1">{item.name}</span>
                  <Select aria-label={text.groupRole(item.name)} className="w-32" value={item.role} onChange={(event) => void groupAct(() => grantGroupAccess(organizationId, yearclockId, item.group_id, event.target.value as GroupGrant["role"], item))}><option value="editor">{text.editor}</option><option value="viewer">{text.viewer}</option></Select>
                  <Button size="sm" variant="ghost" aria-label={text.removeGroup(item.name)} onClick={() => void groupAct(() => revokeGroupAccess(organizationId, yearclockId, item))}>{text.revoke}</Button>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex min-w-48 flex-col gap-1.5"><label htmlFor={ids.group} className="text-[13px] font-medium">{text.group}</label><Select id={ids.group} value={groupId} onChange={(event) => setGroupId(event.target.value)}><option value="">—</option>{groups.filter((group) => !groupGrants.some((item) => item.group_id === group.id)).map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</Select></div>
            <Select aria-label={text.groupRole(groups.find((group) => group.id === groupId)?.name ?? text.group)} className="w-32" value={groupRole} onChange={(event) => setGroupRole(event.target.value as GroupGrant["role"])}><option value="viewer">{text.viewer}</option><option value="editor">{text.editor}</option></Select>
            <Button disabled={!groupId} onClick={() => void groupAct(() => grantGroupAccess(organizationId, yearclockId, groupId, groupRole)).then(() => setGroupId(""))}>{text.grant}</Button>
          </div>
        </div>
      ) : null}
      <div><Button size="sm" variant="ghost" aria-expanded={Boolean(people)} onClick={() => void toggleWho()}>{people ? overview.hide : overview.whoHasAccess}</Button></div>
      {people ? (
        <section aria-label={`${overview.whoHasAccess}: ${people.name}`} className="access-overview rounded-[10px] bg-surface-subtle p-3">
          {people.people.length ? (
            <ul className="m-0 flex list-none flex-col gap-2 p-0">{people.people.map((person) => <li key={person.membership_id}><strong>{person.name}</strong> — {overview.sources.roles[person.role]}<ul className="m-0 list-disc pl-5 text-[13px] text-ink-muted">{person.sources.map((source, index) => <li key={index}>{describeSource(source, overview.sources)}</li>)}</ul></li>)}</ul>
          ) : <p className="m-0">{overview.nobody}</p>}
        </section>
      ) : null}
    </section>
  );
}
