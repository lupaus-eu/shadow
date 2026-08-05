# TASK-036C Customer Tab UI

Status: Planned

## Source Plan

Approved plan: add a complete frontend Customers workspace tab after
TASK-036A has defined the Customer Domain schema and TASK-036B has implemented
the customer, contact and address API contracts.

The tab is reached through an organisation workspace for compatibility with the
current navigation shell, but Customer Domain records are application-wide.
The workspace `orgId` is navigation context only and must not be sent to any
Customer Domain API request.

## Goal

Implement a frontend Customers tab that lets an operator search and manage
active and archived customer profiles together with each customer's contacts
and addresses.

The UI must preserve backend lifecycle and ownership rules, provide resilient
request-state handling, and reuse the existing workspace management patterns
without adding a dependency.

## Requirements

- Depend on the completed TASK-036B backend API contract.
- Add a `customers` workspace tab signature and label it `Customers`.
- Place Customers immediately before Users in the existing workspace tab bar.
- Route the tab at `/schatten/:orgId/customers` and derive its active state from
  the URL.
- Keep Customers enabled without a selected scenario or organisation state.
- Treat customers, contacts and addresses as application-wide even though the
  tab is rendered inside the organisation workspace.
- Do not include workspace `orgId`, scenario id or organisation-state id in any
  Customer Domain API path or payload.
- Add a typed frontend Customer Domain API client covering:
  - customer list/search/filter, get, create, PUT and DELETE
  - nested contact list, create, PUT and DELETE
  - nested address list, create, PUT and DELETE
- Model the API response contracts from TASK-036B, including camelCase
  timestamp and address/contact fields.
- Follow existing frontend API conventions for `VITE_API_BASE_URL`, JSON
  requests, `AbortSignal`, FastAPI error payloads and actionable error messages.
- Add a dedicated `CustomersTab` feature component.
- Show a toolbar with page title, non-deleted customer count and Refresh action.
- Provide customer search over name/email and an active/archived status filter.
- Keep customer ordering deterministic and case-insensitive by name with id as
  the tie-breaker, even if the backend already returns sorted data.
- Show customers in an accessible selectable list with name, optional email and
  status badge.
- Automatically select the first customer after loading when no preserved
  selection is available.
- Preserve the selected customer after refresh or update while it remains in
  the current result set.
- Fall back predictably to the first remaining customer when selection
  disappears because of filtering, search, refresh or deletion.
- Provide a create-customer form with required name and optional email.
- New customers are active; do not offer a create-time status selector.
- Provide a selected-customer profile form for name, email and active/archived
  status.
- Support archiving and reactivating through customer PUT.
- Keep archived customers and their contacts and addresses visible and
  editable.
- Require explicit confirmation before customer deletion and explain that its
  contacts and addresses will also be removed from normal views.
- Treat customer DELETE as soft deletion; do not provide restore or permanent
  deletion UI.
- When selection changes, load the selected customer's contacts and addresses
  in parallel.
- Cancel or ignore stale customer, contact and address list requests during
  unmount, route changes, selection changes and overlapping refreshes.
- Clear child UI state immediately when no customer is selected or the selected
  customer is deleted.
- Provide a Contacts section that supports:
  - explicit loading, empty, error and retry states
  - selectable contact list ordered by name and id
  - create with name, email, phone and job title
  - edit of all contact fields
  - confirmed soft deletion
  - selection preservation and deterministic fallback
- Provide an Addresses section that supports:
  - explicit loading, empty, error and retry states
  - selectable address list ordered by label and id
  - create and edit for label, address lines, postal code, city, region and
    country code
  - confirmed soft deletion
  - selection preservation and deterministic fallback
- Trim required and optional text before submission. Reject blank required
  fields before making an API request and convert blank optional fields to
  `null`.
- Use email inputs and normalize country codes to uppercase for user experience,
  while retaining the backend as the trusted validation boundary.
