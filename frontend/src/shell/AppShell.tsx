import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, LogOut, Menu as MenuIcon, X } from "lucide-react";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";

import { logoutUrl, type UserAccount } from "../auth-client";
import { loadTransferOrganizations } from "../data-transfer/client";
import { dataTransferMessages } from "../data-transfer/messages";
import { messages, workspaceMessages, type Locale } from "../i18n";
import { LegalFooterLink } from "../legal/LegalFooterLink";
import { SystemReadiness } from "../components/SystemReadiness";
import { cx } from "../ui";
import { Logo } from "./Logo";
import { MadeBy } from "./LupausMark";

/** The signed-in person and their session actions, shared by every page of the shell. */
export type Account = { userAccount: UserAccount; locale: Locale; onLocaleChange: (locale: Locale) => Promise<void>; onLogout: () => void };

const AccountContext = createContext<Account | null>(null);
export const AccountProvider = AccountContext.Provider;

export function useAccount(): Account {
  const account = useContext(AccountContext);
  if (!account) throw new Error("useAccount needs an AccountProvider");
  return account;
}

const TitleContext = createContext<(title: string) => void>(() => {});

/** Set the page title shown in the top bar (the page's only h1) and the browser tab. */
export function usePageTitle(title: string) {
  const setTitle = useContext(TitleContext);
  useEffect(() => { setTitle(title); }, [setTitle, title]);
}

/** Signed-in layout for the customer app: the frame with the account menu and the system status. */
export function AppShell({ sidebar, children, wide = false, actions }: { sidebar?: ReactNode; children: ReactNode; wide?: boolean; actions?: ReactNode }) {
  const { locale } = useAccount();
  return <ShellFrame locale={locale} sidebar={sidebar} footer={<div className="flex flex-col gap-2"><SystemReadiness locale={locale} /><LegalFooterLink locale={locale} className="!text-sidebar-muted" /><MadeBy tone="dark" className="text-sidebar-muted" /></div>} account={<>{actions}<UserMenu /></>} wide={wide}>{children}</ShellFrame>;
}

/** The shared frame: sidebar (a drawer on small screens), top bar with the page title and an account control, and the page. */
export function ShellFrame({ locale, sidebar, footer, account, badge, children, wide = false }: { locale: Locale; sidebar?: ReactNode; footer?: ReactNode; account: ReactNode; badge?: ReactNode; children: ReactNode; wide?: boolean }) {
  const text = messages(locale);
  const [title, setTitle] = useState(text.title);
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);
  useEffect(() => { document.title = title === text.title ? text.title : `${title} · ${text.title}`; }, [title, text.title]);
  const nav = (
    <div className="flex h-full flex-col gap-5 overflow-y-auto px-3 py-4">
      <div className="flex items-center gap-2 px-2"><Logo tone="light" />{badge}</div>
      {sidebar}
      {footer ? <div className="mt-auto px-2 pt-4">{footer}</div> : null}
    </div>
  );
  return (
    <TitleContext.Provider value={setTitle}>
      <div className="ui-root min-h-screen bg-canvas text-ink lg:grid lg:grid-cols-[260px_minmax(0,1fr)] print:block print:min-h-0 print:bg-white">
        <a href="#main-content" className="sr-only print:hidden z-50 rounded-[var(--radius-control)] bg-surface px-3 py-2 font-semibold text-accent shadow-[var(--shadow-overlay)] focus:not-sr-only focus:fixed focus:left-3 focus:top-3">{text.shell.skip}</a>
        <aside className="sticky top-0 hidden h-screen bg-sidebar text-sidebar-ink lg:block print:hidden">{nav}</aside>
        <div className="flex min-w-0 flex-col">
          <header className="sticky top-0 z-30 flex h-14 print:hidden items-center gap-3 border-b border-line bg-surface/95 px-4 backdrop-blur lg:px-6">
            <button type="button" onClick={() => setMenuOpen(true)} aria-label={text.shell.openMenu} className="inline-flex size-9 cursor-pointer items-center justify-center rounded-[var(--radius-control)] border-0 bg-transparent text-ink-muted hover:bg-surface-sunken lg:hidden pointer-coarse:size-11">
              <MenuIcon size={20} aria-hidden="true" />
            </button>
            <h1 id="page-title" className="min-w-0 flex-1 truncate text-[17px] font-semibold">{title}</h1>
            {account}
          </header>
          <main id="main-content" tabIndex={-1} aria-labelledby="page-title" className={cx("w-full flex-1 px-4 py-6 outline-none lg:px-8 print:p-0", wide ? "" : "mx-auto max-w-6xl")}>
            {children}
          </main>
        </div>
        <DialogPrimitive.Root open={menuOpen} onOpenChange={setMenuOpen}>
          <DialogPrimitive.Portal>
            <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-[rgb(17_28_36/0.45)] lg:hidden" />
            <DialogPrimitive.Content aria-describedby={undefined} className="ui-root fixed inset-y-0 left-0 z-50 w-[min(300px,88vw)] bg-sidebar text-sidebar-ink shadow-[var(--shadow-overlay)] lg:hidden">
              <DialogPrimitive.Title className="sr-only">{text.shell.navigation}</DialogPrimitive.Title>
              <DialogPrimitive.Close aria-label={text.overlay.close} className="absolute right-3 top-3 inline-flex size-9 cursor-pointer items-center justify-center rounded-[var(--radius-control)] border-0 bg-transparent text-sidebar-muted hover:bg-sidebar-raised hover:text-white pointer-coarse:size-11">
                <X size={18} aria-hidden="true" />
              </DialogPrimitive.Close>
              {nav}
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        </DialogPrimitive.Root>
      </div>
    </TitleContext.Provider>
  );
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "?";
}

