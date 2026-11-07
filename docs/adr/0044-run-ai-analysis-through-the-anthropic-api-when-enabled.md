---
status: superseded
---

# Run AI analysis through the Anthropic API when enabled

## Context

Action proposals from rules are limited to patterns the code knows. An AI model can summarise a forecast and propose actions in plain language, but it needs the metric names and figures of the Organization.

## Decision

- Add an optional AI analysis that calls the Anthropic Messages API with `httpx` (no SDK). It is available only when `ANTHROPIC_API_KEY` is set; `SHADOW_AI_MODEL` selects the model.
- The call runs outside the database transaction (two short editor transactions around it), so no row locks are held while waiting for the model.
- The answer is parsed and validated: only the metric keys of the simulation are accepted, at most one AI proposal per metric is kept (`kind="ai"`), and the summary is stored on the simulation (migration 0057). Regenerating rule proposals leaves AI proposals alone, and accepted or dismissed decisions persist.
- The interface and the REST route say when the feature is unavailable (503). There is no MCP tool for it.

## Consequences

- When enabled, metric names and forecast figures leave the platform to Anthropic whenever someone presses the button. Sub-processor notices and the privacy text must name Anthropic before the feature is enabled in production.
- There is no per-Organization switch yet; enabling is a platform decision.
- Tests use a fake client; the real API has not been exercised without a key.

Superseded by ADR-0047: Shadow makes no LLM calls; agents write analysis through MCP.
