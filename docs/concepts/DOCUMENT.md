# Document Concept

Status: initial candidate concept

## Purpose

Document tarkoittaa järjestelmään ladattua tiedostoa tai tiedostosta muodostettua dokumenttioliota.

Document ei tarkoita AI:n tekemää poimintaa tai laskutusdokumenttia, ellei se ole tallennettu Document Domainin dokumenttina.

---

# Owner

Owning Domain:

- Document Domain

Related Domain Document:

- `docs/domains/DOCUMENT.md`

---

# Definition

```text
A Document is an uploaded file with metadata, lifecycle state and optional version history.
```

---

# Key Fields

- id
- customer_id
- storage_key
- filename
- content_type
- status
- created_at
- updated_at

---

# Invariants

- Document must have a storage reference.
- Document content is immutable after upload.
- Corrections create a new document version.

---

# Lifecycle

States:

- uploaded
- processing
- ready
- archived
- deleted

Transitions:

```text
uploaded -> processing
processing -> ready
ready -> archived
archived -> deleted
```

---

# Relationships

Related Concepts:

- Customer
- AI Extraction

Related Tables:

- documents
- document_versions

Related APIs:

- `/documents`

---

# Domain Rules

- Document Domain owns document metadata and lifecycle.
- AI Domain owns AI outputs derived from documents.
- Customer Domain owns customer profile data.

---

# AI Agent Guidance

When implementing Document features:

- read `docs/domains/DOCUMENT.md`
- update document lifecycle diagrams when lifecycle changes
- do not store AI extraction state directly in document tables unless explicitly agreed

---

# Open Questions

- file storage strategy
- retention policy
- virus scanning workflow
