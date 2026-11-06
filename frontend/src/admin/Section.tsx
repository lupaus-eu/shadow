import { useId, type ReactNode } from "react";

import type { Locale } from "../i18n";
import { cx } from "../ui";

/** A titled card on an administration page; the title names the region. */
export function Section({ title, description, actions, children, className, tone = "default", headingLevel = 2 }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string; tone?: "default" | "danger"; headingLevel?: 2 | 3 }) {
  const id = useId();
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section aria-labelledby={id} className={cx("flex flex-col gap-4 rounded-[var(--radius-card)] border bg-surface p-5 shadow-[var(--shadow-card)]", tone === "danger" ? "border-danger" : "border-line", className)}>
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <Heading id={id} className={cx("m-0 text-[15px] font-semibold", tone === "danger" ? "text-danger" : "text-ink")}>{title}</Heading>
          {description ? <p className="m-0 text-[13px] text-ink-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

/** The one-line description under the page title. */
export function Intro({ children }: { children: ReactNode }) {
  return <p className="m-0 max-w-3xl text-[13px] text-ink-muted">{children}</p>;
}

export function AdminPage({ intro, children }: { intro: ReactNode; children: ReactNode }) {
  return <div className="flex flex-col gap-5">{intro ? <Intro>{intro}</Intro> : null}{children}</div>;
}

/** A list of rows separated by lines inside a card. */
export const ROWS = "m-0 flex list-none flex-col divide-y divide-line rounded-[10px] border border-line p-0";
export const ROW = "flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3";
export const MUTED = "text-[13px] text-ink-muted";
export const INLINE_FORM = "flex flex-wrap items-end gap-3";

const tag = (locale: Locale) => (locale === "fi" ? "fi-FI" : "en-GB");
export const formatDate = (locale: Locale, value: string, style: "medium" | "long" = "medium") => new Intl.DateTimeFormat(tag(locale), { dateStyle: style }).format(new Date(value));
export const formatDateTime = (locale: Locale, value: string) => new Intl.DateTimeFormat(tag(locale), { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
