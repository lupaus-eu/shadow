# TASK-039D API Authorization And Audit Actors

Status: Planned

## Source Plan

Approved TASK-039 plan: the backend is the trusted authentication and
authorization boundary. All existing business APIs must reject anonymous
requests, Users administration is admin-only, and authenticated mutations
should finally populate the repository's existing nullable audit-user columns.

## Goal

Apply the authenticated-user contract from TASK-039C consistently across the
existing API and close the insecure transition in which routes remain public or
mutations know no actor.

## Requirements

- Depends on TASK-039C and accepted ADR-004.
- Keep health plus required auth login/callback/session behavior public as
  defined by ADR-004. Protect every other `/api/v1` route with the active-user
  dependency.
- Require the database `admin` role for all Users list/get/create/update/delete
  operations. Users obtain their own profile from `/auth/session`.
- Permit both current roles to use all other business APIs. Do not infer
  organisation membership, ownership or permissions from route `orgId`, email,
  Entra tenant, Authentik group or token claims. This is intentional: Schatten
  is an internal tool and every application user is trusted to access and
  modify every organisation. It is not a temporary or accidental omission of
  object-level authorization. Revisit the authorization architecture before
  admitting users outside this trust boundary.
- Apply TASK-039C's unsafe-request guard to every authenticated business
  `POST`, `PUT`, `PATCH` and `DELETE`. The backend—not the frontend—must require
  the session-bound CSRF header and exact configured `Origin` and reject missing
  or `null` origins.
- Return `401` for missing/invalid/expired sessions and `403` for an
  authenticated user lacking the required application role, using the existing
  error conventions.
- Pass the authenticated `user_id` through existing mutation service
  boundaries and set:
  - `created_by` on creation
  - `modified_by` on update and domain mutation actions
  - `deleted_by` on soft deletion
- Preserve existing values on reads and operations that do not modify a row.
  Do not backfill historical null audit fields.
- Cover all current domains and mutation actions, including nested and bulk
  operations, without moving business rules between domains.
- Update backend tests to authenticate through a test-only dependency/session
  fixture. Do not weaken production dependencies or add a bypass environment
  variable.
- Add explicit negative tests for anonymous access and consultant access to
  Users administration.
- Add admin-only `POST /api/v1/users/{user_id}/sessions/revoke` using the same
  unsafe-request guard. It atomically deletes all application sessions for the
  selected user and returns `204`; unknown or soft-deleted users use the
  existing not-found behavior. Revoking the caller's own sessions is allowed
  and invalidates the current session after the response.
- Do not implement UI route guards, provider integration or organisation-level
  authorization.

## Acceptance Criteria

- [ ] Every existing business endpoint rejects anonymous requests with `401`.
- [ ] All Users administration endpoints reject consultants with `403` and
      allow admins.
- [ ] Both roles retain access to other existing APIs.
- [ ] Both roles can access resources under every organisation, matching the
      explicitly accepted internal-tool trust model.
- [ ] Every unsafe business endpoint rejects missing, invalid or mismatched CSRF
      and Origin data even when the session is otherwise valid.
- [ ] Admins can revoke all sessions for a user; consultants receive `403` and
      revoked sessions immediately receive `401`.
- [ ] Every existing create/update/delete mutation writes the correct audit
      actor where the affected model has the corresponding column.
- [ ] Soft-deleted or expired-session users immediately lose access.
- [ ] Tests cannot accidentally bypass authentication through production
      configuration.
- [ ] Existing domain behavior and response schemas remain otherwise stable.

## Out Of Scope

- Organisation membership, per-resource permissions and role expansion; these
  are unnecessary under the accepted all-users/all-organisations trust model.
- Provider group or Entra app-role mapping.
- Historical audit backfill or a new AuditEvent domain.
- Frontend authentication state and UX.
- Authentik/Entra infrastructure.

## Implementation Notes

- Read ADR-004, every affected domain document, relevant concept documents,
  `docs/data/DATA-MODEL.md`, `docs/data/DATABASE.md`, `docs/TESTING.md` and this
  task.
- Prefer router-level dependencies for the common authenticated baseline and
  explicit admin dependencies for Users routes. Services still receive the
  actor explicitly for audit writes.
- This task may touch many tests; keep fixture changes centralized and do not
  reduce existing behavioral assertions.

## Testing

Required:

- [ ] Full backend suite
- [ ] Authentication/authorization matrix tests
- [ ] Audit actor tests for each mutation family
- [ ] Backend Ruff and pyright
- [ ] Manual anonymous/admin/consultant API smoke verification

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

## Documentation

Update affected domain/concept documentation so nullable historical audit data,
current authenticated actor writes and the intentional broad non-Users access
model are stated accurately. Document its internal-use trust boundary; do not
claim organisation authorization exists.

## Notes For AI Agent

- Ala keksi organisation membership- tai resource ownership -saantoja.
- Ala muuta domain-logiikkaa auth- ja audit-actor-liitosta laajemmin.
- Ala poista tai heikenna olemassa olevia testeja.
