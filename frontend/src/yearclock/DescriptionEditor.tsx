import { Bold, Eye, Italic, Link as LinkIcon, List } from "lucide-react";
import { useId, useRef, useState } from "react";

import type { PlannerMessages } from "../i18n";
import { Choice, IconButton, TextArea } from "../ui";
import { applyFormat, type FormatKind } from "./description-format";
import { RichText } from "./RichText";

export type DescriptionFormat = "plain" | "markdown";

/** The description with an optional formatting toolbar and a preview; plain text stays as typed. */
export function DescriptionEditor({ value, format, limit, onChange, onFormatChange, copy }: { value: string; format: DescriptionFormat; limit: number; onChange: (value: string) => void; onFormatChange: (format: DescriptionFormat) => void; copy: PlannerMessages }) {
  const area = useRef<HTMLTextAreaElement>(null);
  const [preview, setPreview] = useState(false);
  const helpId = useId();
  const formatted = format === "markdown";

  function apply(kind: FormatKind) {
    const element = area.current;
    if (!element) return;
    const edit = applyFormat(value, element.selectionStart, element.selectionEnd, kind);
    onChange(edit.value);
    // The browser resets the selection when the controlled value changes, so set it after React has rendered.
    requestAnimationFrame(() => { element.focus(); element.setSelectionRange(edit.start, edit.end); });
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label className="flex flex-col gap-1.5 text-[13px] font-medium text-ink">
        {copy.description}
        <TextArea ref={area} maxLength={limit} value={value} aria-describedby={formatted ? helpId : undefined} onChange={(event) => onChange(event.target.value)} />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <Choice type="checkbox" checked={formatted} onChange={(event) => { onFormatChange(event.target.checked ? "markdown" : "plain"); setPreview(false); }} label={copy.useFormatting} />
        {formatted ? (
          <div role="toolbar" aria-label={copy.formatting} className="ml-auto flex gap-1">
            <IconButton size="sm" variant="ghost" label={copy.bold} icon={<Bold size={14} aria-hidden="true" />} onClick={() => apply("bold")} />
            <IconButton size="sm" variant="ghost" label={copy.italic} icon={<Italic size={14} aria-hidden="true" />} onClick={() => apply("italic")} />
            <IconButton size="sm" variant="ghost" label={copy.bulletList} icon={<List size={14} aria-hidden="true" />} onClick={() => apply("list")} />
            <IconButton size="sm" variant="ghost" label={copy.insertLink} icon={<LinkIcon size={14} aria-hidden="true" />} onClick={() => apply("link")} />
            <IconButton size="sm" variant={preview ? "secondary" : "ghost"} label={copy.preview} aria-pressed={preview} icon={<Eye size={14} aria-hidden="true" />} onClick={() => setPreview(!preview)} />
          </div>
        ) : null}
      </div>
      {formatted ? <p id={helpId} className="m-0 text-xs text-ink-muted">{copy.formatHelp}</p> : null}
      {formatted && preview ? <div role="region" aria-label={copy.preview} className="rounded-[var(--radius-control)] border border-line bg-surface-subtle p-3">{value.trim() ? <RichText text={value} /> : <span className="text-xs text-ink-muted">{copy.previewEmpty}</span>}</div> : null}
    </div>
  );
}
