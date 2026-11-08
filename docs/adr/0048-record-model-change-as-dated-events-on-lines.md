---
status: accepted
---

# Record model change as dated events on a base line and scenarios

## Context

A Version is a full copy of a Model's graph with no time, and the change list is a computed difference. Neither says when something happens, neither can start from a point in the past, and a copy per version cannot answer "what did the organisation look like in March?". The product owner wants the model to be event-based: a starting situation, dated events, one line that always describes what really happened, and any number of what-if scenarios that branch from a state of any line, also from the past.

## Decision

- A Model has **lines**. Exactly one is the **Base line** (nameable; it describes what has really happened and, at all times, the present state). Any number of others are **Scenarios**. A Scenario has a parent line and a **branch point**: an event of the parent line (the Base line or another Scenario), meaning "the state after that event".
- A line holds **events**. An event has a mandatory date (`occurred_on`, a calendar date), a title, an optional note, and an ordered list of **changes** (add, remove, update or re-route nodes and connections, by stable element id). Order is by date and then entry order. An event dated after today in the Organization's time zone is **planned**; the Base line may hold planned events for known changes.
- The state after event E of line L is the replay, in order, of the events of every ancestor line up to its branch point, then the events of L up to and including E. A Scenario never inherits later events of its parent unless they precede its branch point in the parent's order. A branch refers to an event; it is not a copy.
- Nodes and connections have stable ids created by the event that adds them. The graph tables that hold a full graph per version (`nodes`, `connections` with `version_id`) are replaced by the event tables; the current graph is computed by replay (and may be cached later).
- Node positions on the canvas are a property of the drawing, not of history. They are stored per line and node and fall back to the parent line, then to the position given when the node was added. Moving a node writes no event.
- Metrics, metric values and simulations belong to a line in place of a version. Creating a Scenario copies the parent's metrics, as a fork does today.
- Existing data migrates: the baseline version becomes the Base line with one event "Initial situation" holding its whole graph, dated the Model's creation day; a forked version becomes a Scenario branching from that event, with one event holding the difference to its base.
- Every event, line and branch change is audited; the audit entry carries the model, line, event and the kind of change, not the element names.

## Consequences

- The state at any date or event can be read; history can be corrected; scenarios can model "what if we had not done X a year ago".
- Writes cost a replay for validation (ADR-0049). Graphs are small, so replay in the application is acceptable; snapshots are a later optimisation, not a first-version requirement.
- Version, merge and the change list as separate concepts disappear from the interface once the timeline lands; ADR-0050 replaces merge.
- Every API route, MCP tool and test that takes a `version_id` changes to a line and, where it reads a graph, an event.

Refines ADR-0043 (the metamodel stays per model and shared by all lines). Replaces the version model of ADR-0045 together with ADR-0050.
