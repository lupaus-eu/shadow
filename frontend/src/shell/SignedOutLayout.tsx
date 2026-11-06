import type { ReactNode } from "react";

import { LegalFooterLink } from "../legal/LegalFooterLink";
import { Logo } from "./Logo";
import { MadeBy } from "./LupausMark";

/** Centred card for pages without the application shell: sign-in, onboarding, invitations, states. */
export function SignedOutLayout({ children, labelledBy, wide = false }: { children: ReactNode; labelledBy?: string; wide?: boolean }) {
  return (
    <main className="ui-root flex min-h-screen flex-col items-center justify-center gap-6 bg-canvas px-4 py-10">
      <Logo />
      <section aria-labelledby={labelledBy} className={`flex w-full flex-col gap-4 rounded-[var(--radius-card)] border border-line bg-surface p-8 shadow-[var(--shadow-card)] ${wide ? "max-w-xl" : "max-w-md"}`}>
        {children}
      </section>
      <div className="flex flex-col items-center gap-1.5 text-ink-muted"><LegalFooterLink /><MadeBy /></div>
    </main>
  );
}
