import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronsUpDown, LayoutGrid, Plus } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router";

import { messages, workspaceMessages, type Locale } from "../i18n";
import { loadOrganizations, loadOwnGroups, type OrganizationSummary, type OrganizationWorkspace, type OwnGroup } from "../organization-client";
import { matchesText } from "../text-match";
import { cx } from "../ui";
import { adminHref, adminSections, organizationHref, sidebarYearclocks, yearclockHref } from "./nav";

const LIST = "m-0 flex list-none flex-col gap-0.5 p-0";
const LINK = "flex min-h-8 items-center gap-2 rounded-[6px] px-2 py-1.5 text-[13px] text-sidebar-ink no-underline hover:bg-sidebar-raised hover:text-white aria-[current=page]:bg-sidebar-raised aria-[current=page]:font-semibold aria-[current=page]:text-white pointer-coarse:min-h-11";

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <div role="group" aria-labelledby={id} className="flex flex-col gap-0.5">
      <p id={id} className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-sidebar-muted">{title}</p>
      {children}
    </div>
  );
}

/** Sidebar for one Organization: switcher, overview, Yearclocks (recent first, searchable), and administration by role. */
export function OrganizationSidebar({ workspace, locale }: { workspace: OrganizationWorkspace; locale: Locale }) {
  const text = messages(locale);
  const organizationId = workspace.organization.id;
  const [query, setQuery] = useState("");
  const searchId = useId();
  const { recent, others } = sidebarYearclocks(workspace.yearclocks, workspace.recent_yearclock_ids ?? []);
  const searching = query.trim().length > 0;
  const matching = workspace.yearclocks.filter((yearclock) => matchesText(query, yearclock.name));
  const link = (yearclock: { id: string; name: string }) => (
    <li key={yearclock.id}><NavLink className={LINK} to={yearclockHref(organizationId, yearclock.id)}><span className="truncate">{yearclock.name}</span></NavLink></li>
  );
  const sections = adminSections(workspace.membership.role);
  const myGroups = useOwnGroups(organizationId);
  return (
    <nav aria-label={text.shell.navigation} className="flex flex-col gap-5">
      <OrganizationSwitcher workspace={workspace} locale={locale} />
      <ul className={LIST}>
        <li><NavLink end className={LINK} to={organizationHref(organizationId)}><LayoutGrid size={15} aria-hidden="true" />{text.shell.overview}</NavLink></li>
      </ul>
      <Section title={text.shell.yearclocks}>
        {workspace.yearclocks.length > 6 ? (
          <div className="px-1 pb-1">
            <label htmlFor={searchId} className="sr-only">{text.shell.findYearclock}</label>
            <input id={searchId} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={text.shell.findYearclock} className="h-8 w-full rounded-[6px] border border-sidebar-line bg-sidebar-raised px-2 text-[13px] text-white placeholder:text-sidebar-muted pointer-coarse:h-11" />
          </div>
        ) : null}
        {workspace.yearclocks.length === 0 ? <p className="px-2 text-[13px] text-sidebar-muted">{text.shell.noYearclocks}</p> : null}
        {searching ? <ul className={LIST}>{matching.map(link)}</ul> : (
          <>
            {recent.length > 0 && others.length > 0 ? <p className="px-2 pt-1 text-[11px] text-sidebar-muted">{text.shell.recent}</p> : null}
            <ul className={LIST}>{recent.map(link)}</ul>
            {others.length > 0 ? <ul className={cx(LIST, recent.length > 0 && "mt-1 border-t border-sidebar-line pt-1")}>{others.map(link)}</ul> : null}
          </>
        )}
      </Section>
      {myGroups.length > 0 ? (
        <Section title={workspaceMessages(locale).myGroups.title}>
          <ul className={LIST}>
            {myGroups.map((group) => <li key={group.id} className="truncate px-2 py-1 text-[13px] text-sidebar-ink">{group.name}</li>)}
          </ul>
        </Section>
      ) : null}
      {sections.length > 0 ? (
        <Section title={text.shell.administration}>
          <ul className={LIST}>
            {sections.map((section) => <li key={section}><NavLink className={LINK} to={adminHref(organizationId, section)}>{text.shell.sections[section]}</NavLink></li>)}
          </ul>
        </Section>
      ) : null}
    </nav>
  );
}

/** The Groups the signed-in person belongs to; empty when none or when they cannot be loaded. */
function useOwnGroups(organizationId: string): OwnGroup[] {
  const [groups, setGroups] = useState<OwnGroup[]>([]);
  useEffect(() => {
    let current = true;
    void loadOwnGroups(organizationId).then((items) => { if (current) setGroups(items); }, () => { if (current) setGroups([]); });
    return () => { current = false; };
  }, [organizationId]);
  return groups;
}

const MENU_ITEM = "flex min-h-8 cursor-pointer items-center gap-2 rounded-[6px] px-2.5 py-1.5 text-[13px] text-ink outline-none data-[highlighted]:bg-surface-sunken pointer-coarse:min-h-11";

function OrganizationSwitcher({ workspace, locale }: { workspace: OrganizationWorkspace; locale: Locale }) {
  const text = messages(locale);
  const navigate = useNavigate();
  const [organizations, setOrganizations] = useState<OrganizationSummary[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    void loadOrganizations(controller.signal).then(setOrganizations, () => setOrganizations([]));
    return () => controller.abort();
  }, []);
  const others = organizations.filter((organization) => organization.id !== workspace.organization.id && (organization.status ?? "active") === "active");
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button type="button" aria-label={`${text.shell.switchOrganization}: ${workspace.organization.name}`} className="flex w-full cursor-pointer items-center gap-2 rounded-[8px] border border-sidebar-line bg-sidebar-raised px-2.5 py-2 text-left hover:border-sidebar-muted pointer-coarse:min-h-11">
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-[13px] font-semibold text-white">{workspace.organization.name}</span>
            <span className="text-[11px] text-sidebar-muted">{text.organizationRole[workspace.membership.role]}</span>
          </span>
          <ChevronsUpDown size={15} aria-hidden="true" className="text-sidebar-muted" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="start" sideOffset={6} className="ui-root z-50 min-w-60 rounded-[10px] border border-line bg-surface p-1 shadow-[var(--shadow-overlay)]">
          {others.map((organization) => (
            <DropdownMenu.Item key={organization.id} className={MENU_ITEM} onSelect={() => navigate(organizationHref(organization.id))}>
              <span className="flex flex-col"><span className="font-medium">{organization.name}</span><span className="text-[11px] text-ink-muted">{text.organizationRole[organization.role]}</span></span>
            </DropdownMenu.Item>
          ))}
          {others.length > 0 ? <DropdownMenu.Separator className="my-1 h-px bg-line" /> : null}
          <DropdownMenu.Item className={MENU_ITEM} onSelect={() => navigate("/")}><LayoutGrid size={14} aria-hidden="true" />{text.shell.allOrganizations}</DropdownMenu.Item>
          <DropdownMenu.Item className={MENU_ITEM} onSelect={() => navigate("/organization-signups/new")}><Plus size={14} aria-hidden="true" />{text.createAnotherOrganization}</DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
