import { useEffect, useId, useState } from "react";

import { workspaceMessages, type Locale } from "../i18n";
import {
  createLabel,
  createOrganizationCategory,
  deleteLabel,
  deleteOrganizationCategory,
  LABEL_COLORS,
  LimitReachedError,
  loadLabels,
  loadOrganizationCategories,
  mergeLabel,
  reorderOrganizationCategories,
  updateLabel,
  updateOrganizationCategory,
  type Label,
  type YearclockCategory,
} from "../organization-client";
import { Alert, Button, Field, Select, TextInput, useConfirm } from "../ui";
import { INLINE_FORM, MUTED, ROW, ROWS, Section } from "./Section";

type ClassificationText = ReturnType<typeof workspaceMessages>["classification"];

const SWATCH = "inline-block size-3.5 shrink-0 rounded-[4px] border border-line";
const EDIT = "flex w-full flex-wrap items-end gap-2";

/** Organization Categories and Labels, shared by every Yearclock. */
export function Classification({ organizationId, locale, writable }: { organizationId: string; locale: Locale; writable: boolean }) {
  const text = workspaceMessages(locale).classification;
  return (
    <div className="classification flex flex-col gap-5">
      <p className="m-0 rounded-[10px] border border-warning-line bg-warning-soft px-4 py-3 text-[13px] text-warning-ink" role="note">{text.visibility}</p>
      {!writable ? <Alert tone="info" role="status">{text.readOnly}</Alert> : null}
      <OrganizationCategories organizationId={organizationId} text={text} writable={writable} />
      <Labels organizationId={organizationId} text={text} writable={writable} />
    </div>
  );
}

function Labels({ organizationId, text, writable }: { organizationId: string; text: ClassificationText; writable: boolean }) {
  const confirm = useConfirm();
  const [labels, setLabels] = useState<Label[]>([]);
  const [name, setName] = useState("");
  const [color, setColor] = useState<string>(LABEL_COLORS[0]);
  const [notice, setNotice] = useState<string | null>(null);
  const refresh = () => loadLabels(organizationId).then(setLabels).catch(() => setNotice(text.failed));
  useEffect(() => { void refresh(); }, [organizationId]);
  async function act(action: () => Promise<unknown>) {
    setNotice(null);
    try { await action(); } catch (error) { setNotice(error instanceof LimitReachedError ? text.limit(error.maximum) : text.failed); }
    await refresh();
  }
  const colorName = (value: string) => text.colors[LABEL_COLORS.indexOf(value as (typeof LABEL_COLORS)[number])] ?? value;
  return (
    <Section title={text.labels} description={text.description}>
      {notice ? <Alert tone="danger" role="alert">{notice}</Alert> : null}
      {labels.length === 0 ? <p className={MUTED}>{text.empty}</p> : (
        <ul className={`label-list ${ROWS}`}>
          {labels.map((label) => <LabelRow key={`${label.id}-${label.version}`} label={label} others={labels.filter((item) => item.id !== label.id)} text={text} colorName={colorName} writable={writable} onSave={(nextName, nextColor) => act(() => updateLabel(organizationId, label, nextName, nextColor))} onMerge={(into) => { void confirm({ title: text.confirmMerge(label.name, into.name, label.usage), confirmLabel: text.merge }).then((ok) => { if (ok) void act(() => mergeLabel(organizationId, label, into)); }); }} onDelete={() => { void confirm({ title: text.confirmDelete(label.name, label.usage), confirmLabel: text.delete, destructive: true }).then((ok) => { if (ok) void act(() => deleteLabel(organizationId, label)); }); }} />)}
        </ul>
      )}
      {writable ? (
        <form className={INLINE_FORM} onSubmit={(event) => { event.preventDefault(); if (name.trim()) void act(() => createLabel(organizationId, name.trim(), color)).then(() => setName("")); }}>
          <Field label={text.name} className="min-w-56 flex-1">{(control) => <TextInput {...control} value={name} maxLength={60} onChange={(event) => setName(event.target.value)} />}</Field>
          <ColorSelect value={color} onChange={setColor} text={text} colorName={colorName} />
          <Button type="submit" variant="primary" disabled={!name.trim()}>{text.create}</Button>
        </form>
      ) : null}
    </Section>
  );
}

