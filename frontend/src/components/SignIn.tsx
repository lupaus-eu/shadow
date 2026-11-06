import { loginUrl } from "../auth-client";
import { messages, type Locale } from "../i18n";
import { SignedOutLayout } from "../shell/SignedOutLayout";
import { Alert } from "../ui";

export function SignIn({
  expired,
  signedOut = false,
  locale,
}: {
  expired: boolean;
  signedOut?: boolean;
  locale: Locale;
}) {
  const copy = messages(locale);
  const returnTo = `${window.location.pathname}${window.location.search}`;

  return (
    <SignedOutLayout labelledBy="signin-title">
      {signedOut ? <Alert tone="success" role="status">{copy.signedOut}</Alert> : null}
      {expired && !signedOut ? <Alert tone="warning" role="alert">{copy.sessionExpired}</Alert> : null}
      <h1 id="signin-title" className="text-xl font-semibold tracking-tight">{copy.signInTitle}</h1>
      <p className="text-[13px] text-ink-muted">{copy.signInDescription}</p>
      <a className="inline-flex h-10 items-center justify-center rounded-[var(--radius-control)] bg-accent px-4 text-sm font-semibold text-white no-underline hover:bg-accent-hover pointer-coarse:h-11" href={loginUrl(returnTo)}>
        {copy.signInAction}
      </a>
    </SignedOutLayout>
  );
}
