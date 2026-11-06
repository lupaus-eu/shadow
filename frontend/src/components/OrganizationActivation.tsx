import { useEffect, useState, type FormEvent } from "react";

import type { UserAccount } from "../auth-client";
import { messages, type Locale } from "../i18n";
import { loadLegalDocuments, requiredDocuments, type LegalDocumentSummary } from "../legal/client";
import { legalMessages } from "../legal/messages";
import { Alert, Button, Choice, Field, Select, TextInput } from "../ui";
import {
  createOrganizationSignup,
  loadOrganizationSignup,
  type OrganizationSignup,
} from "../organization-client";

function signupIdFromLocation(): string | null {
  const match = window.location.pathname.match(
    /^\/organization-signups\/([0-9a-f-]+)$/,
  );
  return match?.[1] ?? null;
}

export function OrganizationActivation({
  userAccount,
  locale,
}: {
  userAccount: UserAccount;
  locale: Locale;
}) {
  const organizationId = signupIdFromLocation();
  if (organizationId) {
    return (
      <OrganizationActivationStatus
        organizationId={organizationId}
        locale={locale}
      />
    );
  }
  return <OrganizationSignupForm userAccount={userAccount} locale={locale} />;
}

function OrganizationSignupForm({
  userAccount,
  locale,
}: {
  userAccount: UserAccount;
  locale: Locale;
}) {
  const labels = messages(locale).organization;
  const [seats, setSeats] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [failed, setFailed] = useState(false);
  // The published required documents; null while loading. Nothing shows while none is published.
  const [required, setRequired] = useState<LegalDocumentSummary[] | null>(null);
  const [ticked, setTicked] = useState<Record<string, boolean>>({});
  const legal = legalMessages(locale);
  useEffect(() => {
    const controller = new AbortController();
    loadLegalDocuments(locale, controller.signal).then(
      (items) => setRequired(requiredDocuments(items)),
      () => { if (!controller.signal.aborted) setRequired([]); },
    );
    return () => controller.abort();
  }, [locale]);
  const allTicked = required !== null && required.every((item) => ticked[item.key]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setFailed(false);
    const form = new FormData(event.currentTarget);
    try {
      const signup = await createOrganizationSignup({
        organization_name: String(form.get("organization_name")),
        time_zone: String(form.get("time_zone")),
        default_locale: String(form.get("default_locale")) as Locale,
        billing_name: String(form.get("billing_name")),
        billing_email: String(form.get("billing_email")),
        initial_seats: seats,
        accepted_documents: (required ?? []).map((item) => ({ document_key: item.key, version: item.version, locale })),
      });
      if (!signup.checkout_url) {
        throw new Error("Checkout URL missing");
      }
      window.location.assign(signup.checkout_url);
    } catch {
      setSubmitting(false);
      setFailed(true);
    }
  }

  return (
    <section className="organization-signup flex flex-col gap-4" aria-labelledby="signup-title">
      <div className="flex flex-col gap-1">
        <h2 id="signup-title" className="m-0 text-xl font-semibold tracking-tight">{labels.title}</h2>
        <p className="m-0 text-[13px] text-ink-muted">{labels.description}</p>
      </div>
      <form className="signup-form grid gap-4 sm:grid-cols-2" onSubmit={(event) => void submit(event)}>
        <Field label={labels.organizationName}>{(control) => <TextInput {...control} name="organization_name" required maxLength={200} />}</Field>
        <Field label={labels.timeZone}>{(control) => <TextInput {...control} name="time_zone" required defaultValue={Intl.DateTimeFormat().resolvedOptions().timeZone} />}</Field>
        <Field label={labels.locale}>{(control) => <Select {...control} name="default_locale" defaultValue={locale}><option value="en">English</option><option value="fi">Suomi</option></Select>}</Field>
        <Field label={labels.billingName}>{(control) => <TextInput {...control} name="billing_name" required maxLength={200} />}</Field>
        <Field label={labels.billingEmail}>{(control) => <TextInput {...control} name="billing_email" type="email" required defaultValue={userAccount.email} />}</Field>
        <Field label={labels.seats}>{(control) => <TextInput {...control} name="initial_seats" type="number" min={1} max={10000} required value={seats} onChange={(event) => setSeats(Math.max(1, Number(event.currentTarget.value)))} />}</Field>
        <div className="price-summary flex flex-col gap-0.5 rounded-[10px] bg-surface-subtle p-3.5 sm:col-span-2" aria-live="polite">
          <strong className="text-sm font-semibold">{labels.price(seats)}</strong>
          <span className="text-xs text-ink-muted">{labels.tax}</span>
        </div>
        {required && required.length > 0 ? (
          <fieldset className="m-0 flex flex-col gap-2 border-0 p-0 sm:col-span-2">
            <legend className="mb-1 p-0 text-[13px] font-semibold">{legal.signup.heading}</legend>
            {required.map((item) => (
              <Choice
                key={item.key}
                name={`accept_${item.key}`}
                required
                checked={ticked[item.key] === true}
                onChange={(event) => setTicked((current) => ({ ...current, [item.key]: event.target.checked }))}
                label={<>{legal.signup.accept(item.title)} (<a className="text-accent underline" href={`/legal/${item.key}`} target="_blank" rel="noopener noreferrer">{item.title}</a> {legal.signup.read})</>}
              />
            ))}
          </fieldset>
        ) : null}
        {failed ? <Alert tone="danger" role="alert" className="sm:col-span-2">{labels.failed}</Alert> : null}
        <div className="sm:col-span-2"><Button type="submit" variant="primary" disabled={submitting || required === null || !allTicked && required.length > 0}>{submitting ? labels.submitting : labels.submit}</Button></div>
      </form>
    </section>
  );
}

