import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, MouseEvent } from "react";

export type SearchableSelectOption = { value: string; label: string };

type SearchableSelectProps = {
  id: string;
  options: SearchableSelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  searchLabel: string;
  searchPlaceholder?: string;
  noMatchesText?: string;
  disabled?: boolean;
};

type IndexedOption = SearchableSelectOption & { index: number };

function matchingOptions(options: SearchableSelectOption[], query: string): IndexedOption[] {
  const normalizedQuery = query.trim().toLowerCase();
  return options
    .map((option, index) => ({ ...option, index }))
    .filter((option) => option.label.toLowerCase().includes(normalizedQuery));
}

/**
 * A single-value dropdown whose options can be filtered by typing.
 *
 * A `<label htmlFor={id}>` names the trigger and the option list.
 *
 * The open panel floats over the content below the trigger. A scrollable
 * ancestor's scroll area grows to include it, and opening scrolls it into
 * view, so the ancestor does not clip it.
 */
export default function SearchableSelect(props: SearchableSelectProps) {
  const {
    id,
    options,
    value,
    onChange,
    placeholder,
    searchLabel,
    searchPlaceholder = "Search…",
    noMatchesText = "No matches",
    disabled = false
  } = props;
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightedValue, setHighlightedValue] = useState<string | null>(null);

  if (disabled && open) {
    // A control that becomes disabled while open closes, and stays closed when enabled again.
    setOpen(false);
    setQuery("");
    setHighlightedValue(null);
  }

  const isOpen = open && !disabled;
  const selectedOption = options.find((option) => option.value === value) ?? null;
  const visibleOptions = isOpen ? matchingOptions(options, query) : [];
  const highlightedPosition = visibleOptions.findIndex(
    (option) => option.value === highlightedValue
  );
  const highlightedOption = visibleOptions[highlightedPosition] ?? null;
  const valueId = `${id}-value`;
  const listboxId = `${id}-listbox`;
  const optionId = (index: number) => `${id}-option-${index}`;
  const highlightedOptionId = highlightedOption ? optionId(highlightedOption.index) : undefined;

  function openPanel() {
    if (disabled) return;
    setQuery("");
    setHighlightedValue(selectedOption?.value ?? null);
    setOpen(true);
  }

  function closePanel(restoreFocus: boolean) {
    setOpen(false);
    setQuery("");
    setHighlightedValue(null);
    if (restoreFocus) triggerRef.current?.focus();
  }

  function selectOption(nextValue: string) {
    closePanel(true);
    if (nextValue !== value) onChange(nextValue);
  }

  function changeQuery(nextQuery: string) {
    setQuery(nextQuery);
    setHighlightedValue(matchingOptions(options, nextQuery)[0]?.value ?? null);
  }

  function clearQuery() {
    setQuery("");
    setHighlightedValue(selectedOption?.value ?? null);
    searchRef.current?.focus();
  }

  function moveHighlight(step: 1 | -1) {
    if (visibleOptions.length === 0) return;
    const lastPosition = visibleOptions.length - 1;
    const nextPosition =
      highlightedPosition < 0
        ? step === 1
          ? 0
          : lastPosition
        : Math.min(Math.max(highlightedPosition + step, 0), lastPosition);
    setHighlightedValue(visibleOptions[nextPosition].value);
  }

  function keepSearchFocus(event: MouseEvent<HTMLDivElement>) {
    // A click anywhere in the panel but the search field, including its empty
    // areas, keeps focus and the keyboard handling in the search field.
    if (event.target !== searchRef.current) event.preventDefault();
  }

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    // Enter and Space reach onClick through the native button.
    if (event.key !== "ArrowDown" || isOpen) return;
    event.preventDefault();
    openPanel();
  }

  function onSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        moveHighlight(1);
        break;
      case "ArrowUp":
        event.preventDefault();
        moveHighlight(-1);
        break;
      case "Enter":
        // Never submits the surrounding form.
        event.preventDefault();
        if (highlightedOption) selectOption(highlightedOption.value);
        break;
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        closePanel(true);
        break;
      case "Tab":
        closePanel(false);
        break;
    }
  }

  useEffect(() => {
    if (!isOpen) return;
    searchRef.current?.focus();
    // jsdom does not implement scrollIntoView.
    panelRef.current?.scrollIntoView?.({ block: "nearest" });

    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) {
        setOpen(false);
        setQuery("");
        setHighlightedValue(null);
      }
    }

    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [isOpen]);

  useEffect(() => {
    if (!highlightedOptionId) return;
    document.getElementById(highlightedOptionId)?.scrollIntoView?.({ block: "nearest" });
  }, [highlightedOptionId]);

  return (
    <div ref={rootRef} className="searchable-select">
      <button
        ref={triggerRef}
        id={id}
        type="button"
        className="select searchable-select__trigger"
        // The label names the trigger; the shown value is its description.
        aria-describedby={valueId}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        disabled={disabled}
        onClick={() => (isOpen ? closePanel(false) : openPanel())}
        onKeyDown={onTriggerKeyDown}
      >
        <span
          id={valueId}
          className={
            selectedOption
              ? "searchable-select__value"
              : "searchable-select__value searchable-select__value--placeholder"
          }
        >
          {selectedOption ? selectedOption.label : placeholder}
        </span>
      </button>
      {isOpen ? (
        <div ref={panelRef} className="searchable-select__panel" onMouseDown={keepSearchFocus}>
          <div className="searchable-select__search">
            <input
              ref={searchRef}
              type="text"
              className="input searchable-select__search-input"
              role="combobox"
              aria-label={searchLabel}
              aria-expanded="true"
              aria-controls={listboxId}
              aria-autocomplete="list"
              aria-activedescendant={highlightedOptionId}
              autoComplete="off"
              spellCheck={false}
              placeholder={searchPlaceholder}
              value={query}
              onChange={(event) => changeQuery(event.target.value)}
              onKeyDown={onSearchKeyDown}
            />
            {query ? (
              <button
                type="button"
                className="searchable-select__clear"
                aria-label="Clear search"
                tabIndex={-1}
                onClick={clearQuery}
              >
                <span aria-hidden="true">×</span>
              </button>
            ) : null}
          </div>
          <div className="searchable-select__list">
            <ul id={listboxId} role="listbox" aria-labelledby={id}>
              {visibleOptions.map((option) => (
                <li
                  key={option.index}
                  id={optionId(option.index)}
                  role="option"
                  aria-selected={option.value === value}
                  className={
                    option.index === highlightedOption?.index
                      ? "searchable-select__option searchable-select__option--highlighted"
                      : "searchable-select__option"
                  }
                  onClick={() => selectOption(option.value)}
                >
                  {option.label}
                </li>
              ))}
            </ul>
            {visibleOptions.length === 0 ? (
              <p className="searchable-select__empty">{noMatchesText}</p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
