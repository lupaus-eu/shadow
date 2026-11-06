import { useEffect, useState } from "react";

import { messages, workspaceMessages, type Locale } from "../i18n";
import { cancelSubscription, changeSeatCapacity, ContactRateLimitedError, loadBillingContact, loadNextCharge, loadPayments, loadSeatProjection, previewSeatIncrease, saveBillingContact, startResubscription, undoCancellation, type CancelReason, type NextCharge, type Payments, type SeatIncreasePreview, type SeatProjection, type Subscription } from "../organization-client";
import { Alert, Button, Dialog, Field, Select, TextInput, useToast } from "../ui";
import { BillingPortalButton, subscriptionMessage } from "./SubscriptionNotice";
import { MUTED, Section, formatDate } from "./Section";

const money = (locale: Locale, amount: number, currency: string) => new Intl.NumberFormat(locale, { style: "currency", currency: currency.toUpperCase() }).format(amount / 100);

/** What Stripe will charge next and the rules for seat changes, from Stripe on each visit. */
function NextChargeLine({ organizationId, locale, revision }: { organizationId: string; locale: Locale; revision: string }) {
  const text = workspaceMessages(locale).billingOverview.nextCharge;
  const [charge, setCharge] = useState<NextCharge | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setCharge(null);
    void loadNextCharge(organizationId, controller.signal).then(setCharge, () => undefined);
    return () => controller.abort();
  }, [organizationId, revision]);
  if (!charge) return null;
  const line = charge.status === "scheduled" && charge.amount !== null && charge.currency && charge.charge_date ? text.scheduled(money(locale, charge.amount, charge.currency), formatDate(locale, charge.charge_date), charge.seats)
    : charge.status === "none_cancelled" ? text.cancelled : charge.status === "none_ended" ? text.ended : text.unavailable;
  return (
    <div className="flex flex-col gap-1">
      <p className="m-0 text-[13px]"><strong className="font-semibold">{text.title}:</strong> {line}</p>
      <p className="m-0 text-[13px] text-ink-muted">{text.rules}</p>
    </div>
  );
}

