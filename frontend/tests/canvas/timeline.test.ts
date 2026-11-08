import { describe, expect, it } from "vitest";

import { adoptMessage, branchPointMessage, canAdopt, canManageLine, canWriteLine, CHAIN_HINT_CODES, chainBrokenMessage, deleteLineMessage, changeRows, lineTree, shownChange, START_PARAM, startInfo, startReadOnly, startRequest, startShown, tabQuery, type ChainHint } from "../../src/models/timeline";
import { describeEdit } from "../../src/models/timeline-messages";

const hint = (code: string, extra: Partial<ChainHint> = {}): ChainHint => ({ code, change_title: "Hire", change_date: "2026-03-01", element_name: "Sales", element_kind: "node", ...extra });

describe("chainBrokenMessage", () => {
  it("has a message for every hint code in both languages, naming the change and saying what to do", () => {
    expect(CHAIN_HINT_CODES).toHaveLength(9);
    for (const code of CHAIN_HINT_CODES) {
      for (const locale of ["en", "fi"] as const) {
        const message = chainBrokenMessage(hint(code, { type_name: "Team", source_name: "A", target_name: "B", scenario_name: "Plan B", branch_change_title: "Reorg", branch_change_date: "2026-02-01" }), locale);
        expect(message, `${code} ${locale}`).toContain(code === "restore_branch_change" ? "Reorg" : "Hire");
        expect(message.length).toBeGreaterThan(40);
        expect(message).not.toMatch(/chain_broken|undefined|null/);
      }
    }
  });
  it("names the element, the type and both ends where the cause has them", () => {
    expect(chainBrokenMessage(hint("add_element_before"), "en")).toContain('"Sales"');
    expect(chainBrokenMessage(hint("choose_existing_type", { type_name: "Team" }), "fi")).toContain('"Team"');
    expect(chainBrokenMessage(hint("remove_duplicate_connection", { element_kind: "connection", source_name: "A", target_name: "B" }), "en")).toContain('"A" to "B"');
    expect(chainBrokenMessage(hint("add_endpoint_before", { source_name: "A", target_name: "B" }), "en")).toContain("A -> B");
  });
  it("says which scenario when the failing change is in another line, and the branch change for branch causes", () => {
    expect(chainBrokenMessage(hint("add_element_before", { in_other_line: true, scenario_name: "Plan B" }), "en")).toContain('in the scenario "Plan B"');
    expect(chainBrokenMessage(hint("add_element_before", { in_other_line: false, scenario_name: "Plan B" }), "en")).not.toContain("Plan B");
    const message = chainBrokenMessage(hint("restore_branch_change", { scenario_name: "Plan B", branch_change_title: "Reorg", branch_change_date: "2026-02-01" }), "en");
    expect(message).toContain('"Plan B"');
    expect(message).toContain('"Reorg" (2026-02-01)');
  });
  it("falls back to a generic message for an unknown code or no hint", () => {
    expect(chainBrokenMessage({ code: "new_code", change_title: "Hire" }, "en")).toContain("Hire");
    expect(chainBrokenMessage(null, "fi")).toContain("Muokkaa tai poista");
  });
  it("words a branch point refusal with the scenario", () => {
    expect(branchPointMessage("Plan B", "en")).toContain('"Plan B"');
    expect(branchPointMessage(null, "fi")).toContain("alkukohta");
  });
});

