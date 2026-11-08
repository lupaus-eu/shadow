# Feature: Model timeline (Base line, events and scenarios)

Status: accepted

## Goal

A Model describes an organisation over time. One **Base line** records what has really happened
to the company, and always shows its present state. Dated **events** along the line record each
change: elements added or removed, connections re-routed, anything the graph allows. A person can
look at the situation after any event, record changes known in advance, correct mistakes, and build
any number of **Scenarios** that start from a state of the Base line (also in the past) or of another
Scenario and look forward, or sideways, from there.

The value: one truthful history, a safe place to ask "what if", and the ability to answer "what did
the organisation look like then?". Today a Model has only versions (full copies with no time) and a
computed change list.

## User

- **Member**: reads every line and event; creates and edits Scenarios and their events.
- **Owner and Admin**: everything a Member does, plus writing to the Base line (recording what has
  happened and what is planned), adopting a Scenario into its parent, and deleting Scenarios.
- **Agent (MCP client)** acting for a person: the same rights as that person.
- **Platform Admin and Support Agent**: no content access without approved Support Access (unchanged).

## Use case

1. An Owner creates a Model. It has a Base line (named "Base line" by default, renameable) with the
   initial situation as its first event, dated that day.
2. They record events as things happen: "Support team founded", 1 March; "Ada moves to Support",
   15 March. Each event has a date and a list of changes, built by drawing on the Structure canvas or in
   the event editor.
3. They record a known future change: "New product team", 1 January next year. It shows in the event
   list in another colour and with a "Planned" label until its date arrives, and becomes part of the
   present state then.
4. They pick an event in the list to see the state after it; the canvas redraws that state.
5. They find that "Ada moves to Support" should have been 1 April. They change the date. If a later event
   depended on the earlier date, the change is refused with a message that names the events and says what
   to do first.
6. A Member picks the state after "Support team founded" and creates a Scenario "No support team, keep
   the old way": it starts from that past state and has events of its own.
7. A Scenario can start from a state of another Scenario, and so on.
8. A Scenario that came true is adopted into its parent line (when the parent has not moved on since
   the branch point), or the person recreates the differences in a new Scenario from the parent's latest state.
9. An agent reads states and writes events and Scenarios through MCP under the same rules.

## Acceptance criteria

### Lines and Scenarios

- [x] Every Model has exactly one Base line; it can be renamed and cannot be deleted.
- [x] A Member can create a Scenario from any event of any line they can read (the state after that
      event); a Scenario has a name and an optional description.
- [x] Any number of Scenarios can exist; a Scenario can branch from another Scenario.
- [ ] A Scenario shows the parent's state at the branch point and its own events after it. Later events of
      the parent do not appear in it, and events inserted into the parent's history before the branch point do (the
      Scenario's owner sees a notice that its start changed).
- [x] A Scenario with child Scenarios cannot be deleted (409 `has_children`); an Owner or Admin or the
      Scenario's creator can delete one without children.
- [ ] The Base line is visibly different from Scenarios everywhere a line is shown.

Verified by: backend tests `test_timeline_tables.py`, `test_timeline_lines.py`, `test_timeline_events.py` (PostgreSQL). Not ticked: the notice that a Scenario's start changed and the visible Base line marking (backend sets `start_changed_at`; the UI parts were only run in Playwright against a mocked API).

### Events

- [x] An event has a title, a date (required, calendar date), an optional note and an ordered list of changes.
      Events sort by date, then by the order they were entered in.
- [x] Changes: add node, remove node, update node (name, description, type), add connection, remove
      connection, re-route connection (new source and/or target), change connection type.
