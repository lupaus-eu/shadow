# Feature: All AI use happens in the user's own agent

Status: implemented

## Goal

Shadow itself never calls a large language model. Every use of an LLM, and every
token it costs, happens in the user's own agent harness under the user's own
subscription. Shadow offers read and write tools through its MCP interface,
records everything agents do through it, and leaves the use of the agent, its
cost and its conclusions to the person who connected it.

This removes the one place where Shadow sent Organization data to a model
provider on its own initiative (the "Analyse with AI" button, ADR-0044) and
settles the questions that came with it: an API key to hold, a bill to bear, a
sub-processor to name, and a consent switch to build.

## User

- **Member, Owner, Admin**: no longer see an AI button; read the rule-based
  analysis in the interface and connect their own agent for anything more.
- **Owner and Admin**: decide whether agents may reach the Organization (the
  existing MCP switch) and can read what agents did in the Activity page.
- **Agent acting for a person**: reads and writes through MCP with that person's
  rights, including writing its own analysis summary and action proposals. It has
  no identity or rights of its own: every call is the connecting person's call,
  made through a named agent program (the MCP client).
- **Platform Admin**: no AI key or model setting exists to operate any more.

## Use case

1. A person connects their own agent (for example Claude with a custom
   connector) to Shadow, as today.
2. They ask the agent to analyse a simulation. The agent reads the model, the
   metrics, the simulation and the rule-based analysis through MCP tools.
3. The agent writes a summary and action proposals back through MCP tools.
4. The person (and their colleagues) see the agent's summary and proposals on
   the analysis page, labelled as written by an agent, and accept or dismiss
   the proposals as before.
5. An Owner or Admin opens Activity, filters on agent calls and sees every call
   the agent made, including the ones that only read, and for whom it acted.

## Acceptance criteria

### Nothing inside Shadow calls an LLM

- [ ] The backend has no LLM client, no LLM API key setting and no model setting
      (`ANTHROPIC_API_KEY` and `SHADOW_AI_MODEL` are gone from the code, both
      `.env` examples and both Compose files).
- [ ] No route, worker job or MCP tool sends Organization data to a model
      provider. A test fails if the backend imports an LLM SDK or names a model
      provider host.
- [ ] The analysis page has no "Analyse with AI" button, no AI badge and no
      AI-failure text; the endpoint `POST .../analysis/ai` no longer exists
      (404).
- [ ] The rule-based analysis, forecasts (including Prophet, which is
      statistics, not an LLM) and exports keep working unchanged.

### Agents can write analysis through MCP

- [ ] An MCP tool sets the analysis summary of a simulation, and another adds a
      proposal to it. Both go through the same endpoint functions as the web
      application (ADR-0046) and are limited to Members and above, and blocked
      while the Organization is read-only.
- [ ] Agent-written proposals have the source `agent`, show a label "Agent" on
      the analysis page, can be accepted or dismissed, and survive regenerating
      the rule-based proposals.
- [ ] The summary shows who wrote it and when ("by an agent" or the person), and
      the Excel export includes it.
- [ ] Proposals that already exist from the removed AI analysis are deleted by
      the migration; the migration is reversible in structure.

### Everything agents do is logged

- [ ] Every MCP tool call produces a record (table `mcp_calls`, see the technical design): reads, writes, refused calls
      (role, read-only, switch off, blocked) and failures. It records the tool,
      the Organization, the acting person, the client, the outcome and the
      duration, never the content that was read or written.
- [ ] Every entry names the person the agent acted for and the agent program
      (client); an entry without both is a defect.
- [ ] Writes keep their specific audit events (for example `metric.values_set`)
      and still carry `source: "mcp"` and the client id.
- [ ] Only Owners and Admins can see agent calls, in Activity behind an "Agent
      calls" filter; the default Activity view does not list read calls.
- [ ] Read calls are logged lightly: if writing a read call's entry fails, the
      read still succeeds and the failure goes to the system log. A write call
      whose entry cannot be written fails.
- [ ] Entries of read calls are deleted after 90 days
      (`MCP_READ_LOG_RETENTION_DAYS`); write calls and refusals follow the normal
      audit retention.

### Responsibility is stated

- [ ] The Owner and Admin page for connecting an agent says that the agent, its
      provider, its token cost and what it does with the data it reads belong
      to the person who connects it, and that Shadow logs agent calls.
- [ ] Admin and user documentation say the same. The privacy notice and the
      sub-processors page already name the agent's provider as the person's own
      choice; they are re-read and left alone or corrected.

## Not in this version

- Any Shadow-hosted model, prompt, agent or scheduled AI task.
- Per-agent quotas, rate limits or cost reporting; cost is the user's.
- Reading what was said in the agent conversation; Shadow stores no
  conversations.
- A change to the terms of service. Whether the terms need a clause about
  agent use is a human and legal decision (see open questions).
- Removing or changing Prophet or the other forecast methods.

## Domain terms

- **Agent**: software acting for a person through MCP under that person's own
  account and rights; it is not part of Shadow. (Replaces the term *AI
  Analysis* in `CONTEXT.md`.)
- **Agent call**: one MCP tool call, successful or refused, made by an agent
  program on behalf of a named person and recorded in the Audit Log without
  content.
- **Proposal source**: `rule` (generated from the forecast rules) or `agent`
  (written through MCP).

## Documentation effects

- [x] `docs/adr/` — ADR-0047 "Make no LLM calls from the system" supersedes ADR-0044; ADR-0044 gets a closing line.
- [x] `docs/architecture/` — `api.md`, `database.md`, `stack.md`, C4 (remove Anthropic, remove the `aiAnalysis` flow, add the agent analysis flow), DBML regenerated.
- [x] `docs/operations/README.md` — remove the AI analysis section.
- [x] `docs/admin/` — agent responsibility and reading agent calls in Activity.
- [x] `docs/user/` — how to ask an agent to analyse a simulation.
- [x] `docs/gdpr/` and `docs/legal/` — re-read; no sub-processor is added; terms decision recorded. The legal texts were left to counsel: whether the privacy notice should mention the per-person agent call record is open.
- [x] `CONTEXT.md` — replace *AI Analysis* with *Agent*, *Agent call*, *Proposal source*.
- [x] `.env.example`, `.env.production.example`, both Compose files — remove the AI variables; add `MCP_READ_LOG_RETENTION_DAYS` (default 90).
- [x] `.scratch/shadow-models/PRD.md` — update the analysis, agent-tool and open-question sections.

## Open questions

- Does the terms of service need a sentence on agent use and responsibility?
  Recommendation: not now; the privacy notice and the connect page say it, and
  changing the terms means re-acceptance by every Owner. (Taken as the default
  unless a human decides otherwise.)

## Decisions (2026-11-07)

- Terms of service: no change for now (recommendation taken).
- Who sees agent calls: Owners and Admins only (decided by the product owner).
- Reads are logged lightly: one content-free entry per call, behind a filter,
  fail-open, 90 days (decided by the product owner).
