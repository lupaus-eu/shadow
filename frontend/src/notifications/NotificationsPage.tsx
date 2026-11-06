import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";

import { Section, MUTED, ROW, ROWS, formatDate, formatDateTime } from "../admin/Section";
import { workspaceMessages } from "../i18n";
import { Alert, Badge, Button, Choice, EmptyState } from "../ui";
import { organizationHref } from "../shell/nav";
import { usePageTitle } from "../shell/AppShell";
import { useOrganization } from "../shell/organization-outlet";
import { loadNotifications, markAllRead, markRead } from "./client";
import { NOTIFICATIONS_CHANGED } from "./NotificationBell";
import { notificationHref, notificationText, type NotificationItem } from "./text";

/** `/organizations/:id/notifications`: the signed-in person's own notifications, newest first. */
export function NotificationsPage() {
  const { workspace, locale } = useOrganization();
  const copy = workspaceMessages(locale).notifications;
  const organizationId = workspace.organization.id;
  usePageTitle(copy.title);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const load = useCallback(async (cursor: string | null, replace: boolean) => {
    setFailed(false);
    try {
      const page = await loadNotifications(organizationId, { cursor, unread: unreadOnly });
      setItems((current) => (replace ? page.items : [...current, ...page.items]));
      setNext(page.next_cursor);
    } catch { setFailed(true); }
    setLoaded(true);
  }, [organizationId, unreadOnly]);
  useEffect(() => { void load(null, true); }, [load]);
  const changed = () => window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
  async function read(id: string) {
    try { await markRead(organizationId, id); setItems((current) => current.map((item) => (item.id === id ? { ...item, read_at: new Date().toISOString() } : item))); changed(); } catch { setFailed(true); }
  }
  async function readAll() {
    try { await markAllRead(organizationId); await load(null, true); changed(); } catch { setFailed(true); }
  }
  return (
    <div className="flex flex-col gap-5">
      <Section title={copy.title} description={copy.description} actions={<><Choice type="checkbox" checked={unreadOnly} onChange={(event) => setUnreadOnly(event.target.checked)} label={copy.unreadOnly} /><Button onClick={() => void readAll()}>{copy.markAllRead}</Button><Link to={`${organizationHref(organizationId)}/notification-settings`} className="text-[13px]">{copy.settings.link}</Link></>}>
        {failed ? <Alert tone="danger" role="alert">{copy.failed}</Alert> : null}
        {loaded && items.length === 0 && !failed ? <EmptyState title={copy.empty} /> : null}
        {items.length ? (
          <ol aria-label={copy.title} className={ROWS}>
            {items.map((item) => {
              const href = notificationHref(item, organizationId);
              return (
                <li key={item.id} className={ROW}>
                  {item.read_at === null ? <Badge tone="info">{copy.unread}</Badge> : null}
                  <span className={`flex-1 text-[13px] ${item.read_at === null ? "font-semibold" : ""}`}>{notificationText(item, copy, (iso) => formatDate(locale, iso))}</span>
                  <time dateTime={item.created_at} className={`${MUTED} shrink-0 tabular-nums`}>{formatDateTime(locale, item.created_at)}</time>
                  {href ? <Link to={href} onClick={() => void read(item.id)} className="text-[13px]">{copy.open}</Link> : null}
                  {item.read_at === null ? <Button size="sm" onClick={() => void read(item.id)}>{copy.markRead}</Button> : null}
                </li>
              );
            })}
          </ol>
        ) : null}
        {next !== null ? <div><Button onClick={() => void load(next, false)}>{copy.more}</Button></div> : null}
      </Section>
    </div>
  );
}
