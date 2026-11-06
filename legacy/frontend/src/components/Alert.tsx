import { useState } from "react";
import type { ReactNode } from "react";

/**
 * A closable `.alert` banner. With `onDismiss` the owner clears its own state; without it
 * the alert hides itself, so callers give it a `key` that changes with its message. A
 * self-hidden alert with `onRetry` leaves a compact Retry button in its place.
 * `boxClassName` replaces the `.alert` box classes for a caller that keeps its own box.
 */
export default function Alert(props: {
  variant: "danger" | "info";
  role?: "alert" | "status" | "region";
  title?: string;
  message?: string;
  children?: ReactNode;
  id?: string;
  className?: string;
  boxClassName?: string;
  ariaLabel?: string;
  onDismiss?: () => void;
  dismissLabel?: string;
  onRetry?: () => void;
  retryLabel?: string;
  retryDisabled?: boolean;
}) {
  const [dismissed, setDismissed] = useState(false);

  const retryButton = props.onRetry ? (
    <button
      className="btn btn--secondary btn--compact"
      type="button"
      onClick={props.onRetry}
      disabled={props.retryDisabled}
    >
      {props.retryLabel ?? "Retry"}
    </button>
  ) : null;

  if (dismissed) {
    if (!retryButton) return null;
    return (
      <div className={["alert-retry", props.className].filter(Boolean).join(" ")}>
        {retryButton}
      </div>
    );
  }

  const dismissLabel =
    props.dismissLabel ?? (props.title ? `Dismiss ${props.title} notice` : "Dismiss notice");
  const className = [
    props.boxClassName ?? `alert alert--${props.variant}`,
    "alert--dismissible",
    props.className
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div id={props.id} className={className} role={props.role} aria-label={props.ariaLabel}>
      <button
        className="alert__dismiss"
        type="button"
        aria-label={dismissLabel}
        onClick={() => {
          if (props.onDismiss) props.onDismiss();
          else setDismissed(true);
        }}
      >
        <span aria-hidden="true">×</span>
      </button>
      {props.title ? <p className="alert__title">{props.title}</p> : null}
      {props.message ? <p className="alert__text">{props.message}</p> : null}
      {props.children}
      {retryButton ? <div className="form-actions">{retryButton}</div> : null}
    </div>
  );
}