function OrganizationActivationStatus({
  organizationId,
  locale,
}: {
  organizationId: string;
  locale: Locale;
}) {
  const labels = messages(locale).organization;
  const [signup, setSignup] = useState<OrganizationSignup | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;

    async function refresh() {
      try {
        const result = await loadOrganizationSignup(
          organizationId,
          controller.signal,
        );
        setSignup(result);
        if (result.status === "pending_activation") {
          timer = window.setTimeout(() => void refresh(), 1500);
        }
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFailed(true);
        }
      }
    }

    void refresh();
    return () => {
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [organizationId]);

  const heading = "m-0 text-xl font-semibold tracking-tight";
  const text = "m-0 text-[13px] text-ink-muted";
  if (failed) {
    return <Alert tone="danger" role="alert">{labels.failed}</Alert>;
  }
  if (!signup || signup.status === "pending_activation") {
    return (
      <section aria-live="polite" className="flex flex-col gap-2">
        <h2 className={heading}>{labels.pending}</h2>
        <p className={text}>{labels.pendingDescription}</p>
      </section>
    );
  }
  if (signup.status === "expired") {
    return (
      <section className="flex flex-col gap-2">
        <h2 className={heading}>{labels.expired}</h2>
        <p className={text}>{labels.expiredDescription}</p>
      </section>
    );
  }
  return (
    <section className="activation-complete flex flex-col gap-3">
      <h2 className={heading}>{labels.active(signup.organization_name)}</h2>
      <p className={text}>{labels.ownerActive}</p>
      <p className="m-0 text-[13px] font-medium">
        {signup.initial_content?.yearclock_name} ·{" "}
        {signup.initial_content?.lane_name}
      </p>
      <a
        className="inline-flex h-10 w-fit items-center justify-center rounded-[var(--radius-control)] bg-accent px-4 text-sm font-semibold text-white no-underline hover:bg-accent-hover"
        href={`/organizations/${signup.organization_id}`}
      >
        {messages(locale).enterOrganization}
      </a>
    </section>
  );
}
