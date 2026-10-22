# TASK-069A AI Via MCP Architecture And Contracts

## Source Plan

Approved plan: "AI chat via MCP for generating Schatten model and timeseries
data". It was accepted for task creation in the conversation on 2026-10-21
under Step 3 of `docs/AI-DEVELOPMENT-WORKFLOW.md`.

This task is the architecture prerequisite for TASK-069B through TASK-069O.
Creating these files specifies future work; it does not implement the tasks.

Requirements and developer decisions (2026-10-21):

- AI must use Schatten through an MCP interface.
- MCP access uses the same people, roles and authentication as the rest of
  Schatten.
- The MCP services are split into a read service and a write service.
- Users run the AI on their own AI subscription. The chat happens in their own
  MCP-capable client, such as Claude Desktop, claude.ai or Claude Code.
  Schatten never calls an LLM and never stores LLM keys, so the design is
  provider-neutral.
- The write service only stages change sets. A human reviews each change set
  and applies or rejects it in the Metrics tab. No MCP tool can apply changes.
- No background worker is added and the prediction worker is not extended.
  All MCP work is short and synchronous.
- The architecture is documented as a C4 model in LikeC4. It includes a
  deployment view of how MCP is used.
- Delivery is phased through TASK-069B to TASK-069O.

## Goal

Document the accepted architecture and contracts before any implementation.
This covers the MCP read and write services, Schatten as an OAuth 2.1
authorization server for MCP clients that reuses the existing Entra login, AI
change sets with human approval, the deterministic timeseries generator,
skills, and how the feature is protected on a resource-limited host.

## Requirements

- Create `docs/decisions/ADR-015-ai-via-mcp.md` from the approved plan. It must
  record the following decisions.
  - **Two FastMCP Streamable HTTP services in the existing FastAPI app.**
    - `/api/mcp/read` requires scope `schatten.read`.
    - `/api/mcp/write` requires scope `schatten.write`.
    - Both run stateless with JSON responses.
    - Neither has an apply tool.
    - Record the developer's approval of the new `fastmcp` dependency and of
      a direct `numpy` declaration (both confirmed on 2026-10-22). The
      fallback is the official `mcp` SDK's bundled FastMCP.
  - **Schatten as its own OAuth 2.1 authorization server.**
    - Endpoints:
      - `/.well-known/oauth-authorization-server`;
      - `/.well-known/oauth-protected-resource/api/mcp/{read,write}`;
      - `/api/oauth/{register,authorize,token,revoke}`.
    - Dynamic Client Registration is limited by a redirect URI allowlist.
    - PKCE S256 is mandatory.
    - Opaque tokens are stored as SHA-256 hashes, and refresh tokens rotate.
    - Reusing an already-rotated refresh token revokes the whole grant.
    - Authorization reuses the existing SPA login, Entra and `return_to` flow,
      followed by a consent page. Approval is sent as a CSRF-protected POST.
    - The Entra registration does not change.
    - Explain why FastMCP's OAuthProxy/AzureProvider was rejected: it changes
      ADR-013, duplicates user linking, stores upstream tokens, and makes
      revocation and per-request role re-reads awkward.
    - Record Client ID Metadata Documents as future work.
  - **Authorization on every MCP request.**
    - Hash the token, load it, check the grant is not revoked, and load a User
      that is not deleted. This re-reads the role.
    - Effective scopes are the grant's scopes intersected with the scopes
      allowed for the user's role.
    - Both current roles get both scopes, matching today's business access.
  - **AI change sets.**
    - Operations are typed and can refer to each other with `$ref` (only for
      server-generated keys; client-supplied keys are used verbatim).
    - Lifecycle: `draft -> submitted -> applied | rejected | failed`, and
      `draft -> discarded`.
    - Dry-run runs the operations and always rolls back.
    - Apply runs atomically in a single transaction through the existing
      domain services.
    - Humans review and apply through cookie-session plus CSRF endpoints, and
      both roles may review.
    - Generated values are frozen at submit time.
  - **Deterministic, spec-based timeseries generator (numpy).** The LLM chooses
    the parameters and never emits the values itself.
  - **Skills.** Repository-owned `SKILL.md` files, distributed as a Claude Code
    plugin, a marketplace and skill zips, and also served as MCP prompts.
  - **Background execution.** None. Reference ADR-012's single-worker rule.
    List the resource protections:
    - a concurrency limiter for MCP tools;
    - per-grant rate limiting;
    - a statement timeout;
    - operation and value limits;
    - lazy cleanup of expired OAuth rows.
  - **Data leaving Schatten.** Business data read through MCP flows to the
    user's AI vendor. Record this product and security decision.
  - **Diagram tooling.** LikeC4 is the accepted tool for the C4 model of this
    feature. Existing PlantUML diagrams remain as they are.