const ITEM = "flex h-8 cursor-pointer items-center gap-2 rounded-[6px] px-2.5 text-[13px] text-ink outline-none data-[highlighted]:bg-surface-sunken pointer-coarse:h-11";

/** Account, language, and sign out. Sign out stays a form post to the backend. */
function UserMenu() {
  const { userAccount, locale, onLocaleChange, onLogout } = useAccount();
  const text = messages(locale);
  const languages = workspaceMessages(locale);
  const form = useRef<HTMLFormElement>(null);
  const [canTransfer, setCanTransfer] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    loadTransferOrganizations(controller.signal).then((items) => setCanTransfer(items.length > 0)).catch(() => setCanTransfer(false));
    return () => controller.abort();
  }, [userAccount.id]);
  return (
    <>
      <form ref={form} action={logoutUrl} method="post" hidden />
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button type="button" aria-label={text.shell.accountMenu(userAccount.display_name)} className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-full border-0 bg-transparent py-1 pl-1 pr-3 text-[13px] font-medium text-ink hover:bg-surface-sunken pointer-coarse:h-11">
            <span aria-hidden="true" className="flex size-7 items-center justify-center rounded-full bg-accent-soft text-[12px] font-semibold text-accent">{initials(userAccount.display_name)}</span>
            <span aria-hidden="true" className="hidden max-w-40 truncate sm:inline">{userAccount.display_name}</span>
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="end" sideOffset={6} className="ui-root z-50 min-w-60 rounded-[10px] border border-line bg-surface p-1 shadow-[var(--shadow-overlay)]">
            <DropdownMenu.Label className="px-2.5 py-2 text-[13px] text-ink-muted">{text.signedIn} {userAccount.display_name}</DropdownMenu.Label>
            <DropdownMenu.Separator className="my-1 h-px bg-line" />
            <DropdownMenu.Label className="px-2.5 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">{text.language}</DropdownMenu.Label>
            <DropdownMenu.RadioGroup value={locale} onValueChange={(value) => void onLocaleChange(value as Locale)}>
              {(["en", "fi"] as const).map((value) => (
                <DropdownMenu.RadioItem key={value} value={value} className={ITEM}>
                  <span className="inline-flex w-4" aria-hidden="true"><DropdownMenu.ItemIndicator><Check size={14} /></DropdownMenu.ItemIndicator></span>
                  {value === "en" ? languages.languageEnglish : languages.languageFinnish}
                </DropdownMenu.RadioItem>
              ))}
            </DropdownMenu.RadioGroup>
            {canTransfer ? (
              <>
                <DropdownMenu.Separator className="my-1 h-px bg-line" />
                <DropdownMenu.Item asChild className={ITEM}><Link to="/data-transfer">{dataTransferMessages(locale).menu}</Link></DropdownMenu.Item>
              </>
            ) : null}
            <DropdownMenu.Separator className="my-1 h-px bg-line" />
            <DropdownMenu.Item className={ITEM} onSelect={() => { onLogout(); form.current?.submit(); }}>
              <LogOut size={14} aria-hidden="true" />{text.signOut}
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </>
  );
}
