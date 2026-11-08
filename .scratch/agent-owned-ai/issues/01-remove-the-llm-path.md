# Ticket 01: Remove the LLM path from the backend

Status: resolved

## Goal

The backend contains no LLM client, key, model setting or route, and a test keeps it so. The analysis keeps working without the AI part.

## Implementation

- Migration `0058_agent_analysis` as in the technical design: delete `recommendations` of kind `ai`; rename `simulations.ai_summary` → `analysis_summary` and `ai_generated_at` → `analysis_summary_at`; add `analysis_summary_author`. Update `models.py`.
- Delete `app/ai.py`, `POST .../analysis/ai`, `AIRequest`, `_parse_answer`, `SYSTEM`, `AI_KIND`, the `ai_client` parameters in `main.py` and `analysis_routes.py`, and the `analysis.ai_generated` audit event.
- `AnalysisResponse`: replace `ai_available`, `ai_summary`, `ai_generated_at` with `summary`, `summary_at`, `summary_author`. Keep rule generation leaving non-`rule` proposals alone.
- `metric_io_routes.py`: workbook shows "Summary" (author, time) and the proposal source as `rule` or `agent`.
- Remove `ANTHROPIC_API_KEY` and `SHADOW_AI_MODEL` from `.env.example`, `.env.production.example`, `docker-compose.yml`, `docker-compose.prod.yml`.
- Add `backend/tests/test_no_llm_calls.py` (guard, see design).
- Remove the FakeAI tests; keep the rule-analysis tests.
- Regenerate DBML (`make dbml`).

## Acceptance criteria

- [ ] No file under `backend/app` imports an LLM SDK or names a provider host; the guard test passes and fails when a forbidden name is added (checked once by hand).
- [ ] `POST .../analysis/ai` answers 404; `GET .../analysis` returns `summary`, `summary_at`, `summary_author` and no `ai_*` fields.
- [ ] Migration 0058 runs up and down on a database that has `ai` proposals; they are gone afterwards, columns have the new names.
- [ ] Env examples and both Compose files contain no AI variable; `docker compose config` still renders.
- [ ] Workbook export has the Summary row and proposal sources.

## Testing

- [ ] Backend — analysis, export, guard; migration test up/down
- [ ] Migration/integration — PostgreSQL
- [ ] Frontend/E2E — not applicable (ticket 02)

## Ajetut tarkistukset

- `cd backend && TEST_DATABASE_URL=… pytest -q` — 194 passed (FakeAI tests removed; new test for the summary slot and the missing `/analysis/ai` route; guard test).
- Guard checked by hand: a probe file naming `api.anthropic.com` made `test_backend_code_names_no_llm_provider` fail; removed again.
- Migration 0058 on a scratch database holding an `ai` and a `decline` proposal: up deleted only `ai`, columns renamed, author added; down restored `ai_summary` and `ai_generated_at`; `upgrade head` ran again.
- `docker compose config -q` and `scripts/check-compose-ports.py` — OK.
- `make dbml` (UPDATE_DBML) — shadow.dbml regenerated.
- Frontend still reads the old `ai_*` fields until ticket 02.

## AI review

(not required)

## Documentation effects

- [ ] `docs/architecture/database.md`, `docs/architecture/dbml/shadow.dbml` — migration 0058
- [ ] `.env.example`, `.env.production.example`, Compose files — AI variables removed
- [ ] The remaining documentation is ticket 05

## Blocked by

- PRD and technical design accepted

## Completion record

(commit and notes)
