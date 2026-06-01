# Domain Name

Status: draft

## Purpose

Kuvaa mitä domain hallitsee ja miksi se on olemassa.

Kerro myös, toimiiko domain jonkin datan source of truth -kerroksena.

---

# Responsibilities

Owns:

- domain-owned concept 1
- domain-owned concept 2

Provides:

- capability 1
- capability 2

Does NOT Own:

- out-of-scope concept 1
- out-of-scope concept 2

---

# Domain Rules

## Rule 1

Kirjaa domainin pysyvä sääntö.

## Rule 2

Kirjaa toinen sääntö.

## Rule 3

Kirjaa poistoon, arkistointiin, validointiin tai lifecycleen liittyvä sääntö.

---

# Database Ownership

Tables:

- table_1
- table_2

Owned exclusively by this domain.

Other domains may reference these tables but may not modify them directly unless explicitly allowed here.

---

# API Ownership

Endpoints:

```text
GET /resource
POST /resource
PUT /resource/{id}
DELETE /resource/{id}
```

---

# Dependencies

Depends On:

- None

Referenced By:

- Other Domain

---

# Common Workflows

## Workflow Name

Flow:

1. Validate request
2. Load required data
3. Apply domain rules
4. Persist change
5. Create audit event if required
6. Return response

---

# AI Agent Guidance

When implementing features in this domain:

Preferred locations:

- backend/domain-name/*
- frontend/domain-name/*

Avoid:

- modifying another domain's tables directly
- adding cross-domain shortcuts
- changing domain boundaries without updating `docs/domains/DOMAIN.md`

If a change affects another domain:

- create a separate task for that domain
- update both domain documents if ownership or dependency changes
- consider whether an ADR is required

---

# Open Questions

- question 1
- question 2
