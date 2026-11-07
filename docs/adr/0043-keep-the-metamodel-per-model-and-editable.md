---
status: accepted
---

# Keep the metamodel per model and make it editable

## Context

Node types, connection types, and allowed connections came from one fixed default metamodel that tenants could not change. Organizations model different things and need their own types.

## Decision

- Each Model owns its metamodel, seeded from `backend/app/default_metamodel.json` when the Model is created.
- Editors of a Model can create, rename, recolour, and delete node types and connection types, and add or remove allowed connections.
- A type or rule that nodes or connections still use cannot be deleted (409 `in_use`); duplicate names inside a Model are refused (409).
- All Versions of a Model share its metamodel, because a Version is a copy of the graph, not of the rules.

## Consequences

- Changing a type affects every Version of the Model at once.
- Types are not shared between Models; copying types between Models is not supported.
