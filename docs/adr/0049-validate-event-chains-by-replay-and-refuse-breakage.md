---
status: accepted
---

# Validate event chains by replay and refuse breakage

## Context

Records contain mistakes, so every event must be changeable afterwards: its date, its content, even deletion. Later events and Scenarios depend on earlier ones (an event moves a person into a team that an earlier event created), so a correction can make the chain impossible to replay.

## Decision

- Every write that creates, changes, moves in time or deletes an event (and every canvas edit, which is a change inside an event) is checked by replaying the whole affected chain in memory before anything is saved: the changed line from its start, and every line that branches from any event of it, recursively.
- A replay step fails when: an element it needs does not exist at that point (or exists twice), a node or connection type does not exist in the metamodel, the metamodel does not allow the connection between the two node types, a connection endpoint is missing or equals the other, a branch event no longer exists, or a Scenario event is dated before its branch event.
- If any step fails nothing is saved and the API answers 422 with `reason: "chain_broken"`, the event, the change position, the element and a machine-readable cause. The interface turns it into a readable message that names the event and element, says why and says what to do first (change or remove the dependent event, move this event to an earlier date). No raw server text reaches the page and the person's input stays in the form.
- Deleting a node or connection type that an event or a branch still uses stays refused with `in_use` (as ADR-0043 already does for the graph), now checked against events.
- The write holds a row lock on the Model for the check and the save, so two writers cannot each pass the check and together break the chain. A stale `expected_version` still gives 409.
- A line with children cannot be deleted. The Base line cannot be deleted.

## Consequences

- Corrections are always possible, and a correction can never leave the model unreadable.
- The cost of a write grows with the chain length and the number of dependent Scenarios. Limits on events per line and a snapshot cache are the planned answer if this becomes slow.
- The refusal messages are a product feature and need Finnish and English texts for every cause.
