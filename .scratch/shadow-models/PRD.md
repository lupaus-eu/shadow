# Feature: Shadow models (digital twin of an organisation)

Status: implemented (written after the fact, 2026-11-07; the features were built in
eleven steps without separate PRDs, see "How this PRD relates to the code")

## Goal

An Organization can describe itself as a **model**: a graph of nodes (people, teams,
products, goals, systems and so on) and typed connections between them, with **metrics**
as monthly time series. It can fork **versions** of the model to explore a change, forecast
the metrics, run what-if **simulations**, and get an **analysis** with proposed actions.
The user's own AI agents work with the same models through MCP and can write their own
summary and proposals; Shadow calls no model itself (ADR-0047).

The value: a shared, explainable picture of the organisation over time, and a safe place
to try changes before making them.

## User

- **Member**: reads and edits models, versions, metrics, simulations and analyses; imports
  and exports metric values; accepts or dismisses proposals.
- **Owner and Admin**: everything a Member does, plus merging a version into its base,
  turning agent access on or off, and (Owner) billing and seats.
- **Agent (MCP client)** acting for a person: the same rights as that person, for the
  tools listed under "Agent tools".
- **Platform Admin and Support Agent**: no content access without approved Support Access;
  Support Access currently grants no model routes (see "Not in this version").

The platform base (sign-in, Organizations, roles, invitations, billing, audit) is described
in `.scratch/saas-platform/` and `.scratch/tenants-and-roles/` and is not repeated here.

## Use case

1. A Member creates a model. It starts with the default metamodel (11 node types, 9
   connection types) and a **baseline** version.
2. They draw the organisation on the canvas: nodes and connections the metamodel allows.
   They adjust the metamodel (types and rules) on the Types tab where the defaults do not fit.
3. They add metrics (entered or derived by formula), attach them to nodes, and fill monthly
   values by hand or import them from CSV or Excel.
4. They fork a version ("move the support team under sales"), change the graph and look at the
   change list against the base.
5. They run a simulation (method and horizon, optional what-if percentage changes per
   metric), look at history, forecast and bands, and compare it with a baseline run.
6. They open the analysis: findings and rule-based proposals, and any summary and proposals
   their agent has written. They accept or dismiss proposals and export the analysis.
7. An Owner or Admin merges a version that proved good into its base.
8. An agent does the same read and write steps through MCP.

## Acceptance criteria

### Models, graph and metamodel

- [ ] A Member can create, rename, describe and delete a model; a new model has the default
      metamodel and one baseline version.
- [ ] Nodes (name, description, type) and connections can be added, changed and removed in a
      version; deleting a node removes its connections.
- [ ] A connection is accepted only when the metamodel allows its connection type between the
      two node types; otherwise it is refused with a readable error.
- [ ] Node types and connection types can be created, renamed, recoloured and deleted; allowed
      connections can be added and removed. A type or rule still in use cannot be deleted
      (409 `in_use`); a duplicate name in the model is refused (409).
- [ ] Changes to the metamodel apply to every version of the model.
- [ ] Concurrent edits are not silently overwritten: a stale `expected_version` gives 409 with
      `latest_version`.
- [ ] Every write is audited; every table is row-level secured by Organization.

### Versions

- [ ] A version is forked from a base and holds its own complete graph and metrics.
- [ ] The change list against the base shows added, removed and changed nodes (name,
      description, type) and added and removed connections.
- [ ] Merge (Owner or Admin only) applies the change list to the base; afterwards the version
      shows no changes. Metrics are not merged. A Member's merge attempt gets 403.
- [ ] Every member can create and rename versions; only Owners and Admins delete them; the baseline cannot be deleted (422).

### Metrics

- [ ] A metric has a key (lower-case, unique in the version), a name, an optional unit and
      node, and either entered monthly values or a formula over other metric keys.
- [ ] Formulas are parsed safely (numbers, metric keys, parentheses and `+ - * / **`; no function calls; limited depth and size);
      unknown keys and cycles are rejected; derived metrics follow their inputs.
- [ ] Monthly values can be set for entered metrics and not for derived ones.
- [ ] Series are returned for both kinds, with derived values computed in dependency order.

### Import and export

- [ ] CSV (delimiter `;`, `,` or tab; decimal comma accepted) and XLSX files import in wide
      layout (one row per month, one column per metric) and long layout (`metric`, `period`,
      `value`).
- [ ] Unknown metrics, derived metrics and unreadable cells are reported and skipped; empty
      cells are ignored; the report says what was imported.
- [ ] Metrics export as CSV or XLSX; an analysis exports as an Excel workbook (Summary,
      Findings, Proposals, Forecast).
- [ ] Exported cells starting with `=`, `+`, `-` or `@` cannot run as formulas (prefixed `'`).

### Forecasts and simulations

