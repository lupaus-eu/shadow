import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";

import type { Locale } from "../i18n";
import { acceptLegalDocument, dueDocuments, loadOrganizationLegal, type OrganizationLegalDocument } from "../legal/client";
import { legalMessages } from "../legal/messages";
import { Alert, Badge, Button } from "../ui";
import { MUTED, ROW, ROWS, Section, formatDate } from "./Section";

/** The Owner's documents, kept fresh after each acceptance. `null` means not loaded (or the person may not see it). */
function useOrganizationLegal(organizationId: string, locale: Locale, enabled: boolean) {
  const [items, setItems] = useState<OrganizationLegalDocument[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    loadOrganizationLegal(organizationId, locale, controller.signal).then(
      (documents) => { setItems(documents); setFailed(false); },
      () => { if (!controller.signal.aborted) setFailed(true); },
    );
    return () => controller.abort();
  }, [organizationId, locale, enabled]);
  const replace = useCallback((item: OrganizationLegalDocument) => setItems((current) => current?.map((entry) => (entry.key === item.key ? item : entry)) ?? current), []);
  return { items, failed, replace };
}

/** Settings block for Owners: what was accepted, by whom and when, and the button for a due version. */
export function LegalDocuments({ organizationId, locale }: { organizationId: string; locale: Locale }) {
  const text = legalMessages(locale).owner;
  const { items, failed, replace } = useOrganizationLegal(organizationId, locale, true);
  const [saving, setSaving] = useState<string | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);
  async function accept(item: OrganizationLegalDocument) {
    setSaving(item.key);
    setSaveFailed(false);
    try { replace(await acceptLegalDocument(organizationId, item.key, item.current_version, locale)); } catch { setSaveFailed(true); }
    setSaving(null);
  }
  if (items === null && !failed) return null;
  const shown = (items ?? []).filter((item) => item.acceptance === "required");
  return (
    <Section title={text.title} description={text.description}>
      {failed || saveFailed ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      <ul className={ROWS}>
        {shown.map((item) => (
          <li key={item.key} className={ROW}>
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="flex flex-wrap items-center gap-2 text-[13px] font-semibold">
                {item.title}
                {item.state === "acceptance_due" ? <Badge tone="warning">{text.due}</Badge> : null}
              </span>
              <span className={MUTED}>
                {item.accepted_version === null
                  ? text.notAccepted
                  : text.accepted(item.accepted_version, formatDate(locale, item.accepted_at ?? ""), item.accepted_by_former_member ? text.formerMember : item.accepted_by_name ?? text.formerMember)}
              </span>
            </div>
            <Link className="text-[13px] text-accent" to={`/legal/${item.key}`} target="_blank" rel="noopener noreferrer">{text.open}</Link>
            {item.state === "acceptance_due" ? (
              <Button variant="primary" disabled={saving === item.key} onClick={() => void accept(item)}>
                {saving === item.key ? text.accepting : `${text.accept} (${text.version(item.current_version)})`}
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    </Section>
  );
}

/** Shown to Owners while a required version is due and its date has passed. */
export function LegalDueBanner({ organizationId, locale, isOwner }: { organizationId: string; locale: Locale; isOwner: boolean }) {
  const text = legalMessages(locale).owner;
  const { items } = useOrganizationLegal(organizationId, locale, isOwner);
  const due = items ? dueDocuments(items) : [];
  if (!isOwner || due.length === 0) return null;
  return (
    <Alert tone="warning" role="status">
      {text.banner(due.map((item) => item.title).join(", "))}{" "}
      <Link className="font-semibold underline" to={`/organizations/${organizationId}/admin/settings`}>{text.bannerAction}</Link>
    </Alert>
  );
}
