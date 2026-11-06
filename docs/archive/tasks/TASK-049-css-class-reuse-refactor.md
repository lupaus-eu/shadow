# TASK-049 CSS Class Reuse Refactor

## Source Plan

Refactor the frontend CSS without intentional visual or behavioral changes,
apart from the two developer-approved follow-ups documented in this task:
consistent content-width date inputs and independent fork-source selection.
Rename layout classes whose names refer to one feature tab even though they are
used by several tabs, consolidate high-confidence shared styles, and remove
verified dead or duplicated CSS. Keep the work reviewable by leaving stylesheet
file moves and unrelated visual redesign out of scope.

The source audit found that Scenario-prefixed layout classes are currently used
by Customers, Events, Metrics, Structure, and Users. It also identified exact
or near-exact duplication in tab toolbars, dropdowns, disclosure buttons, field
stacks, metadata text, clamped descriptions, and panel surfaces.

## Goal

Make the frontend CSS easier to understand and maintain by ensuring shared
classes have neutral names based on their UI responsibility, not the feature
where they were first introduced. Reuse existing abstractions or introduce
small shared primitives where doing so removes meaningful duplication without
obscuring feature-specific behavior.

Preserve the current DOM semantics, interactions, responsive behavior, and
visual appearance across all workspace tabs, except for the explicitly approved
date-input styling and fork-source behavior corrections below.

## Requirements

- Keep the change scoped to `frontend/` and this task document.
- Do not add a dependency or introduce a CSS framework, CSS-in-JS library, CSS
  Modules, preprocessor, visual test framework, or new build step.
- Replace shared Scenario-named layout classes with neutral names. Use the
  following naming map unless an existing neutral project abstraction already
  provides the same responsibility:
  - `scenarios-tab` -> `management-tab`
  - `scenarios-toolbar` -> `tab-toolbar`
  - `scenarios-toolbar__title` -> `tab-toolbar__title`
  - `scenarios-toolbar__count` -> `tab-toolbar__count`
  - `scenario-control-grid` -> `main-detail-layout`
  - `scenario-side-panel` -> `main-detail-sidebar`
  - `scenario-side-section` -> `sidebar-section`
  - `scenario-side-section__header` -> `sidebar-section__header`
  - `scenario-workspace` -> `detail-workspace`
  - `scenario-detail-grid` -> `detail-grid`
  - `secondary__title` -> `secondary-title`
  - `state-delete-form` -> `destructive-action-section`
- Compose the Structure toolbar with the neutral `tab-toolbar` abstraction.
  Preserve any Structure-only or Summary-only layout differences with a
  feature-specific hook or neutral modifier rather than duplicating the shared
  toolbar declarations.
- Remove the replaced class names from both CSS and TSX. Do not retain temporary
  compatibility selectors after all call sites have been migrated.
- Consolidate these high-confidence reuse candidates when their computed styles
  can be preserved:
  - the common Organisation and context dropdown shell, trigger, panel,
    option, focus, and chevron styles
  - the common Structure and Summary disclosure/caret button styles
  - repeated field/list stacks with `display: grid` and the same gap
  - Predictions panels by composing the existing `detail-card` abstraction
    with a neutral spacing modifier while retaining Predictions-only hooks for
    genuinely feature-specific rules
  - the identical Metrics-grid and entity-row two-line description treatment
  - the identical Metrics-grid and timeserie metadata-code treatment
- Keep semantic classes separate when their matching declarations are only
  incidental. In particular, do not replace `eyebrow` with `form-label`, and do
  not generalize chart, timeline, event-status, or user-row modifiers merely to
  reduce declaration count.
- Remove CSS selectors verified as unused by both static and dynamic class-name
  searches:
  - `detail-description`
  - `panel-header`
  - `panel-actions`
  - `scenario-side-section__context`
  - `textarea--code`
- Combine fragmented declarations for the same selector when they occur in the
  same cascade context, including the base `metrics-toolbar__sort-select`
  declarations.
- Preserve dynamically constructed selectors such as Event status variants,
  Summary row-kind variants, and Summary tooltip alignment variants. A missing
  literal full class name is not sufficient evidence that a dynamic selector is
  unused.
- Preserve the current stylesheet import order unless a specific consolidation
  requires a small, behavior-preserving adjustment.
- Do not change React component boundaries or extract new React components as
  part of this CSS refactor.
- Apply the Predictions date-input styling to every date picker so each picker
  has consistent styling and a width that fits its content without overflowing
  its container.
- Keep the fork form's source scenario and source org state as draft form state.
  Selecting a source scenario must load that scenario's org states without
  changing the active workspace scenario or org state. Cancel stale source-state
  requests when the selection changes, and use the selected source values when
  submitting the fork.

## Acceptance Criteria

- [ ] Classes used by more than one feature tab have neutral, responsibility-
      based names rather than the name of the tab where they originated.
- [ ] Every class in the required naming map has been migrated in CSS and TSX,
      and none of the old names remains as a compatibility alias.
- [ ] Scenarios, Events, Users, Customers, Metrics, and Structure use the shared
      toolbar, main-detail, sidebar, and detail-layout styles where applicable.
- [ ] The approved dropdown, disclosure-button, field-stack, panel,
      clamped-description, and metadata-code reuse candidates no longer maintain
      duplicate base declarations.
- [ ] Feature-specific variants remain feature-specific where sharing would
      require misleading names or one-off overrides.
- [ ] The five verified unused selectors are removed.
- [ ] Dynamically constructed Event and Summary modifiers remain styled.
- [ ] Desktop and responsive layouts retain their existing appearance and
      behavior, including the current 1180, 900, 820, 760, 560, and 520 pixel
      breakpoints where applicable.
