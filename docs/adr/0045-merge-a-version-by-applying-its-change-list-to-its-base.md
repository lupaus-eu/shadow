---
status: superseded
---

# Merge a version by applying its change list to its base

## Context

A Version could show its change list against the base, but the changes could not be taken back into the base.

## Decision

- Merging applies the change list to the base Version: removed connections and nodes are deleted, changed nodes take the new name, description, and type, and added nodes and connections are created.
- Afterwards added nodes in the Version point to their new base twins, so the Version shows no changes.
- Only an Owner or Admin may merge; the action is audited as `version.merged` and available as the MCP tool `merge_version`.
- Metrics are not merged.

## Consequences

- A node that the base lost after the fork returns to the base as a new node.
- Metric differences between a Version and its base stay as they are and need manual work.

Superseded by ADR-0050 (adoption of a Scenario replaces merge) together with ADR-0048 (events on lines replace versions); both landed with the model timeline, ticket 08.
