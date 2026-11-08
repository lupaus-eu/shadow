# Technical design: Change terminology (rename event to Change, change to Edit)

Status: accepted

## Current and target state

- **Current state:** the dated item on a line is an "event" (`timeline_events`, `/events`, `add_event`), its steps are "changes" (`event_changes`, `changes[]`). The Scenario change list has no row for the state it starts from.
- **Target state:** ADR-0052: the dated item is a **Change**, its steps are **Edits**, everywhere including the database; a Scenario's list starts with a fixed **Start** row.

## Rename map

| Layer | From | To |
| --- | --- | --- |
| Table | `timeline_events` | `timeline_changes` |
| Table | `event_changes` | `change_edits` |
| Column | `event_changes.event_id` | `change_edits.change_id` |
| Column | `model_lines.branch_event_id` | `model_lines.branch_change_id` |
| Constraints, indexes, policies, identity sequence | names containing `event` / `event_changes` | matching `change` / `change_edits` names |
| ORM | `TimelineEvent`, `EventChange` | `TimelineChange`, `ChangeEdit` |
| Engine | `EventRecord`, `Change`, `ChangeInvalid`, `apply_change(s)` | `ChangeRecord`, `Edit`, `EditInvalid`, `apply_edit(s)` |
| Routes | `/lines/{line}/events`, `/events/{event}`, `/events/{event}/nodes`, `/connections` | `/lines/{line}/changes`, `/changes/{change}`, `/changes/{change}/nodes`, `/connections` |
| Query / JSON | `event_id`, `event`, `event_count`, `change_counts`, `changes[]`, `branch_event_id` | `change_id`, `change`, `change_count`, `edit_counts`, `edits[]`, `branch_change_id` |
| MCP | `list_events`, `add_event`, `update_event`, `delete_event`; arguments `event_id`, `changes` | `list_changes`, `add_change`, `update_change`, `delete_change`; `change_id`, `edits` |
| Audit | `event.created/updated/deleted` | `change.created/updated/deleted` (old rows keep the old names; Activity reads both) |
| Env | `LIMIT_EVENTS_PER_LINE` | `LIMIT_CHANGES_PER_LINE` |
| URL parameter | `?event=` | `?change=` |
| UI | Event, Planned event, event list (fi: tapahtuma, suunniteltu tapahtuma, tapahtumalista) | Change, Planned change, change list (muutos, suunniteltu muutos, muutoslista); steps: Edit (muokkaus) |

The payload operation names (`add_node`, `reroute_connection`, ...) and JSON payloads do not change. Do the rename in two passes so the words never collide: first the inner "change" becomes "edit", then "event" becomes "change".

## Database

Migration 0065 renames tables, columns, constraints, indexes, RLS policies, the identity sequence and the foreign keys; no data moves; the downgrade renames back. Migrations 0060 to 0064 keep their historical names and docstrings. The DBML is regenerated.

## API and MCP

Same behaviour, new names (map above). The 422 `chain_broken` hint codes that contain "event" are renamed to "change" and the hint fields follow (`event` becomes `change`). `GET /models/{model}/lines/{line}/state` also accepts `?change_id=`; the Start row of a Scenario is read through the parent's state route at the branch change (no new route).

## Frontend

Types in `client.ts`, components, message files, URL parameter, outlet fields, Playwright mocks and tests follow the map; Finnish and English texts are rewritten with the new terms. The Start row (model-timeline ticket 12) is built after the rename.

## Testing

- Backend: the full suite renamed and green; a migration test that upgrades a seeded 0064 database to 0065 and back with rows intact; a grep guard test or script listing allowed leftovers of "event" (Audit Event, Stripe, historical migrations, legacy audit actions).
- Frontend: typecheck, build, unit tests and the Playwright specs with the new names; message completeness test.
- `make models`, `python3 scripts/check-compose-ports.py`.

## Configuration

`LIMIT_EVENTS_PER_LINE` becomes `LIMIT_CHANGES_PER_LINE` in `.env.example` and `.env.production.example`. A developer's local `.env` that sets the old name needs the new one (the defaults are unchanged).

## Architecture effects

No service or boundary change; C4 component descriptions and the DBML change.

## Documentation effects

- [ ] ADR-0052 accepted; closing lines in ADR-0048, 0049, 0050 (done with this design)
- [ ] `CONTEXT.md`, `docs/user/`, `docs/admin/`, `docs/design/`, `docs/architecture/`, `docs/runbooks/mcp-interface.md`, `docs/operations/`, `docs/gdpr/` (ticket 03)
- [ ] The PRDs, domain model and technical designs of `model-timeline` and `structure-canvas`: vocabulary only; the completion records of finished tickets stay as written (ticket 03)

## Options and decision

1. Rename everything including the database (chosen by the product owner): one consistent vocabulary, cheapest before a release.
2. Rename only the interface and the documents, keeping `event` in code: a permanent translation layer, and agents would still see `add_event`. Rejected.
3. Rename the dated item to State: confuses the thing with its result. Rejected (see ADR-0052).
