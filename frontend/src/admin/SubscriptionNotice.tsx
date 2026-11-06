import { useState } from "react";

import { workspaceMessages, type Locale } from "../i18n";
import { openBillingPortal, type Subscription } from "../organization-client";
import { Alert, Button } from "../ui";
import { formatDate } from "./Section";

export function subscriptionMessage(subscription: Subscription, locale: Locale): string | null {
  const text = workspaceMessages(locale).subscription;
  if (subscription.ended) return text.ended;
  if (subscription.state === "read_only") return text.readOnly;
  if (subscription.state === "grace" && subscription.grace_expires_at) return text.grace(formatDate(locale, subscription.grace_expires_at, "long"));
  if (subscription.cancel_at_period_end && subscription.current_period_end) return text.cancelScheduled(formatDate(locale, subscription.current_period_end, "long"));
  return null;
}

/** Opens the Stripe billing portal (Owners only; also while read-only). */
export function BillingPortalButton({ organizationId, locale, variant = "secondary" }: { organizationId: string; locale: Locale; variant?: "primary" | "secondary" }) {
  const text = workspaceMessages(locale).subscription;
  const [failed, setFailed] = useState(false);
  async function portal() {
    setFailed(false);
    try { window.location.assign(await openBillingPortal(organizationId)); } catch { setFailed(true); }
  }
  return <span className="inline-flex flex-col gap-1"><Button variant={variant} onClick={() => void portal()}>{text.manage}</Button>{failed ? <span role="alert" className="text-xs font-medium text-danger">{text.failed}</span> : null}</span>;
}

/** A banner when the subscription needs attention; nothing when all is well. */
export function SubscriptionNotice({ organizationId, subscription, isOwner, locale }: { organizationId: string; subscription: Subscription; isOwner: boolean; locale: Locale }) {
  const text = workspaceMessages(locale).subscription;
  const message = subscriptionMessage(subscription, locale);
  if (!message) return null;
  return (
    <section aria-label={text.title}>
      <Alert tone={subscription.state === "read_only" ? "danger" : "warning"} action={isOwner ? <BillingPortalButton organizationId={organizationId} locale={locale} /> : undefined}>
        <p role={subscription.state === "active" ? "status" : "alert"} className="m-0">{message}</p>
        {!isOwner ? <p className="m-0 mt-1 text-xs">{text.askOwner}</p> : null}
      </Alert>
    </section>
  );
}
