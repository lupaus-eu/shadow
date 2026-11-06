import { Link } from "react-router";

import { storedLocale, type Locale } from "../i18n";
import { legalMessages } from "./messages";

/** The link to the public legal pages; on pages without a signed-in person it uses the remembered language. */
export function LegalFooterLink({ locale, className = "" }: { locale?: Locale; className?: string }) {
  return <Link to="/legal" className={`text-[12px] text-ink-muted underline ${className}`}>{legalMessages(locale ?? storedLocale()).footerLink}</Link>;
}
