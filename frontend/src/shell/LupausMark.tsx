/** The company's wordmark, for the "by Lupaus" line; the dark variant is for dark backgrounds such as the sidebar. */
export function LupausMark({ tone = "light", className = "" }: { tone?: "light" | "dark"; className?: string }) {
  return <img src={tone === "dark" ? "/lupaus-on-dark.svg" : "/lupaus-on-light.svg"} alt="Lupaus" height={11} className={`inline-block h-[11px] w-auto align-baseline ${className}`} />;
}

/** "Yearclock by LUPAUS": the product with its maker, shown small in footers. */
export function MadeBy({ tone = "light", className = "" }: { tone?: "light" | "dark"; className?: string }) {
  return <span className={`inline-flex items-center gap-1.5 text-[12px] ${className}`}>Yearclock <span aria-hidden="true">·</span> <LupausMark tone={tone} /></span>;
}
