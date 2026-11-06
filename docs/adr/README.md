# Architecture Decision Records

Create one Markdown file per durable architecture decision, numbered in
sequence:

```text
NNNN-short-imperative-title.md
```

Each ADR starts with YAML front matter and a title:

```markdown
---
status: accepted
---

# Use PostgreSQL with service-level isolation
```

Allowed statuses:

- `proposed` — under discussion
- `accepted` — in force
- `deferred` — accepted in principle but outside the current release
- `superseded` — replaced; name the replacing ADR in the body

The body states the decision and its reasoning in one or a few short
paragraphs. Cover the context that forced the decision and its main
consequences or trade-offs. When a later ADR refines or replaces an earlier
one, add a closing line to both that names the other.