- Rewrite the placeholder `docs/domains/AI.md` as the AI domain. It owns
  `mcp_oauth_*` and `ai_change_sets*` and their rules. Change sets call other
  domains' services and never write their tables directly. The existing
  document-classification candidate content and
  `docs/concepts/AI_EXTRACTION.md` must not be silently deleted. Mark them as
  unplanned candidates outside this feature's scope.
- Add `docs/concepts/AI_CHANGE_SET.md` covering fields, invariants, lifecycle
  and operation types. Update `docs/concepts/CONCEPTS.md`.
- Update `docs/domains/DOMAIN.md` with ownership and dependencies, and update
  `docs/data/DATA-MODEL.md` with the logical model of the planned tables.
- Add the LikeC4 model under `docs/diagrams/likec4/schatten-ai-mcp/`, in the
  files `specification.c4`, `model.c4`, `deployment.c4` and `views.c4`.
  - Required views:
    - `index` (C4 L1);
    - `schattenContainers` (L2);
    - `backendComponents` (L3);
    - `productionMcp` (deployment);
    - `developmentMcp` (deployment);
    - `connectFlow` (dynamic);
    - `generateFlow` (dynamic).
  - The production deployment shows:
    - the user workstation, with a browser and AI client apps;
    - the AI vendor cloud, with LLM inference and the remote connector broker;
    - Microsoft Entra;
    - the UpCloud host, with the `frontend`/Caddy, `backend`,
      `prediction-worker` and `database` containers.
  - The development deployment shows `https://app.localhost` and notes that
    vendor-cloud connectors cannot reach localhost.
  - Elements are tagged `#new` or `#existing`.
- Export every view to `docs/diagrams/generated/likec4-<view>.png`. Add
  `docs/diagrams/likec4/README.md` with the pinned commands. Update
  `docs/diagrams/README.md` to admit LikeC4 for this feature's C4 model.
- Link the views from ADR-015, `docs/domains/AI.md` and `ARCHITECTURE.md`.
- Update `ARCHITECTURE.md` and `AGENTS.md`. Mark the feature as an accepted
  design whose implementation is pending TASK-069B through TASK-069O.

## Acceptance Criteria

- [ ] ADR-015 records every decision above. It references ADR-004, ADR-012 and
      ADR-013 without weakening them.
- [ ] The documentation clearly states that no MCP tool applies changes and
      that a human apply in Schatten is required.
- [ ] The AI domain, change-set concept and data model documents agree with
      ADR-015.
- [ ] `likec4@1.60.0 validate` passes. All seven views render and their PNG
      exports are committed.
- [ ] The documentation distinguishes the accepted design from implemented
      runtime behaviour.
- [ ] No application code, migration, dependency, Compose service or Caddyfile
      is changed.

## Out Of Scope

- Any implementation of TASK-069B through TASK-069O.
- Production actions or changes to the Entra registration.
- An in-app LLM chat, storing LLM API keys, or Schatten calling an LLM.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-004-authentication.md
docs/decisions/ADR-012-background-prediction-requests.md
docs/decisions/ADR-013-shared-entra-local-https-deployment.md
docs/domains/AI.md
docs/domains/ORG_STATES.md
docs/domains/ORG_TWIN_STRUCTURE.md
docs/diagrams/README.md
tasks/TASK-069B-*.md ... tasks/TASK-069O-*.md
```

- LikeC4 runs through `npx` pinned to `likec4@1.60.0`. No project dependency is
  added. Install the browser and export the PNGs with the procedure in
  `docs/diagrams/likec4/README.md`. It installs the Playwright browser bundled
  with LikeC4, exports to a temporary directory and copies each view to
  `docs/diagrams/generated/likec4-<view>.png`.
- Keep the docs in the repository's existing Finnish/English style.

## Testing

Required: documentation consistency and local-link checks, LikeC4 validation,
and visual inspection of every exported view.

Not applicable: application tests, lint, typecheck and builds, because this
task changes documentation only.

```bash
npx -y likec4@1.60.0 validate docs/diagrams/likec4/schatten-ai-mcp
# PNG export: follow the "Commands" section of docs/diagrams/likec4/README.md
npx -y likec4@1.60.0 start docs/diagrams/likec4/schatten-ai-mcp
python3 scripts/ai_review_records.py validate
```

## Documentation

Create ADR-015, `docs/domains/AI.md` (rewrite), `docs/concepts/AI_CHANGE_SET.md`
and the LikeC4 sources and exports. Update `ARCHITECTURE.md`, `AGENTS.md`,
`docs/domains/DOMAIN.md`, `docs/concepts/CONCEPTS.md`,
`docs/data/DATA-MODEL.md` and `docs/diagrams/README.md`.

## Notes For AI Agent

- Branch: `docs/TASK-069A-ai-mcp-architecture`.
- Implement only this documentation task when separately requested.
- Do not add dependencies or implement another TASK-069 task.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069A/`.
- Report all changed files and the checks you ran.
