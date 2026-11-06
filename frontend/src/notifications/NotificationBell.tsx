import { Bell } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import type { Locale } from "../i18n";
import { workspaceMessages } from "../i18n";
import { organizationHref } from "../shell/nav";
import { loadUnreadCount } from "./client";

export const NOTIFICATIONS_CHANGED = "yearclock:notifications-changed";
const POLL_MILLISECONDS = 60_000;

/** The top-bar bell: a link to the inbox with the unread count, refreshed every minute while the tab is visible. */
export function NotificationBell({ organizationId, locale }: { organizationId: string; locale: Locale }) {
  const copy = workspaceMessages(locale).notifications;
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    let current = true;
    const refresh = () => { if (document.visibilityState === "visible") void loadUnreadCount(organizationId).then((count) => { if (current) setUnread(count); }, () => {}); };
    refresh();
    const timer = window.setInterval(refresh, POLL_MILLISECONDS);
    window.addEventListener(NOTIFICATIONS_CHANGED, refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { current = false; window.clearInterval(timer); window.removeEventListener(NOTIFICATIONS_CHANGED, refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [organizationId]);
  return (
    <Link to={`${organizationHref(organizationId)}/notifications`} aria-label={copy.bell(unread)} className="relative inline-flex size-9 items-center justify-center rounded-[var(--radius-control)] text-ink-muted no-underline hover:bg-surface-sunken pointer-coarse:size-11">
      <Bell size={18} aria-hidden="true" />
      {unread > 0 ? <span aria-hidden="true" className="absolute right-0.5 top-0.5 min-w-4 rounded-full bg-accent px-1 text-center text-[10px] font-semibold leading-4 text-white">{unread > 99 ? "99+" : unread}</span> : null}
    </Link>
  );
}
