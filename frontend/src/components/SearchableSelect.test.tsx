import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import SearchableSelect from "./SearchableSelect";

const options = [
  { value: "node_ceo", label: "CEO" },
  { value: "node_sales", label: "Sales" },
  { value: "node_cfo", label: "CFO" },
  { value: "node_ops", label: "Operations" }
];

function Harness(props: {
  initialValue?: string;
  disabled?: boolean;
  onChange?: (value: string) => void;
}) {
  const [value, setValue] = useState(props.initialValue ?? "");
  return (
    <form onSubmit={(event) => event.preventDefault()}>
      <label htmlFor="source">Source</label>
      <SearchableSelect
        id="source"
        options={options}
        value={value}
        onChange={(nextValue) => {
          props.onChange?.(nextValue);
          setValue(nextValue);
        }}
        placeholder="Select source node"
        searchLabel="Search source nodes"
        disabled={props.disabled}
      />
      <button type="button">Outside</button>
    </form>
  );
}

function trigger() {
  return screen.getByLabelText("Source");
}

function openSelect() {
  fireEvent.click(trigger());
  return screen.getByRole("combobox", { name: "Search source nodes" });
}

function optionLabels() {
  return screen.queryAllByRole("option").map((option) => option.textContent);
}

describe("SearchableSelect", () => {
  it("shows the placeholder, or the selected label, in the labelled trigger", () => {
    const { unmount } = render(<Harness />);

    expect(trigger()).toHaveTextContent("Select source node");
    expect(trigger()).toHaveAttribute("type", "button");
    expect(trigger()).toHaveAttribute("aria-haspopup", "listbox");
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: "Source" })).toBe(trigger());
    expect(trigger()).toHaveAccessibleDescription("Select source node");
    unmount();

    render(<Harness initialValue="node_sales" />);
    expect(trigger()).toHaveTextContent("Sales");
    expect(screen.getByRole("button", { name: "Source" })).toBe(trigger());
    // Screen readers announce the selected option after the label, as for a native select.
    expect(trigger()).toHaveAccessibleDescription("Sales");
  });

  it("shows the placeholder for a value that is not among the options", () => {
    render(<Harness initialValue="node_missing" />);

    expect(trigger()).toHaveTextContent("Select source node");
  });

  it("opens with a focused search field and every option, and closes from the trigger", () => {
    render(<Harness initialValue="node_cfo" />);

    const search = openSelect();
    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    expect(search).toHaveFocus();
    expect(search).toHaveAttribute("placeholder", "Search…");
    expect(search).toHaveAttribute("aria-expanded", "true");
    expect(search).toHaveAttribute("aria-autocomplete", "list");
    const listbox = screen.getByRole("listbox", { name: "Source" });
    expect(search).toHaveAttribute("aria-controls", listbox.id);
    expect(optionLabels()).toEqual(["CEO", "Sales", "CFO", "Operations"]);
    const selected = screen.getByRole("option", { name: "CFO" });
    expect(selected).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("option", { name: "CEO" })).toHaveAttribute("aria-selected", "false");
    expect(search).toHaveAttribute("aria-activedescendant", selected.id);

    fireEvent.click(trigger());
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("opens from the keyboard with ArrowDown", () => {
    render(<Harness />);

    fireEvent.keyDown(trigger(), { key: "ArrowDown" });

    expect(screen.getByRole("combobox", { name: "Search source nodes" })).toHaveFocus();
    expect(screen.getByRole("combobox")).not.toHaveAttribute("aria-activedescendant");
  });

  it("filters by a trimmed, case-insensitive substring and keeps the option order", () => {
    render(<Harness />);
    const search = openSelect();

    fireEvent.change(search, { target: { value: "  c " } });
    expect(optionLabels()).toEqual(["CEO", "CFO"]);
    expect(search).toHaveAttribute(
      "aria-activedescendant",
      screen.getByRole("option", { name: "CEO" }).id
    );

    fireEvent.change(search, { target: { value: "ERAT" } });
    expect(optionLabels()).toEqual(["Operations"]);
    expect(screen.queryByText("No matches")).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: "zzz" } });
    expect(optionLabels()).toEqual([]);
    expect(screen.getByText("No matches")).toBeInTheDocument();
    expect(screen.getByText("No matches")).not.toHaveAttribute("role");
    expect(search).not.toHaveAttribute("aria-activedescendant");

    fireEvent.keyDown(search, { key: "Enter" });
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });

  it("uses the given search placeholder and no-matches text", () => {
    render(
      <SearchableSelect
        id="target"
        options={options}
        value=""
        onChange={vi.fn()}
        placeholder="Select target node"
        searchLabel="Search target nodes"
        searchPlaceholder="Find a node"
        noMatchesText="Nothing found"
      />
    );

    fireEvent.click(screen.getByRole("button"));
    const search = screen.getByRole("combobox", { name: "Search target nodes" });
    expect(search).toHaveAttribute("placeholder", "Find a node");
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(screen.getByText("Nothing found")).toBeInTheDocument();
  });

  it("shows the clear button only for a query, and clearing keeps the selection", () => {
    const onChange = vi.fn();
    render(<Harness initialValue="node_sales" onChange={onChange} />);
    const search = openSelect();

    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();
    fireEvent.change(search, { target: { value: "c" } });
    const clear = screen.getByRole("button", { name: "Clear search" });
    expect(clear).toHaveAttribute("type", "button");

    fireEvent.click(clear);

    expect(search).toHaveValue("");
    expect(search).toHaveFocus();
    expect(optionLabels()).toEqual(["CEO", "Sales", "CFO", "Operations"]);
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();
    expect(trigger()).toHaveTextContent("Sales");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("selects with ArrowDown, ArrowUp and Enter, stopping at the ends", () => {
    const onChange = vi.fn();
    render(<Harness initialValue="node_cfo" onChange={onChange} />);
    const search = openSelect();
    const highlighted = () =>
      document.getElementById(search.getAttribute("aria-activedescendant") ?? "")?.textContent;

    fireEvent.keyDown(search, { key: "ArrowDown" });
    expect(highlighted()).toBe("Operations");
    fireEvent.keyDown(search, { key: "ArrowDown" });
    expect(highlighted()).toBe("Operations");
    for (let step = 0; step < 4; step += 1) fireEvent.keyDown(search, { key: "ArrowUp" });
    expect(highlighted()).toBe("CEO");
    fireEvent.keyDown(search, { key: "ArrowDown" });
    expect(highlighted()).toBe("Sales");

    fireEvent.keyDown(search, { key: "Enter" });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("node_sales");
    expect(trigger()).toHaveTextContent("Sales");
    expect(trigger()).toHaveFocus();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    const reopened = openSelect();
    expect(reopened).toHaveValue("");
    expect(optionLabels()).toHaveLength(4);
  });

  it("selects an option with the mouse", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const search = openSelect();
    fireEvent.change(search, { target: { value: "op" } });

    fireEvent.click(screen.getByRole("option", { name: "Operations" }));

    expect(onChange).toHaveBeenCalledWith("node_ops");
    expect(trigger()).toHaveTextContent("Operations");
    expect(trigger()).toHaveFocus();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("closes without a change on Escape, Tab and an outside click", () => {
    const onChange = vi.fn();
    render(<Harness initialValue="node_ceo" onChange={onChange} />);

    let search = openSelect();
    fireEvent.keyDown(search, { key: "ArrowDown" });
    fireEvent.keyDown(search, { key: "Escape" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();

    search = openSelect();
    fireEvent.keyDown(search, { key: "Tab" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    search = openSelect();
    fireEvent.change(search, { target: { value: "sal" } });
    fireEvent.pointerDown(screen.getByRole("listbox"));
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Outside" }));
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    expect(onChange).not.toHaveBeenCalled();
    expect(trigger()).toHaveTextContent("CEO");
    openSelect();
    expect(screen.getByRole("combobox")).toHaveValue("");
  });

  it("keeps focus in the search field for clicks anywhere else in the panel", () => {
    const onChange = vi.fn();
    render(<Harness initialValue="node_ceo" onChange={onChange} />);
    const search = openSelect();
    const panel = search.closest(".searchable-select__panel") as HTMLElement;

    // A prevented mousedown does not move focus out of the search field.
    expect(fireEvent.mouseDown(panel)).toBe(false);
    expect(fireEvent.mouseDown(screen.getByRole("listbox"))).toBe(false);
    expect(fireEvent.mouseDown(screen.getByRole("option", { name: "Sales" }))).toBe(false);
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(fireEvent.mouseDown(screen.getByText("No matches"))).toBe(false);
    expect(fireEvent.mouseDown(screen.getByRole("button", { name: "Clear search" }))).toBe(false);
    // The search field itself still takes clicks, for example to place the caret.
    expect(fireEvent.mouseDown(search)).toBe(true);

    fireEvent.pointerDown(screen.getByText("No matches"));
    expect(search).toHaveFocus();
    fireEvent.keyDown(search, { key: "Escape" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("follows the controlled value", () => {
    function ControlledParent() {
      const [value, setValue] = useState("node_ceo");
      return (
        <>
          <button type="button" onClick={() => setValue("node_ops")}>
            Pick operations elsewhere
          </button>
          <label htmlFor="source">Source</label>
          <SearchableSelect
            id="source"
            options={options}
            value={value}
            onChange={vi.fn()}
            placeholder="Select source node"
            searchLabel="Search source nodes"
          />
        </>
      );
    }
    render(<ControlledParent />);
    expect(trigger()).toHaveTextContent("CEO");
    fireEvent.click(screen.getByRole("button", { name: "Pick operations elsewhere" }));
    expect(trigger()).toHaveTextContent("Operations");
    fireEvent.click(trigger());
    expect(
      within(screen.getByRole("listbox")).getByRole("option", { selected: true })
    ).toHaveTextContent("Operations");
  });

  it("does not select an option the parent does not accept", () => {
    const onChange = vi.fn();
    render(
      <SearchableSelect
        id="source"
        options={options}
        value="node_ceo"
        onChange={onChange}
        placeholder="Select source node"
        searchLabel="Search source nodes"
      />
    );

    fireEvent.click(screen.getByRole("button"));
    fireEvent.click(screen.getByRole("option", { name: "Sales" }));

    expect(onChange).toHaveBeenCalledWith("node_sales");
    expect(screen.getByRole("button")).toHaveTextContent("CEO");
  });

  it("cannot open while disabled, and closes when it becomes disabled", () => {
    const { rerender } = render(<Harness disabled />);

    expect(trigger()).toBeDisabled();
    fireEvent.click(trigger());
    fireEvent.keyDown(trigger(), { key: "ArrowDown" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    rerender(<Harness />);
    openSelect();
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    rerender(<Harness disabled />);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(trigger()).toHaveAttribute("aria-expanded", "false");

    rerender(<Harness />);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("does not submit the surrounding form from the search field", () => {
    const onSubmit = vi.fn((event: { preventDefault: () => void }) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <label htmlFor="source">Source</label>
        <SearchableSelect
          id="source"
          options={options}
          value=""
          onChange={vi.fn()}
          placeholder="Select source node"
          searchLabel="Search source nodes"
        />
        <button type="submit">Save</button>
      </form>
    );

    fireEvent.click(trigger());
    fireEvent.click(screen.getByRole("option", { name: "CEO" }));
    fireEvent.click(trigger());
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "c" } });
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
