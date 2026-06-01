# AI Extraction Concept

Status: initial candidate concept

## Purpose

AI Extraction tarkoittaa AI:n tuottamaa rakenteista poimintaa lähdedatasta.

AI Extraction ei ole automaattisesti totuusdataa. Se on johdettu tulos, joka voi vaatia hyväksynnän.

---

# Owner

Owning Domain:

- AI Domain

Related Domain Document:

- `docs/domains/AI.md`

---

# Definition

```text
An AI Extraction is a structured output generated from a source document or other source data by an AI process.
```

---

# Key Fields

- id
- source_type
- source_id
- model
- prompt_version
- output
- confidence
- status
- created_at

---

# Invariants

- AI Extraction must reference its source data.
- AI Extraction must store model or processing metadata.
- AI Extraction must not overwrite source data directly.

---

# Lifecycle

States:

- pending
- completed
- failed
- reviewed
- rejected

Transitions:

```text
pending -> completed
pending -> failed
completed -> reviewed
completed -> rejected
```

---

# Relationships

Related Concepts:

- Document
- Customer

Related Tables:

- ai_extractions

Related APIs:

- `/ai/extract`

---

# Domain Rules

- AI output is derived data.
- AI output must be auditable.
- Human review may be required before using extracted values as source data.

---

# AI Agent Guidance

When implementing AI Extraction features:

- read `docs/domains/AI.md`
- do not modify source domain tables directly
- preserve traceability to source data
- document model and prompt version assumptions

---

# Open Questions

- human review workflow
- prompt versioning strategy
- confidence threshold rules
