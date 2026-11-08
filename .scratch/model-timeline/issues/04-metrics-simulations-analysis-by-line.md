# Ticket 04: metrics simulations analysis by line

Status: ready-for-agent

## Goal

Make metric, simulation and analysis routes, the MCP read tools and the analysis page work on a line.

## Implementation

- Migration 0062: `line_id` on `metrics`, `metric_values` and `simulations` (added nullable by 0061) becomes required and `version_id` is dropped. Rows left without a `line_id` (versions forked by the old routes after 0061, which have no line) are removed with their version's data; development databases only, nothing is released.
- New Models already get a Base line with the same id as their baseline version (ticket 02), so existing metric and simulation rows map to the Base line by id.
- Routes take `line_id` where they took `version_id`; graph reads inside them use the state function.
- MCP read tools and `run_simulation`, `generate_analysis` take `line_id`.
- Not done: scenario creation (ticket 06), frontend (ticket 09).

## Acceptance criteria

- [ ] Every existing metric, simulation and analysis test passes with the Base line in place of the baseline version.
- [ ] Formulas and derived metrics are scoped to a line.
- [ ] The MCP call log still records the calls.

## Testing

- [ ] Backend/API test — existing suites ported to lines
- [ ] Frontend/UI test — client types updated, typecheck
- [ ] Browser/E2E validation — not applicable
- [ ] Migration/integration/architecture validation — `pytest -q`, `test_no_llm_calls.py`

## Ajetut tarkistukset

- [ ] `<command or browser path>` — <passed / failed / blocked and why>

## AI review

- [ ] Review run on the ticket's diff — <tool or skill used, findings, and how each was resolved or accepted>

## Documentation effects

- [ ] Update architecture or ADR

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 03

## Completion record

- <What was finished, which criteria were met, and where effects were recorded?>

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
