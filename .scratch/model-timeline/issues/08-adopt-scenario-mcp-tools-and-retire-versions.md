# Ticket 08: adopt scenario mcp tools and retire versions

Status: ready-for-agent

## Goal

Adopt a Scenario into its parent, add the MCP tools, and remove versions and merge.

## Implementation

- `POST /lines/{line}/adopt` per ADR-0050 with chain check and audit `line.adopted`.
- MCP: `list_lines`, `list_events`, `get_state`, `create_scenario`, `add_event`, `update_event`, `delete_event`, `adopt_scenario`; `create_version`, `merge_version`, `get_version_changes` removed.
- Migration 0064 drops `nodes`, `connections`, `model_versions`; version routes removed; ADR-0045 marked superseded and ADR-0048 to 0050 accepted. (Ticket 07 took the number 0063 for the `metrics.node_id` remap, which is therefore already done; the old version `changes` and `merge` routes and the MCP tools `merge_version` and `get_version_changes` were also removed in ticket 07, so ticket 08 removes only what remains: the version list, create, rename and delete routes, `create_version`, `GET /models/{id}` with `version_id`, and the frozen old tables with the `in_use` checks that still look at them in `metamodel_routes.py`.)

## Acceptance criteria

- [ ] Adopt succeeds only when the parent has no events after the branch point and dates do not precede its last event; otherwise a readable refusal with the suggestion.
- [ ] Owners and Admins adopt into the Base line; metrics are not adopted.
- [ ] All new MCP tools obey roles, read-only state, chain check and the call log.

## Testing

- [ ] Backend/API test — adopt cases, roles, MCP tools, call log
- [ ] Frontend/UI test — not applicable
- [ ] Browser/E2E validation — not applicable
- [ ] Migration/integration/architecture validation — upgrade/downgrade, `make models`, `make dbml`

## Ajetut tarkistukset

- [ ] `<command or browser path>` — <passed / failed / blocked and why>

## AI review

- [ ] Review run on the ticket's diff — <tool or skill used, findings, and how each was resolved or accepted>

## Documentation effects

- [ ] Update architecture or ADR
- [ ] Update `docs/operations/` or `docs/runbooks/`

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 06
- 07

## Completion record

- <What was finished, which criteria were met, and where effects were recorded?>

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