function OrganizationCategories({ organizationId, text, writable }: { organizationId: string; text: ClassificationText; writable: boolean }) {
  const confirm = useConfirm();
  const [categories, setCategories] = useState<YearclockCategory[]>([]);
  const [name, setName] = useState("");
  const [color, setColor] = useState("#1f5f99");
  const [notice, setNotice] = useState<string | null>(null);
  const colorId = useId();
  const refresh = () => loadOrganizationCategories(organizationId).then(setCategories).catch(() => setNotice(text.failed));
  useEffect(() => { void refresh(); }, [organizationId]);
  async function act(action: () => Promise<unknown>) {
    setNotice(null);
    try { await action(); } catch (error) { setNotice(error instanceof LimitReachedError ? text.categoryLimit(error.maximum) : text.failed); }
    await refresh();
  }
  function move(index: number, delta: number) {
    const ids = categories.map((category) => category.id);
    [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    void act(() => reorderOrganizationCategories(organizationId, categories, ids));
  }
  return (
    <Section title={text.categories} description={text.categoriesDescription}>
      {notice ? <Alert tone="danger" role="alert">{notice}</Alert> : null}
      {categories.length === 0 ? <p className={MUTED}>{text.categoriesEmpty}</p> : (
        <ul className={`label-list ${ROWS}`} aria-label={text.categories}>
          {categories.map((category, index) => (
            <li key={`${category.id}-${category.version}`} className={ROW}>
              <span className={SWATCH} style={{ background: category.color ?? "#4a5a67" }} aria-hidden="true" /> <strong className="font-semibold">{category.name}</strong> <span className={MUTED}>{text.usage(category.usage ?? 0)}</span>
              {writable ? <OrganizationCategoryEditor category={category} text={text} onSave={(nextName, nextColor) => act(() => updateOrganizationCategory(organizationId, category, nextName, nextColor))} onDelete={() => { void confirm({ title: text.confirmCategoryDelete(category.name, category.usage ?? 0), confirmLabel: text.delete, destructive: true }).then((ok) => { if (ok) void act(() => deleteOrganizationCategory(organizationId, category)); }); }} onUp={index > 0 ? () => move(index, -1) : undefined} onDown={index < categories.length - 1 ? () => move(index, 1) : undefined} /> : null}
            </li>
          ))}
        </ul>
      )}
      {writable ? (
        <form className={INLINE_FORM} onSubmit={(event) => { event.preventDefault(); if (name.trim()) void act(() => createOrganizationCategory(organizationId, name.trim(), color)).then(() => setName("")); }}>
          <Field label={`${text.categories}: ${text.name}`} className="min-w-56 flex-1">{(control) => <TextInput {...control} value={name} maxLength={120} onChange={(event) => setName(event.target.value)} />}</Field>
          <div className="flex flex-col gap-1.5"><label htmlFor={colorId} className="text-[13px] font-medium">{`${text.categories}: ${text.color}`}</label><input id={colorId} type="color" className="h-9 w-14 cursor-pointer rounded-[var(--radius-control)] border border-line-strong bg-surface p-1" value={color} onChange={(event) => setColor(event.target.value)} /></div>
          <Button type="submit" variant="primary" disabled={!name.trim()}>{text.addCategory}</Button>
        </form>
      ) : null}
    </Section>
  );
}

function OrganizationCategoryEditor({ category, text, onSave, onDelete, onUp, onDown }: { category: YearclockCategory; text: ClassificationText; onSave: (name: string, color: string) => void; onDelete: () => void; onUp?: () => void; onDown?: () => void }) {
  const [name, setName] = useState(category.name);
  const [color, setColor] = useState(category.color ?? "#4a5a67");
  const colorId = useId();
  return (
    <div className={EDIT}>
      <Field label={`${text.name}: ${category.name}`} hideLabel className="min-w-48 flex-1">{(control) => <TextInput {...control} value={name} maxLength={120} onChange={(event) => setName(event.target.value)} />}</Field>
      <label htmlFor={colorId} className="sr-only">{`${text.color}: ${category.name}`}</label><input id={colorId} type="color" className="h-9 w-12 cursor-pointer rounded-[var(--radius-control)] border border-line-strong bg-surface p-1" value={color} onChange={(event) => setColor(event.target.value)} />
      <Button size="sm" disabled={!name.trim() || (name.trim() === category.name && color === category.color)} onClick={() => onSave(name.trim(), color)} aria-label={`${text.save}: ${category.name}`}>{text.save}</Button>
      {onUp ? <Button size="sm" variant="ghost" onClick={onUp} aria-label={`${text.up}: ${category.name}`}>{text.up}</Button> : null}
      {onDown ? <Button size="sm" variant="ghost" onClick={onDown} aria-label={`${text.down}: ${category.name}`}>{text.down}</Button> : null}
      <Button size="sm" variant="ghost-danger" onClick={onDelete} aria-label={`${text.delete}: ${category.name}`}>{text.delete}</Button>
    </div>
  );
}

function ColorSelect({ value, onChange, text, colorName, label, hideLabel = false }: { value: string; onChange: (value: string) => void; text: ClassificationText; colorName: (value: string) => string; label?: string; hideLabel?: boolean }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className={hideLabel ? "sr-only" : "text-[13px] font-medium"}>{label ?? text.color}</label>
      <span className="flex items-center gap-2"><span className={SWATCH} style={{ background: value }} aria-hidden="true" /><Select id={id} className="w-36" value={value} onChange={(event) => onChange(event.target.value)}>{LABEL_COLORS.map((option) => <option key={option} value={option}>{colorName(option)}</option>)}</Select></span>
    </div>
  );
}

