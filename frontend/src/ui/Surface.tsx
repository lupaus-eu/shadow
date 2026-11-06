import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";

export function Card({ className, as: Tag = "section", ...props }: HTMLAttributes<HTMLElement> & { as?: "section" | "div" | "article" }) {
  return <Tag className={cx("rounded-[var(--radius-card)] border border-line bg-surface p-5 shadow-[var(--shadow-card)]", className)} {...props} />;
}

export type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

const BADGE: Record<Tone, string> = {
  neutral: "bg-surface-sunken text-ink-muted",
  accent: "bg-accent-soft text-accent",
  success: "bg-success-soft text-success-ink",
  warning: "bg-warning-soft text-warning-ink",
  danger: "bg-danger-soft text-danger",
  info: "bg-info-soft text-info-ink",
};

export function Badge({ tone = "neutral", className, children }: { tone?: Tone; className?: string; children: ReactNode }) {
  return <span className={cx("inline-flex h-[22px] items-center rounded-full px-2 text-xs font-semibold", BADGE[tone], className)}>{children}</span>;
}

const ALERT: Record<Exclude<Tone, "neutral" | "accent">, string> = {
  info: "bg-info-soft text-info-ink border-info-soft",
  success: "bg-success-soft text-success-ink border-success-soft",
  warning: "bg-warning-soft text-warning-ink border-warning-line",
  danger: "bg-danger-soft text-danger border-danger-soft",
};

/** A message box. Pass `role` ("alert" or "status") when it must be announced. */
export function Alert({ tone = "info", title, children, action, className, role }: { tone?: keyof typeof ALERT; title?: ReactNode; children?: ReactNode; action?: ReactNode; className?: string; role?: "alert" | "status" }) {
  return (
    <div role={role} className={cx("flex flex-wrap items-start gap-x-3 gap-y-2 rounded-[10px] border px-4 py-3 text-[13px]", ALERT[tone], className)}>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        {title ? <strong className="font-semibold">{title}</strong> : null}
        {children ? <div>{children}</div> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function EmptyState({ title, children, action, className }: { title: ReactNode; children?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cx("flex flex-col items-center gap-2 rounded-[var(--radius-card)] border border-dashed border-line bg-surface px-6 py-10 text-center", className)}>
      <p className="text-sm font-semibold text-ink">{title}</p>
      {children ? <p className="max-w-md text-[13px] text-ink-muted">{children}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

/** The header of a page: title, one-line description, and actions on the right. */
export function PageHeader({ title, description, eyebrow, actions, titleId }: { title: ReactNode; description?: ReactNode; eyebrow?: ReactNode; actions?: ReactNode; titleId?: string }) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {eyebrow ? <p className="text-xs font-medium text-ink-muted">{eyebrow}</p> : null}
        <h1 id={titleId} className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {description ? <p className="text-[13px] text-ink-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/** A data table in a card; columns keep their natural width, numbers align right with `numeric`. */
export function Table({ caption, children, className }: { caption?: string; children: ReactNode; className?: string }) {
  return (
    <div className={cx("overflow-x-auto rounded-[var(--radius-card)] border border-line bg-surface", className)}>
      <table className="w-full border-collapse text-[13px] [&_thead_th]:bg-surface-subtle [&_thead_th]:px-4 [&_thead_th]:py-2.5 [&_thead_th]:text-left [&_thead_th]:text-xs [&_thead_th]:font-semibold [&_thead_th]:text-ink-muted [&_td]:border-t [&_td]:border-line [&_td]:px-4 [&_td]:py-3 [&_td]:align-middle [&_tbody_th]:border-t [&_tbody_th]:border-line [&_tbody_th]:px-4 [&_tbody_th]:py-3 [&_tbody_th]:text-left [&_tbody_th]:align-middle">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        {children}
      </table>
    </div>
  );
}
