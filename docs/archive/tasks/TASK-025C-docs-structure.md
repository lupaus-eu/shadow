# TASK-025C Documentation & Task Specs for Structure Feature

## Source Plan

Approved plan: "Structure-tab feature (Structure view)" — Phase C (Documentation & QA).

Update architecture and testing documentation, create QA checklists and task links for the Structure feature. Authorization is out of scope for this task and will be documented in a later task.

## Goal

Update project documentation to reflect the new Structure API and UI feature, provide clear acceptance criteria, testing procedures and a manual QA checklist so implementers and testers can verify feature completeness.

## Requirements

- Update `docs/architecture/overview.md` with org-twin-structure domain ownership, endpoint organization and component hierarchy
- Update `docs/operations/testing.md` with backend pytest and frontend Vitest commands for Structure feature
- Add a manual QA checklist covering graph, node and edge operations and position updates
- Create task links for [TASK-025A](TASK-025A-backend-structure-api.md), [TASK-025A2](TASK-025A2-add-type-metadata-support.md), [TASK-025A3](TASK-025A3-allowed-connection-metadata.md) and [TASK-025B](TASK-025B-frontend-structure-ui.md) and record acceptance criteria
- Document that authorization is handled in a future task (and list the todo/task id if available)

## Acceptance Criteria

- [ ] `docs/architecture/overview.md` updated with a new section describing the Structure API and frontend components
- [ ] `docs/operations/testing.md` updated with commands and guidance to run backend and frontend tests for the Structure feature
- [ ] QA checklist added with step-by-step verification scenarios
- [ ] TASK-025A and TASK-025B referenced and linked in the tasks directory
- [ ] Documentation reviewed for clarity and correct links

## Out Of Scope

- Implementing backend or frontend code (those are TASK-025A and TASK-025B)
- Implementing authorization or permission documentation beyond noting it will be handled in a follow-up task

## Implementation Notes

### Files to Modify / Create

- `docs/architecture/overview.md` — add "Org Twin Structure" section
- `docs/operations/testing.md` — add "Testing Structure Feature" instructions
- `docs/operations/qa/STRUCTURE-QA-CHECKLIST.md` — manual QA checklist for Structure feature
- `docs/architecture/domains/ORG_TWIN_STRUCTURE.md` — domain overview
- `docs/archive/tasks/TASK-025A-backend-structure-api.md` — ensure it is linked
- `docs/archive/tasks/TASK-025A2-add-type-metadata-support.md` — ensure it is linked
- `docs/archive/tasks/TASK-025A3-allowed-connection-metadata.md` — ensure it is linked
- `docs/archive/tasks/TASK-025B-frontend-structure-ui.md` — ensure it is linked

Related task specs:

- [TASK-025A Backend Structure API](TASK-025A-backend-structure-api.md)
- [TASK-025A2 Backend Structure API](TASK-025A2-add-type-metadata-support.md)
- [TASK-025A3 Backend Structure API](TASK-025A3-allowed-connection-metadata.md)
- [TASK-025B Frontend Structure UI](TASK-025B-frontend-structure-ui.md)

### Manual QA Checklist (summary)

- Open the Structure tab for an organisation state and verify the graph persists
- Add, edit and delete nodes and edges; verify persistence
- Drag nodes to new positions; verify optimistic UI and backend bulk update
- Verify node list grouping, filtering, zoom-to-fit and sidebar focus

Note: Authorization checks and testing are explicitly out of scope for this documentation task and will be added in a dedicated follow-up task.

## Notes For AI Agent

- This is documentation-only work. Do not implement feature code here.
- Ensure all added links point to existing files.
- Keep QA checklist actionable and concise.