- [ ] Methods: linear, seasonal (24+ months of history), Holt, and Prophet (12+ months). Too
      little history gives a clear error naming the method and the minimum.
- [ ] A simulation has a name, method, horizon of 1 to 60 months and optional adjustments
      (percentage change from −100 to +1000 per metric). It stores history, forecast and a
      95 % band per metric; derived metrics are recomputed from the adjusted inputs.
- [ ] Simulations can be listed, read and deleted.

### Analysis and proposals

- [ ] Rules give one finding per metric (start, end, change %, trend, month it turns
      negative, band width) and proposals of kinds `turns_negative`, `decline`, `growth`,
      `uncertain` and `scenario_gain`, each with severity and a rationale that names the
      numbers.
- [ ] Comparing with another simulation of the same model adds the difference to the findings.
- [ ] A proposal can be accepted or dismissed; the decision survives regenerating the analysis.
- [ ] A summary and one proposal per metric can be written by a person's agent through MCP; they are
      labelled "Agent" with the author, survive regenerating the rule proposals, and a repeated
      proposal for a metric replaces the earlier one (see `.scratch/agent-owned-ai/`).
- [ ] Shadow itself calls no LLM and holds no LLM key (a test guards it).

### Agent tools (MCP)

- [ ] Reads: `list_models`, `get_model`, `get_version_changes`, `list_metrics`,
      `get_metric_series`, `list_simulations`, `get_simulation`, `get_analysis`.
- [ ] Writes: `create_model`, `create_node`, `create_connection`, `create_version`,
      `create_metric`, `set_metric_values`, `run_simulation`, `generate_analysis`,
      `merge_version`, `set_analysis_summary`, `add_proposal`.
- [ ] Tools obey the same roles, read-only state, concurrency and audit as the web application;
      audit entries carry `source: "mcp"`. They stop when the Organization's MCP switch is off.
- [ ] Every tool call is recorded without content for Owners and Admins (Activity, Agent calls).

### Cross-cutting

- [ ] The interface exists in Finnish and English.
- [ ] A read-only Organization (ended subscription) can read and export but not write or import.
- [ ] Every user-visible error is readable; no raw server text reaches the page.

## Not in this version

- Merging metrics (values and formulas) with a version merge; metrics stay as they are.
- Per-version metamodels; types are shared by all versions of a model and not between models.
- Support Access to model content (the grant is recorded but opens no model route).
- Metamodel editing, import and export as agent tools; delete tools for agents.
- Events and scenarios on a timeline, user-defined forecast methods, automatic metric feeds
  from other systems, and real-time collaboration (conflicts are detected, not merged).
- Browser and accessibility tests of the new screens (tested by hand by the product owner).

## Domain terms

Defined in `CONTEXT.md`: **Model**, **Metamodel**, **Node**, **Connection**, **Version**,
**Baseline**, **Change list**, **Merge**, **Metric**, **Formula**, **Forecast**,
**Simulation**, **Analysis**, **Finding**, **Proposal**, **Agent**, **Agent call**, **Proposal source**, **Import**,
**Export**, **Agent tool**.

## Documentation effects

- [x] `docs/architecture/` — API, database, stack, C4 model (LikeC4) and DBML updated
- [x] `docs/adr/` — ADR-0042 to ADR-0047
- [x] `CONTEXT.md` — Shadow vocabulary
- [x] `.env.example` and `.env.production.example` — AI variables removed; `MCP_READ_LOG_RETENTION_DAYS` added
- [x] `docs/operations/` — agent call log note
- [ ] `docs/user/` — end-user guidance for models, versions, metrics, simulations and analysis
- [ ] `docs/admin/` — merging and agent access guidance
- [ ] `docs/legal/` — whether the privacy notice should say that agent calls are recorded per person
- [ ] `docs/design/` — UI guidance for the canvas, Types tab and analysis page
- [ ] `docs/end-user-tutorial/` — a Shadow testing tutorial replacing the Yearclock one

## Open questions

- Should a version merge carry metric values and formulas, and how are conflicts shown?
- Should agents be allowed to edit the metamodel, or is that a human-only action?
- Does Support Access need read access to models for support cases?
- Is a limit per Organization needed for models, nodes, metrics and simulations (none exists yet)?
- Is the Prophet image weight (and slow first fit) acceptable in production, or should it run
  in the worker?

## How this PRD relates to the code

Built in this order, each in its own commit: models and graph (62d1ac5, 798f56e), versions
(0ddabbd), metrics and formulas (3eac85a), forecasts and simulations (d842394), analysis and
proposals (168b57b), editable metamodel (1dd1207), MCP model tools (c0fccb6), Prophet
(d4e2e12), AI analysis (c98e914), version merge (e384faa), import and export (4553850).
The acceptance criteria above were written from the code and its tests (193 backend tests), not
checked off by a person; tick them while testing in the browser.
