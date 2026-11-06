import { useRef, type KeyboardEvent } from "react";

import { cx } from "./cx";

/** A single choice among a few options: a radio group with arrow-key movement. */
export function SegmentedControl<T extends string>({ label, options, value, onChange, className }: { label: string; options: Array<{ value: T; label: string }>; value: T; onChange: (value: T) => void; className?: string }) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  function move(event: KeyboardEvent, index: number) {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = (index + step + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  }
  return (
    <div role="radiogroup" aria-label={label} className={cx("inline-flex max-w-full gap-0.5 overflow-x-auto rounded-[9px] bg-surface-sunken p-[3px]", className)}>
      {options.map((option, index) => {
        const checked = option.value === value;
        return (
          <button
            key={option.value}
            ref={(node) => { refs.current[index] = node; }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => move(event, index)}
            className={cx("h-8 cursor-pointer rounded-[7px] border-0 whitespace-nowrap px-2.5 text-[13px] pointer-coarse:h-11", checked ? "bg-surface font-semibold text-ink shadow-[var(--shadow-card)]" : "bg-transparent font-medium text-ink-muted hover:text-ink")}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
