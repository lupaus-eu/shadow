import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronsUpDown, LayoutGrid, Plus } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router";

import { messages, type Locale } from "../i18n";
import { loadOrganizations, type OrganizationSummary, type OrganizationWorkspace } from "../organization-client";
import { modelMessages } from "../models/messages";
import { adminHref, adminSections, modelsHref, organizationHref } from "./nav";

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

/** Sidebar for one Organization: switcher, overview, and administration by role. */
export function OrganizationSidebar({ workspace, locale }: { workspace: OrganizationWorkspace; locale: Locale }) {
  const text = messages(locale);
  const organizationId = workspace.organization.id;
  const sections = adminSections(workspace.membership.role);
  return (
    <nav aria-label={text.shell.navigation} className="flex flex-col gap-5">
      <OrganizationSwitcher workspace={workspace} locale={locale} />
      <ul className={LIST}>
        <li><NavLink end className={LINK} to={organizationHref(organizationId)}><LayoutGrid size={15} aria-hidden="true" />{text.shell.overview}</NavLink></li>
        <li><NavLink className={LINK} to={modelsHref(organizationId)}>{modelMessages(locale).nav}</NavLink></li>
      </ul>
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