- [ ] Hover, focus-visible, disabled, selected, scrolling, sticky table,
      dropdown, disclosure, and destructive-confirmation states remain usable.
- [ ] Every date picker uses the shared Predictions-style date-input treatment,
      with content-fitting width and no container overflow.
- [ ] Selecting a source scenario in the fork form does not change the active
      workspace scenario or org state, loads source states for the draft source,
      and submits the selected source scenario and state.
- [ ] No new dependency is added and no backend code is changed.
- [ ] Frontend lint, tests, and build pass.

## Out Of Scope

- No product redesign, spacing refresh, typography change, color change, or new
  responsive behavior beyond the approved date-input sizing correction.
- No changes to user-facing copy, routing, authentication, authorization, API
  clients, or backend code. Data-loading and state-management changes are
  limited to the approved fork-source correction.
- No React component extraction or component API redesign.
- No broad split or relocation of `app.css` and `components.css`. A later task
  may move feature-owned styles after this semantic refactor is stable.
- No adoption of a class-name methodology, utility framework, or design-system
  dependency beyond the repository's existing CSS conventions.
- No architecture, ADR, domain, concept, data-model, database, migration,
  deployment, or diagram changes.

## Implementation Notes

Primary CSS files:

- `frontend/src/styles/app.css`
- `frontend/src/styles/components.css`
- `frontend/src/styles/tokens.css` only if an existing token must be reused; do
  not add or change visual token values for this task

Expected TSX call sites include:

- `frontend/src/features/scenarios/ScenariosTab.tsx`
- `frontend/src/features/events/EventsTab.tsx`
- `frontend/src/features/users/UsersTab.tsx`
- `frontend/src/features/customers/CustomersTab.tsx`
- `frontend/src/features/metrics/MetricsTab.tsx`
- `frontend/src/features/structure/GraphEditorToolbar.tsx`
- `frontend/src/features/structure/NodeList.tsx`
- Structure form and timeserie components that use the shared destructive-action
  styles
- shared dropdown components under `frontend/src/components/`
- `frontend/src/features/summary/SummaryTab.tsx` for shared disclosure styling
- `frontend/src/features/predictions/PredictionsTab.tsx` for panel composition

Prefer composition: a neutral base class should own declarations common to
multiple consumers, while a feature class or neutral modifier should contain
only the real difference. Avoid replacing a small duplicate with a generic
class that has only one consumer or requires several one-off overrides.

Before deleting a selector, search the complete frontend source for both the
full class name and any dynamic prefix. Summary and Event components construct
some modifier names in template strings.

The CSS refactor and date-input styling do not require new unit tests because
jsdom does not validate layout or computed visual rendering. The fork-source
correction does introduce application logic and requires a regression test that
verifies the active workspace selection remains unchanged while the chosen
source scenario and state are submitted. The complete existing frontend suite
and manual visual verification are still required.

Suggested branch:

```text
refactor/TASK-049-css-class-reuse-refactor
```

## Testing

Required:

- [ ] Frontend tests, including the fork-source behavior regression test
- [ ] Manual verification
- [ ] Lint
- [ ] Build

Manual verification must compare the before and after UI for:

- Scenarios, Events, Users, Customers, Metrics, Structure, Summary, and
  Predictions tabs
- Organisation, Scenario, and Org State dropdowns
- list selection, disabled rows, disclosure toggles, form controls, delete or
  revoke confirmations, alerts, and empty states
- wide desktop layout and the existing responsive boundaries at 1180, 900, 820,
  760, 560, and 520 pixels where relevant
- keyboard focus visibility and layouts with horizontal or vertical scrolling
- all date pickers use consistent styling and fit their displayed date content
  without stretching to fill their container
- changing the fork form's source scenario leaves the workspace scenario and
  org state unchanged and exposes the selected source scenario's states

Not applicable:

- [ ] Backend tests: backend code is not changed.
- [ ] Integration tests: no service boundary or runtime integration changes.
- [ ] New CSS-focused frontend unit tests: jsdom does not verify CSS layout.
- [ ] Dedicated frontend typecheck command: the repository has no separate
      script; `pnpm build` runs `tsc -b` before the Vite build.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Also verify that obsolete class names and dead selectors no longer occur:

```bash
rg -n "scenarios-tab|scenarios-toolbar|scenario-control-grid|scenario-side-panel|scenario-side-section|scenario-workspace|scenario-detail-grid|secondary__title|state-delete-form|detail-description|panel-header|panel-actions|textarea--code" frontend/src
```

The command should return no matches after implementation.

## Documentation

This task file is the persistent scope and naming record for the refactor and
the two developer-approved follow-ups. No architecture, ADR, domain, concept,
data, database, deployment, or diagram documentation changes are expected: the
date-input adjustment is presentational, and the fork-source correction restores
the form's intended behavior without changing system architecture or domain
rules.

If implementation reveals that another proposed shared abstraction would change
UI semantics or layout behavior, keep the feature-specific style and record the
reason in the final implementation summary rather than expanding the task.

## Notes For AI Agent

- Lue `AGENTS.md`, `docs/architecture/overview.md`, `docs/operations/testing.md` ja tämä task ennen
  toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Älä muuta käyttöliittymän tarkoituksellista ulkoasua tai toimintaa tämän
  taskin kahden hyväksytyn follow-up-korjauksen ulkopuolella.
- Älä poista dynaamisesti muodostettujen class name -varianttien CSS:ää pelkän
  literal-haun perusteella.
- Älä poista tai heikennä testejä.
- Kerro lopuksi mitä muutit, mitä tietoisesti jätit feature-kohtaiseksi ja miten
  tarkistit työn.
