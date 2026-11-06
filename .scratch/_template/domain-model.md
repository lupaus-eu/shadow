# Domain model: <feature name>

Status: needs-triage

## Purpose and boundary

<Which business rule, lifecycle, or concept is clarified? What does this not decide?>

## Concepts

| Concept | Definition |
| --- | --- |
| **<Term>** | <Canonical meaning and boundary> |

## Aggregate and ownership

- <Which aggregate is changed, by whom, and in which state?>

## Lifecycle

```mermaid
stateDiagram-v2
  [*] --> <State>
```

## Business rules

1. <Rule, exception, and invariant to enforce>

## Authorization matrix

| Action | <Role> | Own resource |
| --- | --- | --- |
| <Action> | <Allowed/denied and state> | <Rule> |

## Consequences for specifications

- <Which PRD, technical-design, or ticket sections are clarified?>
- <Which durable documentation or ADR is evaluated during implementation?>