/** The Owner's subscription card: its state, cancelling and undoing it, and the billing portal. */
export function SubscriptionCard({ organizationId, subscription, locale, onChanged }: { organizationId: string; subscription: Subscription; locale: Locale; onChanged: () => void }) {
  const text = workspaceMessages(locale).subscription;
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState<CancelReason | "none">("none");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const day = (value: string | null) => (value ? formatDate(locale, value, "long") : "");
  const [projection, setProjection] = useState<SeatProjection | null>(null);
  const [seats, setSeats] = useState("");
  const [starting, setStarting] = useState(false);
  const [startFailed, setStartFailed] = useState(false);
  const returning = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("checkout") : null;
  const ended = subscription.ended === true;
  useEffect(() => {
    if (!ended) return;
    const controller = new AbortController();
    void loadSeatProjection(organizationId, controller.signal).then((result) => { setProjection(result); setSeats((current) => current || String(Math.max(result.occupied + result.reserved, result.purchased))); }, () => undefined);
    return () => controller.abort();
  }, [ended, organizationId]);
  // Back from Checkout: the payment is confirmed by Stripe's webhook, so look again every few seconds.
  useEffect(() => {
    if (!ended || returning !== "returned") return;
    let tries = 0;
    const timer = window.setInterval(() => { tries += 1; onChanged(); if (tries >= 15) window.clearInterval(timer); }, 4000);
    return () => window.clearInterval(timer);
  }, [ended, returning, onChanged]);
  const minimum = projection ? projection.occupied + projection.reserved : 1;
  const validSeats = Number.isInteger(Number(seats)) && Number(seats) >= minimum;
  async function subscribeAgain() {
    setStarting(true);
    setStartFailed(false);
    try { window.location.assign(await startResubscription(organizationId, Number(seats))); } catch { setStartFailed(true); setStarting(false); }
  }
  const status = ended ? text.endedStatus : subscription.cancel_at_period_end && subscription.current_period_end ? text.status.cancelScheduled(day(subscription.current_period_end))
    : subscription.state === "read_only" ? text.status.readOnly
    : subscription.state === "grace" && subscription.grace_expires_at ? text.status.grace(day(subscription.grace_expires_at))
    : subscription.current_period_end ? text.status.active(day(subscription.current_period_end)) : text.status.activeNoDate;
  async function run(action: () => Promise<{ current_period_end: string | null }>, done: (result: { current_period_end: string | null }) => string) {
    setBusy(true);
    setFailed(false);
    try { const result = await action(); setAsking(false); toast(done(result)); onChanged(); } catch { setFailed(true); }
    setBusy(false);
  }
  const cancel = () => void run(() => cancelSubscription(organizationId, reason === "none" ? null : reason), (result) => text.cancel.done(day(result.current_period_end)));
  const undo = () => void run(() => undoCancellation(organizationId), () => text.cancel.undone);
  return (
    <Section title={text.title} actions={<BillingPortalButton organizationId={organizationId} locale={locale} />}>
      <p className="m-0 text-[13px]" role="status">{status}</p>
      {subscription.ended ? null : <NextChargeLine organizationId={organizationId} locale={locale} revision={`${subscription.state}|${subscription.cancel_at_period_end}|${subscription.current_period_end}`} />}
      {failed && !asking ? <Alert tone="danger" role="alert">{text.cancel.failed}</Alert> : null}
      {ended ? (
        <div className="flex flex-col gap-3 border-t border-line pt-3">
          <h3 className="m-0 text-[14px] font-semibold">{text.resubscribe.title}</h3>
          <p className="m-0 text-[13px] text-ink-muted">{text.resubscribe.description}</p>
          {returning === "returned" ? <Alert tone="info"><p role="status" className="m-0">{text.resubscribe.waiting}</p></Alert> : null}
          {returning === "cancelled" ? <Alert tone="warning"><p role="status" className="m-0">{text.resubscribe.cancelled}</p></Alert> : null}
          <Field label={text.resubscribe.seats} hint={text.resubscribe.minimum(minimum)} className="w-40">{(control) => <TextInput {...control} type="number" min={minimum} value={seats} onChange={(event) => setSeats(event.target.value)} />}</Field>
          {startFailed ? <Alert tone="danger" role="alert">{text.resubscribe.failed}</Alert> : null}
          <div><Button variant="primary" disabled={!validSeats || starting} onClick={() => void subscribeAgain()}>{starting ? text.resubscribe.working : text.resubscribe.action}</Button></div>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {ended ? null : subscription.cancel_at_period_end ? <Button disabled={busy} onClick={undo}>{text.cancel.undo}</Button> : <Button variant="danger" onClick={() => { setFailed(false); setAsking(true); }}>{text.cancel.action}</Button>}
      </div>
      <Dialog open={asking} onOpenChange={setAsking} title={text.cancel.title} description={text.cancel.description(day(subscription.current_period_end))}
        footer={<><Button onClick={() => setAsking(false)}>{text.cancel.keep}</Button><Button variant="danger" disabled={busy} onClick={cancel}>{text.cancel.confirm}</Button></>}>
        <div className="flex flex-col gap-3">
          <p className="m-0 text-[13px]">{text.cancel.consequence}</p>
          <p className="m-0 text-[13px] text-ink-muted">{text.cancel.seatDecrease}</p>
          <Field label={text.cancel.reason}>{(control) => <Select {...control} value={reason} onChange={(event) => setReason(event.target.value as CancelReason | "none")}>{(["none", "too_expensive", "not_needed", "switching", "other"] as const).map((value) => <option key={value} value={value}>{text.cancel.reasons[value]}</option>)}</Select>}</Field>
          {failed ? <Alert tone="danger" role="alert">{text.cancel.failed}</Alert> : null}
        </div>
      </Dialog>
    </Section>
  );
}

/** The billing name and email the Owner may edit here; address, VAT ID, and payment method stay in the portal. */
export function BillingContact({ organizationId, locale }: { organizationId: string; locale: Locale }) {
  const text = workspaceMessages(locale).subscription.contact;
  const toast = useToast();
  const [saved, setSaved] = useState<{ billing_name: string; billing_email: string } | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let current = true;
    void loadBillingContact(organizationId).then((contact) => { if (current) { setSaved(contact); setName(contact.billing_name); setEmail(contact.billing_email); } }, () => { if (current) setError(text.failed); });
    return () => { current = false; };
  }, [organizationId]);
  const valid = name.trim().length > 0 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
  const changed = saved !== null && (name.trim() !== saved.billing_name || email.trim() !== saved.billing_email);
  async function save() {
    setBusy(true);
    setError(null);
    try { const contact = await saveBillingContact(organizationId, { billing_name: name.trim(), billing_email: email.trim() }); setSaved(contact); setName(contact.billing_name); setEmail(contact.billing_email); toast(text.saved); }
    catch (failure) { setError(failure instanceof ContactRateLimitedError ? text.rateLimited(Math.max(1, Math.ceil(failure.retryAfterSeconds / 3600))) : text.failed); }
    setBusy(false);
  }
  return (
    <Section title={text.title} description={text.description}>
      <div className="flex flex-wrap items-end gap-3">
        <Field label={text.name} className="w-64">{(control) => <TextInput {...control} value={name} maxLength={200} onChange={(event) => setName(event.target.value)} />}</Field>
        <Field label={text.email} className="w-72">{(control) => <TextInput {...control} type="email" value={email} maxLength={320} onChange={(event) => setEmail(event.target.value)} />}</Field>
        <Button variant="primary" disabled={!changed || !valid || busy} onClick={() => void save()}>{text.save}</Button>
      </div>
      {error ? <Alert tone="danger" role="alert">{error}</Alert> : null}
    </Section>
  );
}