function LabelRow({ label, others, text, colorName, writable, onSave, onMerge, onDelete }: { label: Label; others: Label[]; text: ClassificationText; colorName: (value: string) => string; writable: boolean; onSave: (name: string, color: string) => void; onMerge: (into: Label) => void; onDelete: () => void }) {
  const [name, setName] = useState(label.name);
  const [color, setColor] = useState(label.color);
  const [into, setInto] = useState(others[0]?.id ?? "");
  const mergeId = useId();
  const target = others.find((item) => item.id === into) ?? others[0];
  return (
    <li className={ROW}>
      <span className={SWATCH} style={{ background: label.color }} aria-hidden="true" /> <strong className="font-semibold">{label.name}</strong> <span className={MUTED}>{text.usage(label.usage)}</span>
      {writable ? (
        <div className={EDIT}>
          <Field label={`${text.name}: ${label.name}`} hideLabel className="min-w-40 flex-1">{(control) => <TextInput {...control} value={name} maxLength={60} onChange={(event) => setName(event.target.value)} />}</Field>
          <ColorSelect value={color} onChange={setColor} text={text} colorName={colorName} label={`${text.color}: ${label.name}`} hideLabel />
          <Button size="sm" disabled={!name.trim() || (name.trim() === label.name && color === label.color)} onClick={() => onSave(name.trim(), color)} aria-label={`${text.save}: ${label.name}`}>{text.save}</Button>
          {others.length > 0 ? <>
            <label htmlFor={mergeId} className="sr-only">{`${text.mergeInto}: ${label.name}`}</label>
            <Select id={mergeId} className="w-36" value={target?.id ?? ""} onChange={(event) => setInto(event.target.value)}>{others.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select>
            <Button size="sm" disabled={!target} onClick={() => target && onMerge(target)} aria-label={`${text.merge}: ${label.name}`}>{text.merge}</Button>
          </> : null}
          <Button size="sm" variant="ghost-danger" onClick={onDelete} aria-label={`${text.delete}: ${label.name}`}>{text.delete}</Button>
        </div>
      ) : null}
    </li>
  );
}
