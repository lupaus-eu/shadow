import { ChevronDown, ChevronRight, Plus, Search } from "lucide-react";
import type { KeyboardEvent, Ref } from "react";

import { Button, IconButton, cx } from "../../ui";
import type { GraphMarkers } from "./graph-types";
import { shortenName } from "./diagram/shapes";
import { isGroupOpen, type TypeGroup } from "./type-list";

export type TypePanelTexts = {
  searchNodes: string;
  searchPlaceholder: string;
  searchNoMatch: string;
  selectAll: string;
  deselectAll: string;
  typeFilter: string;
  noNodes: string;
  typeEmpty: string;
  changeAdded: string;
  changeUpdated: string;
  showType(name: string): string;
  collapseType(name: string): string;
  expandType(name: string): string;
  addNodeOfType(name: string): string;
};

type Props = {
  groups: TypeGroup[];
  /** Types whose nodes are hidden on the canvas. */
  hidden: ReadonlySet<string>;
  /** The person's collapse choices; a type they never toggled follows the default (collapsed without nodes). */
  collapse: Readonly<Record<string, boolean>>;
  query: string;
  /** Ids of the nodes that match the query, or null when there is no query. */
  matches: ReadonlySet<string> | null;
  selectedId: string | null;
  markers: GraphMarkers;
  /** False on a read-only model: the "+" buttons are not shown. */
  writable: boolean;
  texts: TypePanelTexts;
  searchRef?: Ref<HTMLInputElement>;
  onQuery(query: string): void;
  /** Enter in the search box. */
  onSubmitSearch(): void;
  onToggleType(typeId: string): void;
  onSelectAll(): void;
  onDeselectAll(): void;
  onToggleCollapse(typeId: string, collapsed: boolean): void;
  onAdd(typeId: string): void;
  onSelectNode(nodeId: string): void;
};

/** The left panel of the Structure canvas: nodes grouped by type with visibility, collapse, "+" and a name search. */
export function TypePanel({ groups, hidden, collapse, query, matches, selectedId, markers, writable, texts, searchRef, onQuery, onSubmitSearch, onToggleType, onSelectAll, onDeselectAll, onToggleCollapse, onAdd, onSelectNode }: Props) {
  const added = new Set(markers.added);
  const updated = new Set(markers.updated);
  const onSearchKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") { event.preventDefault(); onSubmitSearch(); }
    else if (event.key === "Escape" && query) { event.preventDefault(); onQuery(""); }
  };
  const matchCount = matches ? groups.reduce((sum, group) => sum + group.nodes.filter((node) => matches.has(node.id)).length, 0) : 0;
  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="relative">
        <Search aria-hidden="true" size={14} className="pointer-events-none absolute top-1/2 left-2 -translate-y-1/2 text-ink-muted" />
        <input
          ref={searchRef}
          type="search"
          aria-label={texts.searchNodes}
          placeholder={texts.searchPlaceholder}
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          onKeyDown={onSearchKey}
          className="h-[34px] w-full rounded-[var(--radius-control)] border border-line bg-surface pr-2 pl-7 text-[13px] text-ink pointer-coarse:min-h-11"
        />
      </div>
      {matches && matchCount === 0 ? <p role="status" className="m-0 text-xs text-ink-muted">{texts.searchNoMatch}</p> : null}
      <div role="group" aria-label={texts.typeFilter} className="flex gap-2">
        <Button size="sm" variant="ghost" onClick={onSelectAll} disabled={hidden.size === 0}>{texts.selectAll}</Button>
        <Button size="sm" variant="ghost" onClick={onDeselectAll} disabled={groups.every((group) => hidden.has(group.type.id))}>{texts.deselectAll}</Button>
      </div>
      {groups.length === 0 ? <p className="m-0 text-[13px] text-ink-muted">{texts.noNodes}</p> : null}
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {groups.map((group) => {
          const { type } = group;
          const isHidden = hidden.has(type.id);
          const open = isGroupOpen(group, collapse, matches);
          const listId = `type-nodes-${type.id}`;
          return (
            <li key={type.id} className="flex flex-col">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  aria-expanded={open}
                  aria-controls={listId}
                  aria-label={open ? texts.collapseType(type.name) : texts.expandType(type.name)}
                  title={open ? texts.collapseType(type.name) : texts.expandType(type.name)}
                  onClick={() => onToggleCollapse(type.id, open)}
                  className="inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-[6px] border-0 bg-transparent text-ink hover:bg-surface-sunken pointer-coarse:size-11"
                >
                  {open ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
                </button>
                <label className="flex min-h-8 min-w-0 flex-1 cursor-pointer items-center gap-2 text-[13px] font-medium text-ink pointer-coarse:min-h-11">
                  <input type="checkbox" className="size-4 shrink-0 accent-[var(--color-accent)]" checked={!isHidden} aria-label={texts.showType(type.name)} onChange={() => onToggleType(type.id)} />
                  <span aria-hidden="true" data-testid="type-colour" className="size-3 shrink-0 rounded-[3px] border border-line" style={{ background: type.color }} />
                  <span className="min-w-0 flex-1 truncate">{type.name}</span>
                  <span className="shrink-0 text-xs font-normal text-ink-muted">({group.nodes.length})</span>
                </label>
                {writable ? <IconButton size="sm" variant="ghost" label={texts.addNodeOfType(type.name)} icon={<Plus size={14} />} onClick={() => onAdd(type.id)} className="h-7 w-7" /> : null}
              </div>
              <ul id={listId} hidden={!open} className={cx("m-0 list-none flex-col gap-0.5 p-0 pl-8", open ? "flex" : "hidden")}>
                {group.nodes.length === 0 ? <li className="py-1 text-xs text-ink-muted">{texts.typeEmpty}</li> : null}
                {group.nodes.map((node) => {
                  const change = added.has(node.id) ? "added" : updated.has(node.id) ? "updated" : null;
                  const dimmed = matches !== null && !matches.has(node.id);
                  return (
                    <li key={node.id}>
                      <button
                        type="button"
                        disabled={isHidden}
                        aria-pressed={selectedId === node.id}
                        onClick={() => onSelectNode(node.id)}
                        className={cx(
                          "flex min-h-8 w-full cursor-pointer flex-col items-start gap-0.5 rounded-[6px] border-0 bg-transparent px-2 py-1 text-left text-[13px] text-ink hover:bg-surface-sunken aria-pressed:bg-accent-soft pointer-coarse:min-h-11",
                          "disabled:cursor-not-allowed disabled:text-ink-muted disabled:hover:bg-transparent",
                          dimmed && "opacity-50",
                          matches && !dimmed && "font-semibold",
                        )}
                      >
                        <span className="flex w-full items-center gap-1">
                          <span className="min-w-0 flex-1 truncate" title={node.name}>{shortenName(node.name)}</span>
                          {change ? <span data-change={change} className="shrink-0 rounded-[4px] border border-line px-1 text-[11px] leading-4 text-ink" title={change === "added" ? texts.changeAdded : texts.changeUpdated}><span aria-hidden="true">{change === "added" ? "+" : "~"}</span><span className="sr-only">{change === "added" ? texts.changeAdded : texts.changeUpdated}</span></span> : null}
                        </span>
                        {node.description ? <span className="line-clamp-2 w-full text-xs font-normal text-ink-muted">{node.description}</span> : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
