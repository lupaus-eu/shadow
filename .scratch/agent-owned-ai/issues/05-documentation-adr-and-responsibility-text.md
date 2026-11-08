# Ticket 05: Documentation, ADR and the responsibility text

Status: resolved

## Goal

The documents say that Shadow makes no LLM calls and that agent use is the user's responsibility; ADR-0044 is superseded.

## Implementation

- ADR-0047 "Make no LLM calls from the system"; closing line in ADR-0044 (status `superseded`).
- `docs/architecture/`: `api.md` (remove `/ai`, add summary and proposal routes and the two tools, audit of calls), `database.md` (0058), `stack.md` (remove the AI line), C4 (remove Anthropic, the `aiAnalysis` flow and the analysis component's Anthropic text; add an `agentAnalysis` flow), `c4/README.md`, DBML (`make dbml`), then `make models`.
- `docs/operations/README.md`: remove the AI analysis section.
- `docs/admin/` and `docs/user/`: agent responsibility, reading agent calls in Activity, asking an agent to analyse a simulation.
- `AgentsPage.tsx`: the responsibility text from the PRD (Finnish and English).
- `CONTEXT.md`: replace *AI Analysis*; add *Agent*, *Agent call*, *Proposal source*.
- `docs/gdpr/` and `docs/legal/`, `backend/legal/*`: re-read privacy notice and sub-processors; correct only if wrong. Record the terms decision (no change) in the ticket.
- `.scratch/shadow-models/PRD.md`: update analysis, agent-tool and open-question sections.

## Acceptance criteria

- [ ] No document refers to AI analysis in Shadow, `ANTHROPIC_API_KEY` or an Anthropic sub-processor (`grep -ri anthropic` over docs and code finds only ADR-0044/0047 and the guard test).
- [ ] `make models` passes.
- [ ] The connect page and admin guide state who carries cost, conduct and data handling.
- [ ] Every documentation-effects item in the PRD is ticked or justified.

## Testing

- [ ] `make models`; `npm run test:unit` for message parity; no new code paths otherwise

## Ajetut tarkistukset

- `make models` — LikeC4 valid (4 files); DBML test and dbml2sql OK.
- `npm --prefix frontend run typecheck`, `build`, `test:unit` (23 passed, message parity included) — OK.
- Backend `pytest -q` — see the last run in the completion record.
- `grep -ri anthropic` over docs, CONTEXT.md, README.md, backend, frontend/src, env examples and Compose files finds only ADR-0044, ADR-0047 and the guard test.
- Privacy notice and sub-processors page re-read: they already say an agent the person connects is their own choice and that Shadow stores no agent conversations; no sub-processor was ever added for Anthropic. Not edited (counsel owns the texts; a version change needs approval). Open: should the notice mention that agent calls are recorded per person? Noted in ADR-0047 and `docs/gdpr/records-of-processing.md`.
- Terms of service: no change (decision recorded in the PRD).

## Documentation effects

All of the above.

## Blocked by

- Tickets 01–04

## Completion record

(commit and notes)
