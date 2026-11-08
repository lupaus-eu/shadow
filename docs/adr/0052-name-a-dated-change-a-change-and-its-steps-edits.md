---
status: accepted
---

# Name a dated change a Change and its steps Edits

## Context

ADR-0048 called the dated item on a line an **event** and its steps **changes**. "Event" is also what the business calls things that happen around the organisation (a market crash, a regulation) and is the word an agent reaches for when asked about such things; the MCP tools `add_event` and `list_events` invite that mix-up. The Structure canvas also has no clickable place that shows the state a Scenario starts from. The product owner chose the word **Change** for the dated item and asked for the rename to reach the database, since no release exists yet and a later rename would cost more.

## Decision

- The dated item on a line is a **Change** (Finnish: *muutos*): a title, an optional note, a mandatory date and an ordered list of **Edits**. A planned one is a **planned change**. The state after a Change is the **State**; the list is the **change list**.
- A step inside a Change (add node, remove node, update node, add, remove, re-route or re-type a connection) is an **Edit** (Finnish: *muokkaus*). The word "change" no longer names a step.
- The rename reaches everything: tables (`timeline_events` becomes `timeline_changes`, `event_changes` becomes `change_edits`), columns (`event_id` becomes `change_id`, `branch_event_id` becomes `branch_change_id`), code and test names, API routes (`/events` becomes `/changes`, the state parameter `event_id` becomes `change_id`, JSON fields `event`, `event_count`, `changes` become `change`, `change_count`, `edits`), MCP tools (`list_events`, `add_event`, `update_event`, `delete_event` become `list_changes`, `add_change`, `update_change`, `delete_change`; their arguments follow), audit actions (`event.created`, `event.updated`, `event.deleted` become `change.created`, `change.updated`, `change.deleted`), the limit `LIMIT_EVENTS_PER_LINE` (becomes `LIMIT_CHANGES_PER_LINE`), interface texts in Finnish and English, documents and the PRDs.
- Left alone, because they are different things: the platform's **Audit Event** and `audit_events`, Stripe webhook events, browser DOM events, and the earlier migrations 0060 to 0064, which keep their historical names. Audit rows already written keep their old `event.*` actions (they are append-only); the Activity page reads both spellings.
- The word **event** stays free for the organisation's own happenings (a market event, a regulation), which may later be modelled as node types or notes.
- A Scenario's change list starts with a fixed **Start** row (Finnish: *Lähtötilanne*) that shows the state the Scenario starts from, read-only. It is not a Change and is not stored.

## Consequences

- One migration (0065) renames the tables, columns, constraints, indexes, policies and the identity sequence, with a downgrade that renames back; no data changes.
- Every client of the API and MCP changes in one step, which is cheap now because nothing is released.
- The older ADRs keep their wording, with a closing line that reads their "event" as Change and their "change" as Edit.

Refines ADR-0048, ADR-0049 and ADR-0050 (vocabulary only).