- Reconcile successful mutations into local state so results remain visible
  without requiring an immediate list reload.
- Show explicit customer-list, customer-mutation, contact and address errors
  with retry paths where a load can be retried.
- Show saving/deleting progress and prevent duplicate or conflicting mutations.
  Use separate request state where safe so an unrelated child panel does not
  unnecessarily lose its visible data.
- Use semantic headings, labelled fields, keyboard-accessible controls,
  accessible selected state, `role="alert"` for errors and accessible delete
  confirmation dialogs.
- Reuse existing design tokens, forms, entity-list and management-view
  patterns. Add only scoped or reusable styles needed for Customer Domain UI.
- Keep the layout usable at the responsive widths supported by the workspace
  shell.
- Do not add a frontend dependency.

## Acceptance Criteria

- [ ] Customers appears immediately before Users in the workspace tab bar and
      links to `/schatten/:orgId/customers`.
- [ ] The active Customers tab is derived from the URL and remains enabled
      without scenario or organisation-state selection.
- [ ] Customer Domain API requests never include the workspace `orgId`.
- [ ] The tab renders customer loading, empty, error, retry and refresh states.
- [ ] Search and status filtering work and selection fallback is predictable.
- [ ] Customer ordering is case-insensitive and deterministic.
- [ ] An operator can create a trimmed, valid active customer.
- [ ] An operator can edit name and email, archive a customer and reactivate an
      archived customer.
- [ ] Archived customers and their children remain visible and editable.
- [ ] Customer deletion requires confirmation, removes the customer and child
      state from normal UI, and selects a predictable fallback.
- [ ] The selected customer's contacts and addresses load in parallel.
- [ ] Switching customers cannot allow stale contact or address results to
      overwrite the current selection.
- [ ] Contact loading, selection, create, edit and confirmed-delete flows work.
- [ ] Address loading, selection, create, edit and confirmed-delete flows work.
- [ ] Blank required values are rejected before mutation and optional blank
      values are submitted as `null`.
- [ ] Mutation progress and failures are visible and duplicate submissions are
      prevented.
- [ ] Successful mutations remain visible without a mandatory list reload.
- [ ] Customer, contact and address controls are accessible by keyboard with
      meaningful labels, states and error announcements.
- [ ] The layout remains usable at supported responsive widths.
- [ ] No authentication, authorization, organisation ownership, restore or
      permanent-delete behavior is introduced.
- [ ] Frontend API, component, routing and integration tests pass.
- [ ] Frontend lint and build pass.
- [ ] The TASK-036B backend Customer Domain contract tests continue to pass.

## Out Of Scope

- Backend implementation or schema changes except a separately approved defect
  correction.
- Customer merge, restore or permanent deletion.
- Restoring individual contacts or addresses.
- Organisation-specific customers or passing `orgId` to Customer Domain APIs.
- Authentication, authorization, role-based UI or Entra ID integration.
- Billing, Document or AI Domain workflows.
- Shared AuditEvent behavior.
- Pagination, virtualized lists, fuzzy search or advanced address lookup.
- Country selector reference data, geocoding or address autocomplete.
- New frontend dependencies.
- A separate global administration shell or top-level `/customers` route.

## Implementation Notes

- Read `AGENTS.md`, `ARCHITECTURE.md`,
  `docs/decisions/ADR-001-tech-stack.md`,
  `tasks/TASK-036B-customer-backend-api.md`,
  `docs/concepts/CUSTOMER.md`, `docs/domains/CUSTOMER.md`,
  `docs/TESTING.md` and this task before implementation.
- Expected frontend areas include:
  - `frontend/src/workspace/workspaceTabs.ts`
  - `frontend/src/pages/Workspace.tsx`
  - `frontend/src/App.test.tsx`
  - `frontend/src/api/customers.ts`
  - `frontend/src/api/customers.test.ts`
  - `frontend/src/features/customers/CustomersTab.tsx`
  - `frontend/src/features/customers/CustomersTab.test.tsx`
  - relevant shared styles and test API mocks