describe("change list rows", () => {
  const change = (id: string, planned: boolean) => ({ id, planned });
  const kinds = (rows: ReturnType<typeof changeRows>) => rows.map((row) => (row.kind === "now" ? "now" : (row.change as { id: string }).id));
  it("puts the Now divider between the last happened and the first planned change", () => {
    expect(kinds(changeRows([change("a", false), change("b", false), change("c", true), change("d", true)], null))).toEqual(["a", "b", "now", "c", "d"]);
  });
  it("puts Now at the end when nothing is planned and at the start when everything is", () => {
    expect(kinds(changeRows([change("a", false), change("b", false)], null))).toEqual(["a", "b", "now"]);
    expect(kinds(changeRows([change("a", true)], null))).toEqual(["now", "a"]);
    expect(kinds(changeRows([], null))).toEqual(["now"]);
  });
  it("marks the shown change, the last one by default", () => {
    const rows = changeRows([change("a", false), change("b", true)], null).filter((row) => row.kind === "change");
    expect(rows.map((row) => row.kind === "change" && row.selected)).toEqual([false, true]);
    const chosen = changeRows([change("a", false), change("b", true)], "a").filter((row) => row.kind === "change");
    expect(chosen.map((row) => row.kind === "change" && row.selected)).toEqual([true, false]);
  });
  it("shows the requested change when the line has it, else the last, and tells whether it is the last", () => {
    const items = [{ id: "a" }, { id: "b" }, { id: "c" }];
    expect(shownChange(items, "a")).toEqual({ change: items[0], isLast: false });
    expect(shownChange(items, "zzz")).toEqual({ change: items[2], isLast: true });
    expect(shownChange(items, null).isLast).toBe(true);
    expect(shownChange([], null)).toEqual({ change: null, isLast: true });
  });
  it("builds tab queries that carry the line and the change", () => {
    expect(tabQuery(null, null)).toBe("");
    expect(tabQuery("L", null)).toBe("?line=L");
    expect(tabQuery("L", "E")).toBe("?line=L&change=E");
  });
});

describe("line tree", () => {
  const line = (id: string, kind: "base" | "scenario", parent: string | null, creator: string | null = null) => ({ id, name: id, kind, parent_line_id: parent, created_by_user_account_id: creator });
  it("lists the Base line first and each Scenario right under its parent", () => {
    const lines = [line("s1", "scenario", "base"), line("base", "base", null), line("s2", "scenario", "base"), line("s1a", "scenario", "s1")];
    expect(lineTree(lines).map((row) => `${row.depth}:${row.line.id}`)).toEqual(["0:base", "1:s1", "2:s1a", "1:s2"]);
  });
  it("keeps a Scenario whose parent is missing instead of losing it", () => {
    expect(lineTree([line("base", "base", null), line("x", "scenario", "gone")]).map((row) => row.line.id)).toEqual(["base", "x"]);
  });
  it("lets an Owner or Admin manage any line and a Member only the Scenarios they created", () => {
    const base = line("base", "base", null);
    const mine = line("s", "scenario", "base", "me");
    const theirs = line("t", "scenario", "base", "you");
    expect(canManageLine(base, "admin", "me")).toBe(true);
    expect(canManageLine(base, "member", "me")).toBe(false);
    expect(canManageLine(mine, "member", "me")).toBe(true);
    expect(canManageLine(theirs, "member", "me")).toBe(false);
    expect(canManageLine(theirs, "owner", "me")).toBe(true);
  });
  it("lets a Member write Scenarios but not the Base line, and adopt only into a parent they may write", () => {
    const lines = [line("base", "base", null), line("s", "scenario", "base"), line("c", "scenario", "s")];
    expect(canWriteLine(lines[0], "member")).toBe(false);
    expect(canWriteLine(lines[1], "member")).toBe(true);
    expect(canAdopt(lines[1], lines, "member")).toBe(false);
    expect(canAdopt(lines[1], lines, "owner")).toBe(true);
    expect(canAdopt(lines[2], lines, "member")).toBe(true);
    expect(canAdopt(lines[0], lines, "owner")).toBe(false);
  });
});

describe("adopt and delete messages", () => {
  it("explains parent_moved_on with the count and the suggestion to start a new scenario", () => {
    const message = adoptMessage({ reason: "parent_moved_on", parent_name: "Base line", changes_after: 2 }, "en");
    expect(message).toContain('"Base line"');
    expect(message).toContain("2 changes");
    expect(message).toContain("new scenario");
    expect(adoptMessage({ reason: "parent_moved_on", parent_name: "Peruslinja", changes_after: 1 }, "fi")).toContain("uusi skenaario");
  });
  it("explains dates_precede, nothing_to_adopt and the other reasons", () => {
    expect(adoptMessage({ reason: "dates_precede", parent_last_change_title: "Reorg" }, "en")).toContain('"Reorg"');
    expect(adoptMessage({ reason: "nothing_to_adopt" }, "en")).toContain("nothing to adopt");
    expect(adoptMessage({ reason: "nothing_to_adopt" }, "fi")).toContain("liitettävää");
    expect(adoptMessage({ reason: "base_line" }, "en")).toContain("Base line");
    expect(adoptMessage({ reason: "other" }, "en")).toContain("could not be adopted");
  });
  it("explains has_children and the Base line on delete", () => {
    expect(deleteLineMessage({ reason: "has_children" }, "en")).toContain("Delete them first");
    expect(deleteLineMessage({ reason: "has_children" }, "fi")).toContain("Poista ne ensin");
    expect(deleteLineMessage({ reason: "base_line" }, "en")).toContain("Base line");
  });
});