export function SeatCapacity({ organizationId, locale }: { organizationId: string; locale: Locale }) {
  const labels = messages(locale).seatCapacity;
  const [projection, setProjection] = useState<SeatProjection | null>(null);
  const [target, setTarget] = useState("");
  const [preview, setPreview] = useState<SeatIncreasePreview | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void loadSeatProjection(organizationId, controller.signal)
      .then((result) => { setProjection(result); setTarget(String(result.purchased)); })
      .catch((error) => { if (!(error instanceof DOMException && error.name === "AbortError")) setFailed(true); });
    return () => controller.abort();
  }, [organizationId]);

  if (failed) return <Alert tone="danger" role="alert">{labels.failed}</Alert>;
  if (!projection) return null;
  const targetSeats = Number(target);
  const isIncrease = targetSeats > projection.purchased;
  const validTarget = Number.isInteger(targetSeats) && targetSeats > 0;
  const amount = preview ? new Intl.NumberFormat(locale, { style: "currency", currency: preview.currency }).format(preview.amount_due / 100) : null;

  async function requestPreview() {
    setFailed(false);
    try { setPreview(await previewSeatIncrease(organizationId, targetSeats, projection!.version)); } catch { setFailed(true); }
  }
  async function submitChange() {
    setFailed(false);
    try { setProjection(await changeSeatCapacity(organizationId, targetSeats, projection!.version, preview?.preview_id ?? null)); setPreview(null); } catch { setFailed(true); }
  }
  const counts: Array<[string, number]> = [[labels.purchased, projection.purchased], [labels.occupied, projection.occupied], [labels.reserved, projection.reserved], [labels.available, projection.available]];
  return (
    <Section title={labels.title}>
      <dl className="m-0 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {counts.map(([label, value]) => (
          <div key={label} className="rounded-[10px] border border-line bg-surface-subtle px-4 py-3">
            <dt className={MUTED}>{label}</dt>
            <dd className="m-0 text-xl font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      {projection.pending_change ? (
        <Alert tone="info" role="status">
          {projection.pending_change.status === "pending_payment"
            ? labels.pendingPayment(projection.pending_change.target_seats)
            : labels.scheduled(projection.pending_change.target_seats, new Intl.DateTimeFormat(locale).format(new Date(projection.pending_change.effective_at!)))}
        </Alert>
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <Field label={labels.input} className="w-40">{(control) => <TextInput {...control} type="number" min={1} value={target} onChange={(event) => { setTarget(event.target.value); setPreview(null); }} />}</Field>
          {isIncrease && !preview ? <Button disabled={!validTarget} onClick={requestPreview}>{labels.preview}</Button> : null}
          {preview && amount ? <><p className="m-0 text-[13px]">{labels.dueNow(amount)}</p><Button variant="primary" onClick={submitChange}>{labels.confirm}</Button></> : null}
          {!isIncrease && targetSeats !== projection.purchased ? <Button disabled={!validTarget} onClick={submitChange}>{labels.schedule}</Button> : null}
        </div>
      )}
    </Section>
  );
}

/** The latest Stripe invoices, newest first. */
export function PaymentHistory({ organizationId, locale }: { organizationId: string; locale: Locale }) {
  const text = workspaceMessages(locale).billingOverview.payments;
  const [payments, setPayments] = useState<Payments | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void loadPayments(organizationId, controller.signal).then(setPayments, () => undefined);
    return () => controller.abort();
  }, [organizationId]);
  if (!payments) return null;
  return (
    <Section title={text.title} description={text.description}>
      {payments.status === "unavailable" ? <Alert tone="warning" role="status">{text.unavailable}</Alert>
        : payments.invoices.length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{text.empty}</p>
        : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-[13px]">
              <thead><tr className="border-b border-line">{[text.date, text.amount, text.status, text.reason, text.invoice].map((heading) => <th key={heading} scope="col" className="py-2 pr-4 font-semibold">{heading}</th>)}</tr></thead>
              <tbody>
                {payments.invoices.map((invoice) => (
                  <tr key={invoice.id} className="border-b border-line last:border-0">
                    <td className="py-2 pr-4">{formatDate(locale, invoice.date)}</td>
                    <td className="py-2 pr-4 tabular-nums">{money(locale, invoice.amount, invoice.currency)}</td>
                    <td className="py-2 pr-4">{text.states[invoice.state] ?? invoice.state}</td>
                    <td className="py-2 pr-4">{text.reasons[invoice.reason] ?? text.reasons.other}</td>
                    <td className="py-2 pr-4">{invoice.hosted_invoice_url ? <a href={invoice.hosted_invoice_url} target="_blank" rel="noopener noreferrer" aria-label={text.viewInvoice(formatDate(locale, invoice.date))}>{text.invoice}</a> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </Section>
  );
}