- The Users tab is the nearest existing application-wide management pattern,
  but the Customer tab has additional independent contact/address request and
  selection state. Reuse patterns without coupling the domains.
- Prefer request-controller or generation-token handling that prevents older
  customer or child responses from replacing newer results.
- A customer change should abort or invalidate child requests associated with
  the previously selected customer.
- Keep frontend validation focused on user experience. The backend remains the
  trusted validation, ownership and lifecycle boundary.
- `PUT` is part of the approved Customer Domain contract; the client and tests
  must use it rather than `PATCH`.
- No ADR is expected because this task uses the existing frontend and workspace
  architecture.

## Testing

Required:

- [ ] Frontend Customer Domain API client tests
- [ ] Frontend Customers tab component/integration tests
- [ ] Workspace routing and navigation tests
- [ ] Backend contract regression verification
- [ ] Manual browser verification
- [ ] Frontend lint
- [ ] Frontend build and TypeScript checking

Not applicable:

- [ ] Database migration tests: TASK-036A owns schema verification.
- [ ] New backend tests: TASK-036B owns backend implementation; add a backend
      regression test only for a separately approved defect correction.
- [ ] Broad end-to-end browser automation: focused component/integration tests
      plus manual QA are proportionate for this management UI.

Frontend automated coverage must include:

- Customers route, tab link, ordering and active state
- availability without scenario or organisation-state selection
- absence of workspace `orgId` from every Customer Domain API request
- customer loading, empty, error, retry, refresh, search and status filtering
- customer sorting, initial selection, preservation and fallback
- customer creation and client-side required-field validation
- customer edit, archive and reactivate operations using PUT
- customer delete cancellation, confirmation and child-state clearing
- parallel contact/address loading
- child loading failure and independent retry behavior
- contact sorting, selection, create, edit and delete
- address sorting, selection, create, edit and delete
- optional blank-to-null request normalization and country-code normalization
- successful mutation reconciliation without forced reload
- mutation failures and duplicate-submission prevention
- request abortion on unmount and customer selection change
- stale customer/contact/address response protection
- accessible selected states, errors and delete confirmations
- exact HTTP methods, encoded paths, query parameters and request payloads

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build

cd ../backend
uv run pytest
```

Manual verification must cover:

- opening Customers directly by URL and through the tab bar
- using Customers without selecting a scenario or organisation state
- customer loading, refresh, search and active/archived filtering
- customer create, edit, archive, reactivate and confirmed delete
- contact create, edit and confirmed delete
- address create, edit and confirmed delete
- switching customers while child data is loading
- customer deletion with populated contacts and addresses
- API validation and server-error presentation
- keyboard navigation, focus behavior and responsive layout

## Documentation

- Update `ARCHITECTURE.md` to record the implemented frontend Customer tab,
  its application-wide boundary and its relationship to the Customer backend.
- Update `docs/TESTING.md` only if permanent Customer-tab verification guidance
  adds value beyond this task.
- Update `docs/concepts/CUSTOMER.md` or `docs/domains/CUSTOMER.md` only when the
  implementation reveals a clarification that does not change the approved
  concept or domain contract.
- Do not change data-model documentation, migrations or diagrams unless a
  separately approved backend/schema correction is required.

## Notes For AI Agent

- Toteuta vain tassa taskissa maaritelty scope.
- Ala muuta backend- tai tietokantasopimusta ilman ihmisen paatosta.
- Ala laheta workspace-organisaation tunnistetta Customer Domain APIin.
- Ala lisaa uusia riippuvuuksia ilman hyvaksyntaa.
- Sailyta stale request -suojaus kaikissa customer-, contact- ja address-listoissa.
- Lisaa testit muutoksen riskin mukaan ja raportoi kaikki ajetut tarkistukset.
- Kerro lopuksi mita muutit ja miten tarkistit tyon.
