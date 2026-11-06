import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { cx } from "./cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "ghost-danger";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover border border-transparent",
  secondary: "bg-surface text-ink border border-line hover:bg-surface-subtle",
  ghost: "bg-transparent text-ink border border-transparent hover:bg-surface-sunken",
  danger: "bg-danger text-white hover:bg-danger-hover border border-transparent",
  "ghost-danger": "bg-transparent text-danger border border-transparent hover:bg-danger-soft",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: "sm" | "md"; icon?: ReactNode };

/** The one button: 34 px (sm 32 px, 44 px on touch screens), visible focus, disabled dims. */
export const Button = forwardRef<HTMLButtonElement, Props>(function Button({ variant = "secondary", size = "md", icon, className, children, type = "button", ...props }, ref) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-control)] font-medium whitespace-nowrap cursor-pointer transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50 pointer-coarse:min-h-11",
        size === "md" ? "h-[34px] px-3 text-[13px]" : "h-8 px-2.5 text-[13px]",
        VARIANTS[variant],
        className,
      )}
      {...props}
    >
      {icon ? <span aria-hidden="true" className="inline-flex">{icon}</span> : null}
      {children}
    </button>
  );
});

/** An icon-only button: the label is required and becomes the accessible name. */
export const IconButton = forwardRef<HTMLButtonElement, Omit<Props, "children" | "icon"> & { label: string; icon: ReactNode }>(function IconButton({ label, icon, className, variant = "secondary", ...props }, ref) {
  return (
    <Button ref={ref} variant={variant} aria-label={label} title={label} className={cx("w-[34px] px-0 pointer-coarse:min-w-11", className)} {...props}>
      <span aria-hidden="true" className="inline-flex">{icon}</span>
    </Button>
  );
});
