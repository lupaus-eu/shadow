# Organisations Domain

Status: core domain baseline

## Purpose

Organisations Domain hallitsee organisaatioita, joiden sisalla skenaariot, organisaatiotilat ja organisaatiokohtaiset metamodelit elavat.

Organisation on tenant-like datan omistusraja, ei nykyisen käyttöoikeusmallin
membership-raja.

---

# Responsibilities

Owns:

- organisation records
- stable organisation keys
- active organisation display names
- organisation soft-delete lifecycle

Provides:

- organisation lookup
- organisation list and search
- organisation boundary for scenarios
- organisation boundary for organisation-specific metamodels

Does NOT Own:

- user records
- scenario contents
- organisation state snapshots
- graph structure
- metamodel type contents

---

# Domain Rules

## Stable Key

`organisation_key` is the stable external/import identity for an organisation.

It is unique among active organisations.

## Name Uniqueness

Active organisation `name` values are unique case-insensitively.

Soft-deleted historical organisation names are reusable.

## Deletion

Organisation deletion is a soft delete using `deleted_time`.

Normal reads should exclude rows where `deleted_time IS NOT NULL`.

## Authorization And Audit Actors

Kaikki endpointit vaativat aktiivisen istunnon. Sekä `admin` että `consultant`
saavat lukea ja muuttaa kaikkien organisaatioiden dataa hyväksytyn sisäisen
työkalun trust boundaryn mukaisesti. `organisation_key`, frontendin route
`orgId` tai provider claim ei osoita membershipiä.

Autentikoitu luonti kirjoittaa `created_by`, päivitys `modified_by` ja soft
delete sekä `modified_by`- että `deleted_by`-actorin. Historialliset null-arvot
säilyvät.

---

# Database Ownership

Tables:

- organisations

Owned exclusively by Organisations Domain.

Other domains may reference `organisations.organisation_id` but may not modify organisation records directly.

---

# API Ownership

Endpoints:

```text
/organisations
```

Exact HTTP operations and versioned paths are defined in backend implementation tasks.

---

# Dependencies

Depends On:

- Users Domain for audit references

Referenced By:

- Organisation States Domain
- Organisation Twin Structure Domain

---

# Common Workflows

## Create Organisation

Flow:

1. Validate name.
2. Generate or validate stable `organisation_key`.
3. Reject duplicate active organisation names case-insensitively.
4. Create organisation row.
5. Return organisation data.

## Soft Delete Organisation

Flow:

1. Load active organisation.
2. Apply domain-specific deletion checks.
3. Set `deleted_time`.
4. Exclude organisation from normal reads.

---

# AI Agent Guidance

When implementing organisation features:

- read this document before changing organisation data, APIs or rules
- preserve active case-insensitive name uniqueness
- preserve reusable names for soft-deleted organisations
- use `organisation_key` for stable external API identity unless a task states otherwise

Avoid:

- exposing bigint primary keys as stable external identifiers
- changing scenario or graph ownership from this domain

---

# Open Questions

- organisation deletion behavior when active scenarios exist
