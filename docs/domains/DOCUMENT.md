# Document Domain

Status: initial candidate domain

## Purpose

Document Domain hallitsee ladattuja dokumentteja, niiden metatietoja ja dokumenttien lifecycleä.

Se voi viitata asiakkaaseen, mutta ei omista customer profile -dataa.

---

# Responsibilities

Owns:

- uploaded documents
- document versions
- document metadata
- document lifecycle

Provides:

- document upload
- document lookup
- document metadata updates
- document lifecycle transitions

Does NOT Own:

- customer data
- billing data
- AI-generated summaries or extractions

---

# Domain Rules

## Rule 1

Document must always have:

- id
- owner or parent reference
- storage reference
- created_at

## Rule 2

Document content is immutable after upload. Corrections create a new version.

## Rule 3

Document deletion policy must be explicit before production use.

---

# Database Ownership

Tables:

- documents
- document_versions

Owned exclusively by Document Domain.

Other domains may reference these tables but may not modify them directly.

---

# API Ownership

Endpoints:

```text
GET /documents
POST /documents
GET /documents/{id}
```

---

# Dependencies

Depends On:

- Customer Domain

Referenced By:

- AI Domain

---

# Common Workflows

## Upload Document

Flow:

1. Validate request
2. Validate customer or parent reference
3. Store file
4. Create document metadata
5. Create audit event
6. Return document

## Update Document Metadata

Flow:

1. Validate request
2. Load document
3. Apply metadata changes
4. Create audit event

---

# AI Agent Guidance

When implementing document features:

Preferred locations:

- backend/document/*
- frontend/document/*

Avoid:

- modifying customer profile tables
- modifying billing tables
- storing AI extraction state directly in document tables unless explicitly agreed

If a change affects AI processing:

- create a separate AI task

---

# Open Questions

- file storage strategy
- document retention policy
- versioning model
