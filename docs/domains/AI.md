# AI Domain

Status: initial candidate domain

## Purpose

AI Domain hallitsee AI-luokitteluja, tiivistelmiä ja poimintoja.

AI Domain ei omista alkuperäistä customer-, billing- tai document-dataa. Se tuottaa johdettua dataa muiden domainien datasta.

---

# Responsibilities

Owns:

- AI classifications
- AI summaries
- AI extractions

Provides:

- document classification
- document summarization
- structured data extraction
- AI processing metadata

Does NOT Own:

- customer data
- document source data
- billing data

---

# Domain Rules

## Rule 1

AI output must reference the source data it was generated from.

## Rule 2

AI output must store enough metadata to audit how it was produced.

## Rule 3

AI output is not treated as authoritative source data unless a human or explicit business rule accepts it.

---

# Database Ownership

Tables:

- ai_classifications
- ai_summaries
- ai_extractions

Owned exclusively by AI Domain.

Other domains may reference AI outputs but may not modify them directly.

---

# API Ownership

Endpoints:

```text
POST /ai/classify
POST /ai/extract
POST /ai/summarize
```

---

# Dependencies

Depends On:

- Customer Domain
- Document Domain

Referenced By:

- TBD

---

# Common Workflows

## Classify Document

Flow:

1. Validate request
2. Load document metadata
3. Run classification
4. Store AI classification
5. Create audit event
6. Return classification

## Extract Data

Flow:

1. Validate request
2. Load document
3. Run extraction
4. Store extraction output
5. Create audit event
6. Return extraction

---

# AI Agent Guidance

When implementing AI features:

Preferred locations:

- backend/ai/*
- frontend/ai/*

Avoid:

- modifying customer source data directly
- modifying document source data directly
- modifying billing records directly
- treating AI output as verified user data without an explicit rule

If a change affects document lifecycle:

- create a separate Document task

If a change affects customer data:

- create a separate Customer task

---

# Open Questions

- model provider strategy
- prompt/version storage
- human review workflow
- AI output retention policy