describe("describeEdit", () => {
  const names = new Map([["n1", "Sales"], ["n2", "Support"], ["t1", "Team"]]);
  it("resolves element, end and type names for reading", () => {
    expect(describeEdit({ op: "add_node", element_id: "n1", payload: { name: "Sales", node_type_id: "t1" } }, names, "en")).toBe('Add the node "Sales" (Team)');
    expect(describeEdit({ op: "add_connection", element_id: "c1", payload: { source_node_id: "n1", target_node_id: "n2" } }, names, "fi")).toContain('"Sales" -> "Support"');
    expect(describeEdit({ op: "remove_node", element_id: "n2", payload: {} }, names, "en")).toBe('Remove the node "Support"');
  });
});

describe("the Start row", () => {
  const base = { id: "b", name: "Base line", kind: "base" as const, parent_line_id: null, branch_change_id: null };
  const plan = { id: "s", name: "Plan B", kind: "scenario" as const, parent_line_id: "b", branch_change_id: "e1" };
  const parentChanges = [{ id: "e1", title: "Reorg", occurred_on: "2026-02-01" }, { id: "e2", title: "Hire", occurred_on: "2026-03-01" }];
  const own = [{ id: "c1", planned: false }, { id: "c2", planned: true }];

  it("exists only for a Scenario and names the parent line, the branch change and its date", () => {
    expect(startInfo(base, [base, plan], [])).toBeNull();
    expect(startInfo({ ...plan, parent_line_id: "gone" }, [base, plan], parentChanges)).toBeNull();
    expect(startInfo(plan, [base, plan], parentChanges)).toEqual({ parentLineId: "b", parentLineName: "Base line", parentIsBase: true, changeId: "e1", changeTitle: "Reorg", changeDate: "2026-02-01" });
    expect(startInfo(plan, [base, plan], [])).toMatchObject({ changeId: "e1", changeTitle: null, changeDate: null });
  });

  it("follows a corrected history: it reads the current branch change and the current parent changes", () => {
    const moved = [{ id: "e1", title: "Reorg", occurred_on: "2026-01-15" }];
    expect(startInfo(plan, [base, plan], moved)?.changeDate).toBe("2026-01-15");
    expect(startInfo({ ...plan, branch_change_id: "e2" }, [base, plan], parentChanges)?.changeTitle).toBe("Hire");
  });

  it("is the first row, not a Change: it takes no Now divider, no change count and no selection of a Change", () => {
    const info = startInfo(plan, [base, plan], parentChanges)!;
    const rows = changeRows(own, null, info, false);
    expect(rows.map((row) => row.kind)).toEqual(["start", "change", "now", "change"]);
    expect(rows.filter((row) => row.kind === "change")).toHaveLength(own.length);
    expect(rows.find((row) => row.kind === "change" && row.selected)).toMatchObject({ change: { id: "c2" } });
    const selected = changeRows(own, "c1", info, true);
    expect(selected[0]).toMatchObject({ kind: "start", selected: true });
    expect(selected.some((row) => row.kind === "change" && row.selected)).toBe(false);
    expect(changeRows(own, null).some((row) => row.kind === "start")).toBe(false);
  });

  it("is shown by ?change=start only when the line has one, and the canvas is then read-only whatever the role", () => {
    const info = startInfo(plan, [base, plan], parentChanges);
    expect(START_PARAM).toBe("start");
    expect(startShown("start", info)).toBe(true);
    expect(startShown("start", null)).toBe(false);
    expect(startShown("c1", info)).toBe(false);
    expect(startShown(null, info)).toBe(false);
    expect(startReadOnly(true, true)).toBe(false);
    expect(startReadOnly(false, true)).toBe(true);
    expect(startReadOnly(false, false)).toBe(false);
  });

  it("reads the PARENT line's state after the branch change", () => {
    expect(startRequest(startInfo(plan, [base, plan], parentChanges)!)).toEqual({ lineId: "b", changeId: "e1" });
    expect(tabQuery("s", START_PARAM)).toBe("?line=s&change=start");
  });
});