- [x] Only the Base line receives events from Owners and Admins; a Member's write to the Base line gets 403.
- [ ] An event dated after today (in the Organization's time zone) is planned, in any line. Planned
      events are listed in a different colour with a "Planned" label (not by colour alone). The present
      state of a line is the state after the last event dated today or earlier.
- [x] Choosing any event, planned or not, shows the state after it.
- [x] Any event can be changed (title, note, date, changes) or deleted afterwards, by a person who may
      write to that line.
- [x] A write that would break the chain is refused with 422 `chain_broken` and saves nothing. Breaking means:
      a needed element does not exist at that point or exists twice, a type is missing, the metamodel
      forbids a connection, an endpoint is missing, a branch event disappears, or a Scenario event
      falls before its branch event. The check covers the line and every Scenario that branches from it.
- [ ] The refusal names the event and element, says why, and says what to change first; the person's
      input stays on the screen.
- [x] An event that is the branch point of another line cannot be deleted (it would break that line); the
      message names the Scenario.
- [x] Concurrent edits are not silently overwritten (stale `expected_version` gives 409).
- [x] Every event and line write is audited; every new table has `organization_id` and row-level security.

Verified by: backend `test_timeline_events.py`, `test_timeline_edits.py`, `test_timeline_read_api.py`, `test_timeline_adopt.py`. Not ticked: the planned colour, label and "Now" divider, and "the person's input stays on the screen" (Vitest and mocked-API Playwright only; no real browser against the real backend).

### Reading state

- [ ] `state after event E of line L` returns nodes, connections, types and positions, and is the only
      way the canvas, analysis and MCP read a graph.
- [x] A state can also be requested by date ("as of 1 March"): it is the state after the last event dated that
      day or earlier.
- [x] Positions are stored per line and node, fall back to the parent line and then to the position the
      node was added with, and moving a node writes no event.

Verified by: `test_timeline_read_api.py` (as-of, positions fallback). Not ticked: "the only way the canvas, analysis and MCP read a graph" is a design claim no test enforces.

### Metrics, simulations and analysis

- [x] Metrics, metric values, simulations and analyses belong to a line instead of a version.
- [x] Creating a Scenario copies the parent's metrics and values, as a fork does today.
- [x] Existing models migrate: the baseline version becomes the Base line with one "Initial situation"
      event; each forked version becomes a Scenario with one event holding its difference. Nothing is lost.

Verified by: `test_metrics_by_line.py`, `test_timeline_lines.py`, `test_timeline_migration.py`.

### Adopting a Scenario

- [x] A Scenario's own events can be appended to its parent line when the parent has no events after the
      branch point and no event would fall before the parent's last event; otherwise it is refused with
      an explanation and the suggestion to recreate the differences from the parent's latest state.
- [x] Owners and Admins adopt into the Base line; the chain check runs before saving; metrics are not adopted.

Verified by: `test_timeline_adopt.py`.

### Agent tools (MCP)

- [x] Reads: `list_lines`, `list_events`, `get_state` (by line and event or date).
- [x] Writes: `create_scenario`, `add_event`, `update_event`, `delete_event`, `adopt_scenario`.
- [x] Tools obey the same roles, read-only state, chain check and audit (`source: "mcp"`) as the web
      application, and appear in the agent call log.

Verified by: `test_mcp.py::test_agents_read_and_write_lines_events_and_adopt_scenarios_under_the_same_rules`.

### Cross-cutting

- [x] Finnish and English texts, including every refusal cause.
- [x] A read-only Organization can read all lines and states, and cannot write.
- [x] An event list of 2000 events and a state of 500 nodes load in under two seconds on the development
      stack (measured and recorded in the technical design).

Verified by: Vitest `tests/canvas/timeline.test.ts` (every cause has a Finnish and English message; the Finnish text was not reviewed by a native speaker), `test_timeline_read_api.py`, `test_timeline_events.py` (read-only Organization), and `backend/tests/test_timeline_performance.py` (state 0.2 s, events 0.2 s at 2000 events and 500 nodes; numbers in the technical design).

## Not in this version

- Manual re-ordering of events within one day (order is entry order).
- Three-way merge, or adopting a Scenario that the parent has moved past.
- A separate "cancelled" state for planned events (delete or move them).
- Notifications when a planned event's date arrives or when a branch's start changes beyond the notice.
- Per-line metamodels (types stay shared by the whole Model, ADR-0043).
- Comparing two arbitrary states side by side (the Structure canvas marks what one event changed).
- Snapshots and caching of states (added only if the performance criterion fails).
- Importing events from other systems.

## Domain terms

Defined in `domain-model.md` and to be added to `CONTEXT.md`: **Base line**, **Scenario**, **Line**,
**Event**, **Change**, **Planned event**, **Present state**, **Branch point**, **State**, **Chain**,
**Adopt**. Replaces **Version**, **Baseline**, **Change list** and **Merge**.

## Documentation effects

- [x] `CONTEXT.md` - new vocabulary; old terms retired (ticket 11)
- [x] `docs/architecture/database.md`, DBML and C4 - tables, containers and components (ticket 01 and each migration ticket)
- [x] `docs/architecture/api.md` - routes (tickets 03 to 08)
- [x] `docs/architecture/audit.md` - new audit actions (ticket 05)
- [x] `docs/adr/` - ADR-0048 to ADR-0050 accepted; ADR-0045 superseded (ticket 08)
- [x] `docs/user/README.md` and `docs/admin/README.md` - timeline, scenarios, planned events, adoption (ticket 11)
- [x] `docs/design/` - event list, planned marking, refusal messages (ticket 09)
- [x] `docs/runbooks/mcp-interface.md` - new tools (ticket 08)
- [x] `docs/gdpr/` - evaluated: audit entries carry no element names (ticket 05)

## Open questions

Recommendations in brackets.

- Does a Scenario inherit later events of its parent? [No; only events up to its branch point, but
  history inserted before the branch point flows in with a notice.]
- Can the Base line get events dated in the past? [Yes, to record late or corrected history.]
- Who writes the Base line? [Owners and Admins; Members write Scenarios.]
- Adopting a Scenario: fast-forward only? [Yes (ADR-0050).]
- Metrics of a Scenario: copy at creation? [Yes; a redesign of metrics over time is a later feature.]
- Event dates by day and metrics monthly? [Yes.]
- Should the present state of the Base line be materialised daily by the worker? [No; computed on read.]
