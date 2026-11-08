---
status: accepted
---

# Replace version merge with fast-forward adoption of a scenario

## Context

ADR-0045 merged a Version into its base by applying its change list. With events on lines (ADR-0048) there is no change list to apply, and a Scenario is a what-if, not a draft of the Base line. Still, a Scenario that "came true" should be adoptable into the line it branched from without retyping it.

## Decision

- **Adopt** appends a Scenario's own events to its parent line, keeping their titles, notes, changes and dates, when the parent has no events after the branch point (a fast-forward). Dates earlier than the parent's last event are refused. After adoption the Scenario is deleted if it has no child Scenarios; otherwise it stays with no events of its own and its branch point moves to the adopted events' last event, and its child Scenarios branch from the parent line at the adopted copies of the events they branched from (their states do not change).
- The adopted events are created again in the parent (new ids and entry numbers, same date, title, note and changes), and the positions drawn on the Scenario for the nodes it added go with them.
- If the parent has events after the branch point, adoption is refused with a message that says so and suggests creating a new Scenario from the parent's latest state and redoing the differing changes there.
- The chain check of ADR-0049 runs before saving. Owners and Admins adopt into the Base line; Members may adopt a Scenario into another Scenario they could edit.
- A Scenario's metrics are not adopted, as metrics were not merged by ADR-0045.

## Consequences

- No three-way merge and no conflict resolution to build; the common case (a plan that was carried out) works, the rest is explicit.
- Planned events dated in the future can be adopted into the Base line and then show as planned.

Supersedes ADR-0045. Part of the change set of ADR-0048. Implemented in ticket 08 of the model timeline, which also retired the version routes and tables.

ADR-0052 renames the vocabulary of this decision: read "event" as Change and "change" (a step) as Edit.
