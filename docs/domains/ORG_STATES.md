# Organisation States Domain

Status: core domain baseline

## Purpose

Organisation States Domain hallitsee skenaarioita, organisaatiotilan snapshotteja, tapahtumia ja skenaariokohtaisia aikasarjoja.

Domain kuvaa miten organisaation suunnittelu- tai analyysikonteksti versioidaan ajassa ilman, etta organisaation perustietoja tai graph-rakennetta omistetaan tassa domainissa.

---

# Responsibilities

Owns:

- scenarios
- organisation states
- events
- scenario-owned timeseries
- timeserie values

Provides:

- scenario versioning boundary
- named organisation state snapshots
- event timeline data
- scenario-level timeseries definitions and values

Does NOT Own:

- organisation records
- user records
- metamodel type definitions
- graph nodes or graph edges

---

# Domain Rules

## Scenario Boundary

Every scenario belongs to exactly one organisation.

## Organisation State Naming

Every organisation state has:

- stable `org_state_key`
- human-readable `name`
- `version`

The `name` is the display name for the snapshot and is required.

## Soft Delete Propagation

Scenario deletion is a soft delete in normal application flows.

When the application soft-deletes a scenario, it must also soft-delete owned organisation states, events, graphs, timeseries and timeserie values.

Physical database cascades are hard-delete cleanup/safety behavior only.

---

# Database Ownership

Tables:

- scenarios
- org_states
- events
- timeseries
- timeserie_values

Owned exclusively by Organisation States Domain.

Other domains may reference these tables but may not modify them directly unless a task explicitly defines a cross-domain service boundary.

---

# API Ownership

Endpoints:

```text
/scenarios
/org-states
/events
/timeseries
```

Exact HTTP operations and versioned paths are defined in backend implementation tasks.

---

# Dependencies

Depends On:

- Organisations Domain
- Users Domain for audit references

Referenced By:

- Organisation Twin Structure Domain

---

# Common Workflows

## Create Scenario

Flow:

1. Validate organisation exists and is active.
2. Create scenario.
3. Optionally link source scenario or initial organisation state when task scope allows it.
4. Return scenario data.

## Create Organisation State

Flow:

1. Validate scenario exists and is active.
2. Validate required `name`.
3. Create organisation state row.
4. Create related graph data only through Organisation Twin Structure behavior.

---

# AI Agent Guidance

When implementing scenario or organisation state features:

- read this document before changing scenario, org state, event or timeseries data
- preserve soft-delete behavior
- keep organisation state `name` required
- update data and diagram docs when fields or relationships change

Avoid:

- modifying organisation rows directly
- implementing metamodel copy behavior unless the task explicitly requires it
- treating physical cascade deletes as normal application deletion behavior

---

# Open Questions

- scenario lifecycle states beyond active and soft-deleted
- default scenario and organisation state creation flow
