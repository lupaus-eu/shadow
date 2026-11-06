import { Clock3 } from "lucide-react";

/** The Yearclock mark and wordmark; the mark follows the accent colour. */
export function Logo({ tone = "dark" }: { tone?: "dark" | "light" }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <span aria-hidden="true" className="flex size-7 items-center justify-center rounded-[8px] bg-accent text-white">
        <Clock3 size={16} strokeWidth={2.25} />
      </span>
      <span className={tone === "light" ? "text-[15px] font-bold tracking-tight text-white" : "text-[15px] font-bold tracking-tight text-ink"}>Yearclock</span>
    </span>
  );
}
