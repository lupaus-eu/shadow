import { useEffect, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link, Route, Routes, useParams } from "react-router";

import { rememberLocale, storedLocale, type Locale } from "../i18n";
import { Logo } from "../shell/Logo";
import { MadeBy } from "../shell/LupausMark";
import { Alert, Badge, SegmentedControl } from "../ui";
import {
  LegalDocumentNotFoundError,
  loadLegalDocument,
  loadLegalDocuments,
  type LegalDocument,
  type LegalDocumentSummary,
} from "./client";
import { legalMessages } from "./messages";

/** Public legal pages: no sign-in, so they carry their own frame and language switch. */
export function LegalRoutes() {
  const [locale, setLocale] = useState<Locale>(storedLocale);
  function change(next: Locale) {
    rememberLocale(next);
    setLocale(next);
  }
  return (
    <LegalFrame locale={locale} onLocaleChange={change}>
      <Routes>
        <Route index element={<LegalIndex locale={locale} />} />
        <Route path=":key" element={<LegalText locale={locale} />} />
      </Routes>
    </LegalFrame>
  );
}

function LegalFrame({ locale, onLocaleChange, children }: { locale: Locale; onLocaleChange: (locale: Locale) => void; children: ReactNode }) {
  const text = legalMessages(locale);
  return (
    <div className="ui-root min-h-screen bg-canvas px-4 py-8">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <a href="/" aria-label="Shadow"><Logo /></a>
          <SegmentedControl
            label={text.language}
            value={locale}
            onChange={(value) => onLocaleChange(value as Locale)}
            options={(["en", "fi"] as const).map((value) => ({ value, label: text.languageNames[value] }))}
          />
        </header>
        <main id="main-content" className="flex flex-col gap-4 rounded-[var(--radius-card)] border border-line bg-surface p-6 shadow-[var(--shadow-card)] sm:p-8">
          {children}
        </main>
        <footer className="flex justify-center text-ink-muted"><MadeBy /></footer>
      </div>
    </div>
  );
}

function useDocuments<T>(load: (signal: AbortSignal) => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ status: "loading" } | { status: "ready"; value: T } | { status: "missing" } | { status: "failed" }>({ status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    load(controller.signal).then(
      (value) => setState({ status: "ready", value }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setState(error instanceof LegalDocumentNotFoundError ? { status: "missing" } : { status: "failed" });
      },
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

function LegalIndex({ locale }: { locale: Locale }) {
  const text = legalMessages(locale);
  const state = useDocuments((signal) => loadLegalDocuments(locale, signal), [locale]);
  useEffect(() => { document.title = `${text.indexTitle} · Shadow`; }, [text.indexTitle]);
  return (
    <>
      <h1 className="text-xl font-semibold">{text.indexTitle}</h1>
      <p className="text-[14px] text-ink-muted">{text.indexIntro}</p>
      {state.status === "loading" ? <p role="status" className="text-[13px] text-ink-muted">{text.loading}</p> : null}
      {state.status === "failed" || state.status === "missing" ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      {state.status === "ready" && state.value.length === 0 ? <p className="text-[14px]">{text.indexEmpty}</p> : null}
      {state.status === "ready" && state.value.length > 0 ? (
        <ul className="m-0 flex list-none flex-col divide-y divide-line p-0">
          {state.value.map((item) => <IndexRow key={item.key} item={item} locale={locale} />)}
        </ul>
      ) : null}
    </>
  );
}

function IndexRow({ item, locale }: { item: LegalDocumentSummary; locale: Locale }) {
  const text = legalMessages(locale);
  return (
    <li className="flex flex-col gap-1 py-3">
      <span className="flex flex-wrap items-center gap-2">
        <Link className="text-[15px] font-semibold text-accent" to={`/legal/${item.key}`}>{item.title}</Link>
        {item.status === "draft" ? <Badge tone="warning">{locale === "fi" ? "Luonnos" : "Draft"}</Badge> : null}
      </span>
      <span className="text-[13px] text-ink-muted">{text.version(item.version, item.effective_from)} · {text.acceptance[item.acceptance]}</span>
    </li>
  );
}

function LegalText({ locale }: { locale: Locale }) {
  const { key = "" } = useParams();
  const text = legalMessages(locale);
  const state = useDocuments((signal) => loadLegalDocument(key, locale, signal), [key, locale]);
  const title = state.status === "ready" ? state.value.title : text.indexTitle;
  useEffect(() => { document.title = `${title} · Shadow`; }, [title]);
  return (
    <>
      <Link className="text-[13px] text-accent" to="/legal">{text.back}</Link>
      {state.status === "loading" ? <p role="status" className="text-[13px] text-ink-muted">{text.loading}</p> : null}
      {state.status === "missing" ? <><h1 className="text-xl font-semibold">{text.notFound}</h1></> : null}
      {state.status === "failed" ? <Alert tone="danger" role="alert">{text.failed}</Alert> : null}
      {state.status === "ready" ? <Document document={state.value} locale={locale} /> : null}
    </>
  );
}

function Document({ document, locale }: { document: LegalDocument; locale: Locale }) {
  const text = legalMessages(locale);
  return (
    <article className="flex flex-col gap-3">
      {document.status === "draft" ? <Alert tone="warning" role="status">{text.draftBanner}</Alert> : null}
      <h1 className="text-xl font-semibold">{document.title}</h1>
      <p className="text-[13px] text-ink-muted">{text.version(document.version, document.effective_from)}</p>
      <div className="legal-text flex flex-col gap-3 text-[14px] leading-relaxed">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{document.body}</ReactMarkdown>
      </div>
    </article>
  );
}

// Raw HTML is not rendered (react-markdown's default); these only style the allowed elements.
const components = {
  h1: (props: object) => <h2 className="mt-4 text-lg font-semibold" {...props} />,
  h2: (props: object) => <h2 className="mt-4 text-lg font-semibold" {...props} />,
  h3: (props: object) => <h3 className="mt-3 text-[15px] font-semibold" {...props} />,
  ul: (props: object) => <ul className="m-0 list-disc pl-5" {...props} />,
  ol: (props: object) => <ol className="m-0 list-decimal pl-5" {...props} />,
  a: (props: object) => <a className="text-accent underline" rel="noopener noreferrer" {...props} />,
  table: (props: object) => <div className="overflow-x-auto"><table className="w-full border-collapse text-left text-[13px]" {...props} /></div>,
  th: (props: object) => <th className="border-b border-line px-2 py-1.5 font-semibold" {...props} />,
  td: (props: object) => <td className="border-b border-line px-2 py-1.5 align-top" {...props} />,
};
