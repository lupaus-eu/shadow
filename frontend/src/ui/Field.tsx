import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cx } from "./cx";

const CONTROL = "font-[inherit] rounded-[var(--radius-control)] border border-line-strong bg-surface px-2.5 text-[13px] text-ink placeholder:text-ink-muted disabled:bg-surface-sunken disabled:text-ink-muted aria-[invalid=true]:border-danger";

export type FieldControl = { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean };

/** Controls fill their container unless the caller sets a width. */
const width = (className?: string) => (/(^|\s)w-/.test(className ?? "") ? "" : "w-full");

/** Label, optional hint and error, and one control wired to them by id. */
export function Field({ label, hint, error, children, className, hideLabel = false }: { label: ReactNode; hint?: ReactNode; error?: ReactNode; children: (control: FieldControl) => ReactNode; className?: string; hideLabel?: boolean }) {
  const id = useId();
  const described = [hint ? `${id}-hint` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className={cx("text-[13px] font-medium text-ink", hideLabel && "sr-only")}>{label}</label>
      {children({ id, "aria-describedby": described, "aria-invalid": error ? true : undefined })}
      {hint ? <p id={`${id}-hint`} className="text-xs text-ink-muted">{hint}</p> : null}
      {error ? <p id={`${id}-error`} className="text-xs font-medium text-danger">{error}</p> : null}
    </div>
  );
}

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function TextInput({ className, ...props }, ref) {
  return <input ref={ref} className={cx(CONTROL, width(className), "h-9 pointer-coarse:h-11", className)} {...props} />;
});

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cx(CONTROL, width(className), "min-h-24 py-2", className)} {...props} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, ...props }, ref) {
  return <select ref={ref} className={cx(CONTROL, width(className), "h-9 pr-8 pointer-coarse:h-11", className)} {...props} />;
});

/** A checkbox or radio with its label to the right; the whole row is the target. */
export function Choice({ type = "checkbox", label, className, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className={cx("inline-flex min-h-8 cursor-pointer items-center gap-2 text-[13px] text-ink pointer-coarse:min-h-11", props.disabled && "cursor-not-allowed text-ink-muted", className)}>
      <input type={type} className="size-4 accent-[var(--color-accent)]" {...props} />
      <span>{label}</span>
    </label>
  );
}
