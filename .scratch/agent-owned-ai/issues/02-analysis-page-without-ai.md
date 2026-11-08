# Ticket 02: Analysis page without AI

Status: resolved

## Goal

The analysis page shows the rule-based analysis and any summary and proposals an agent has written, with no AI button.

## Implementation

- `AnalysisPage.tsx`: remove the "Analyse with AI" button, the AI badge, note and failure text, and `ai_available` use; show `summary` with author and time; show an "Agent" badge on proposals with source `agent`; keep accept and dismiss; add the hint to ask a connected agent, linking to the agent page when the person is an Owner or Admin.
- `client.ts`: remove `generateAiAnalysis`; update the analysis type.
- `messages.ts`: remove the AI messages; add summary, agent badge and hint texts in Finnish and English.
- Render agent text as plain text only.

## Acceptance criteria

- [ ] No AI button, badge or text remains anywhere in `frontend/src`.
- [ ] A summary written through the API shows with author and time; an `agent` proposal shows the Agent badge and can be accepted and dismissed.
- [ ] The hint links to the agent page only for Owners and Admins.
- [ ] Finnish and English texts match (parity test).

## Testing

- [ ] Frontend — `tsc`, `npm run build`, `npm run test:unit`
- [ ] Browser — by the product owner (changed workflow)
- [ ] Backend — not applicable

## Ajetut tarkistukset

- `npm --prefix frontend run typecheck` — clean.
- `npm --prefix frontend run build` — built.
- `npm --prefix frontend run test:unit` — 23 passed.
- grep for `askAi`, `aiBadge`, `ai_`, "with AI", "tekoäl" in `frontend/src` and `frontend/tests` — no matches.
- Not run: browser test of the page (the product owner tests the UI). The summary renders as plain text; the hint links to `/organizations/:id/admin/agents` only for Owner and Admin.

## Documentation effects

- [ ] `docs/design/` — evaluated (no durable change expected)
- [ ] `docs/user/` — ticket 05

## Blocked by

- Ticket 01

## Completion record

(commit and notes)
