# TASK-069C Deterministic Timeseries Generator

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Schatten
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

The LLM picks generation parameters, and Schatten generates the values
deterministically. The LLM never emits thousands of numbers itself.

## Goal

Add a pure, deterministic timeseries generator with a validated specification.
It will be used by the read tool's preview (TASK-069H) and by change-set
staging (TASK-069I).

## Requirements

- Create the package `backend/app/api/v1/timeserie_generation/`.
  - `schemas.py` defines `TimeserieGenerationSpec` (`StrictBaseModel`, camelCase
    aliases) with these fields:
    - `start_date`, plus exactly one of `periods` or `end_date`;
    - `time_unit` (`day|week|month|year`, reusing the existing literal);
    - `base_level`;
    - `trend`: `none|linear|percent|logistic` with its parameters;
    - `seasonality[]`: period, amplitude, `additive|multiplicative`;
    - `noise`: `std` or `relative_std`, and an optional `ar1` coefficient;
    - `level_shifts[]`: date and delta;
    - optional `clamp_min` and `clamp_max`;
    - `decimals`;
    - `seed`.
  - `generator.py` provides `generate(spec) -> list[GeneratedPoint]` and the
    constant `GENERATOR_VERSION`.
- Use `numpy.random.default_rng(seed)`. Identical specs give identical output.
- Align dates to the rules in `_ensure_timeserie_value_date_is_valid`: weeks
  start on Monday, months on the 1st, years on 1 January. Reject a
  `start_date` that is not aligned, with a clear validation error.
- Output is numeric only (`value_unit` `number`). Enforce at most 20,000
  points.
- Declare `numpy` directly in `backend/pyproject.toml`. It is already locked
  transitively, so no new package is installed. Confirm `uv.lock` adds no new
  package.

## Acceptance Criteria

- [ ] Unit tests cover:
      - determinism for the same seed and different output for a different
        seed;
      - date alignment for each time unit and rejection of unaligned starts;
      - trend, seasonality, noise and level shifts;
      - clamping, rounding and the point limit;
      - `periods` versus `end_date`.
- [ ] Generated output passes the existing timeserie value validation.
- [ ] No API route, migration or new locked package is added.

## Out Of Scope

- MCP tools, change sets and UI.
- String and boolean series, or generation fitted to existing data
  (forecasting).

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/decisions/ADR-015-ai-via-mcp.md
docs/domains/ORG_STATES.md
docs/TESTING.md
backend/app/api/v1/org_states/schemas.py
backend/app/api/v1/org_states/org_states_service.py
```

## Testing

Required:

- [ ] Backend tests (`backend/tests/test_timeserie_generation.py`)
- [ ] Lint
- [ ] Typecheck

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Update `docs/domains/AI.md` with the generator specification and version.

## Notes For AI Agent

- Branch: `feature/TASK-069C-timeseries-generator`.
- Do not start until TASK-069A and ADR-015 are accepted.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069C/`.
- Report all changed files and every verification command run.
- Developer-accepted additions (2026-10-23, AI review
  `TASK-069C/review-001` F-006): the optional seasonality `peakOffset`
  (default 0), at most 10 seasonality components, at most 100 level shifts,
  `decimals` 0 to 10 (default 2), `seed` 0 to 2^32 - 1 and the
  `TimeserieGenerationError` type. They are part of the generator version 1
  spec contract.
- Developer decision (2026-10-23, AI review `TASK-069C/review-001` F-007):
  numeric spec fields are strict, so strings and booleans are not coerced and
  integer fields reject floats.
