import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import type { PlannerMessages } from "../i18n";
import { Button, IconButton, TextInput } from "../ui";
import { LINKS_MAX, LINK_TITLE_MAX, LINK_URL_MAX, moveLink, type EventLink } from "./event-links";

/** Up to ten titled links: add, edit, reorder, and remove. */
export function LinksEditor({ links, onChange, copy }: { links: EventLink[]; onChange: (links: EventLink[]) => void; copy: PlannerMessages }) {
  const change = (index: number, patch: Partial<EventLink>) => onChange(links.map((link, position) => (position === index ? { ...link, ...patch } : link)));
  return (
    <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
      <legend className="mb-1 p-0 text-[13px] font-medium text-ink">{copy.links}</legend>
      {links.map((link, index) => (
        <div key={index} role="group" aria-label={copy.linkRow(index + 1)} className="flex flex-wrap items-end gap-2">
          <label className="flex min-w-32 flex-1 flex-col gap-1 text-xs font-medium text-ink">{copy.linkTitle}<TextInput maxLength={LINK_TITLE_MAX} value={link.title} onChange={(event) => change(index, { title: event.target.value })} /></label>
          <label className="flex min-w-48 flex-[2] flex-col gap-1 text-xs font-medium text-ink">{copy.linkAddress}<TextInput type="url" maxLength={LINK_URL_MAX} placeholder="https://" value={link.url} onChange={(event) => change(index, { url: event.target.value })} /></label>
          <div className="flex gap-1">
            <IconButton size="sm" variant="ghost" label={copy.moveLinkUp(index + 1)} disabled={index === 0} onClick={() => onChange(moveLink(links, index, -1))} icon={<ArrowUp size={14} aria-hidden="true" />} />
            <IconButton size="sm" variant="ghost" label={copy.moveLinkDown(index + 1)} disabled={index === links.length - 1} onClick={() => onChange(moveLink(links, index, 1))} icon={<ArrowDown size={14} aria-hidden="true" />} />
            <IconButton size="sm" variant="ghost-danger" label={copy.removeLink(index + 1)} onClick={() => onChange(links.filter((_, position) => position !== index))} icon={<Trash2 size={14} aria-hidden="true" />} />
          </div>
        </div>
      ))}
      <div><Button size="sm" disabled={links.length >= LINKS_MAX} onClick={() => onChange([...links, { title: "", url: "" }])} icon={<Plus size={14} aria-hidden="true" />}>{copy.addLink}</Button></div>
    </fieldset>
  );
}
