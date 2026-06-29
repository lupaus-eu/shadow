# Users Domain

Status: core domain baseline

## Purpose

Users Domain hallitsee Schattenin sovelluskayttajia ja kayttajan sovellusroolia.

Tama domain toimii source of truth -kerroksena sovelluksen omille user-riveille. Microsoft Entra ID on tuleva ulkoinen identiteettilahde, mutta sen tarkka mappaus ei kuulu tahan taskiin.

---

# Responsibilities

Owns:

- application users
- user roles
- user soft-delete lifecycle

Provides:

- user lookup
- user role lookup
- audit user references for other core tables

Does NOT Own:

- Microsoft Entra ID tenant configuration
- organisation membership rules
- organisation data
- scenario or graph data

---

# Domain Rules

## Role Values

User `role` must be one of:

- `consultant`
- `admin`

## Audit References

Core tables may reference `users.user_id` through nullable audit columns:

- `created_by`
- `modified_by`
- `deleted_by`

Audit references remain nullable until authentication is implemented.

## Deletion

User deletion is a soft delete using `deleted_time`.

Normal reads should exclude rows where `deleted_time IS NOT NULL`.

---

# Database Ownership

Tables:

- users

Owned exclusively by Users Domain.

Other domains may reference `users.user_id` from audit columns but may not modify user records directly.

---

# API Ownership

Endpoints:

```text
/users
```

Exact HTTP operations and versioned paths are defined in backend implementation tasks.

---

# Dependencies

Depends On:

- Microsoft Entra ID, when authentication is implemented

Referenced By:

- Organisations Domain
- Organisation States Domain
- Organisation Twin Structure Domain

---

# Common Workflows

## Create User

Flow:

1. Validate user name and role.
2. Create active user row.
3. Return user data.

## Soft Delete User

Flow:

1. Load active user.
2. Set `deleted_time`.
3. Set `deleted_by` when authenticated actor data exists.
4. Exclude user from normal reads.

---

# AI Agent Guidance

When implementing user features:

- read this document before changing user data, APIs or rules
- preserve role constraints
- keep audit user references nullable until authentication is implemented
- do not add Entra ID behavior without an auth-specific task or ADR

Avoid:

- modifying organisation, scenario or graph tables directly from Users Domain
- hardcoding identity provider assumptions outside approved auth work

---

# Open Questions

- Entra ID subject-to-user mapping
- organisation membership and authorization model
