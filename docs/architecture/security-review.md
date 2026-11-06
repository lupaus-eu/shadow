# V1 security review

Reviewed on 2026-09-23 against the code on `main` (ticket 23). Each area names
the evidence. This is an engineering review, not an external penetration test,
which remains a launch item.

| Area | Result | Evidence |
| --- | --- | --- |
| OIDC sign-in | Authorization code flow with PKCE (S256), `state`, and `nonce`; the login attempt is single-use and bound to an HttpOnly flow cookie scoped to the callback path; platform and customer audiences never merge accounts. | `app/auth.py`, `tests/test_authentication.py`, `tests/test_security_review.py::test_session_cookie_is_http_only_and_same_site`, `tests/test_platform_operations.py` |
| Sessions | Random token stored as a hash, `HttpOnly`, `SameSite=Lax`, `Secure` in production (`AUTH_COOKIE_SECURE=true` in `docker-compose.prod.yml`), eight-hour default lifetime, server-side revocation on logout; account class checked on every request. | `app/auth.py`, `tests/test_authentication.py` |
| CSRF | `SameSite=Lax` cookies, a CORS allow-list with credentials, and (added in this review) refusal of state-changing requests whose `Origin` is not a trusted frontend or API origin. The Stripe webhook is exempt and signature-verified instead. | `app/main.py`, `tests/test_security_review.py::test_cross_origin_writes_are_refused` |
| SSRF and unsafe links | The backend calls only configured Stripe, Authentik, and Scaleway endpoints. Event links are stored and rendered as links, never fetched, and must be `http` or `https` on both the API and the form. | `app/event_routes.py`, `tests/test_security_review.py::test_event_links_accept_only_http_and_https` |
| Injection | All queries use SQLAlchemy bound parameters; the only interpolated SQL in `app/` is the constant application role name. React escapes rendered text. | `tests/test_security_review.py::test_hostile_text_is_stored_verbatim_not_executed` |
| Tenant crossover | Every tenant table uses forced row-level security under a non-owner role; routes also check membership. The authorization matrix exercises 8 actors × 16 endpoints, self-promotion, and RLS on 11 tables across Organizations. | `tests/test_authorization_matrix.py`, `tests/test_request_context.py` |
| Role escalation | Members cannot change any role or grant themselves Yearclock access; Admins cannot create, demote, or become Owners. | `tests/test_authorization_matrix.py::test_members_cannot_promote_themselves_or_others`, `::test_admins_cannot_promote_themselves_or_anyone_to_owner`, `tests/test_memberships.py` |
| Support scope | Grants are enforced in PostgreSQL (`app_support_grant_allows`); expired, revoked, read-only, other-Organization, and other-agent use fails closed; every use is audited. | `tests/test_support_access.py` |
| Deletion | Pending Deletion is closed in RLS; purge runs only in a narrow worker scope; audit rows stay append-only apart from emptying summaries during purge. | `tests/test_organization_deletion.py` |
| Secrets | Only environment variables; `.env` is git-ignored; production Compose refuses to start without each secret; the monitoring token is compared in constant time; webhook and job errors are stored truncated, without payloads. | `.gitignore`, `docker-compose.prod.yml`, `app/monitoring_routes.py` |
| Webhooks | Stripe signatures verified with a five-minute timestamp tolerance; unsigned or tampered payloads return `400`; events are idempotent by id and stale events are ignored. | `app/billing.py`, `tests/test_organization_activation.py::test_stripe_signature_verification_rejects_tampering`, `tests/test_security_review.py::test_unsigned_stripe_webhooks_are_rejected`, `tests/test_subscription_lifecycle.py` |
| Headers | HSTS, CSP with `frame-ancestors 'none'`, `nosniff`, referrer and permissions policies, and `no-store` for the API and console. | `caddy/Caddyfile`, ticket 22 |

## MCP interface (added with ADR-0037 and ADR-0038)

| Concern | Control | Evidence |
| --- | --- | --- |
| Tokens for other audiences | Only JWTs for the MCP provider (issuer and client id) are accepted; web-provider tokens, wrong signatures, and expired tokens get `401`. Authentik has no RFC 8707, so the audience is the provider's client id. | `tests/test_mcp.py::test_verifier_accepts_only_tokens_for_the_mcp_provider`, `::test_endpoint_needs_a_valid_token_and_publishes_resource_metadata` |
| Identity | The subject must belong to an existing customer account; platform accounts and strangers are refused and no account is created. | `tests/test_mcp.py::test_token_resolves_the_web_account_and_never_creates_one`, `::test_a_platform_account_cannot_use_mcp` |
| Authorization | Every tool calls the functions the REST API uses, so roles, grants, versions, limits, and subscription state apply; other Organizations are not found. | `tests/test_mcp.py::test_read_tools_return_what_the_rest_api_returns`, `::test_other_organizations_stay_out_of_reach`, `::test_writes_follow_the_rest_rules_and_are_attributed_to_mcp` |
| Attribution | Audit entries and Event Revisions made through MCP name the source and the client. | same test |
| Stopping it | Per-Organization switch (Owners and Admins) and operator block, checked before any content is read; the web application is unaffected. | `tests/test_mcp.py::test_the_organization_switch_stops_mcp_for_that_organization_only`, `::test_the_operator_block_cannot_be_lifted_by_the_organization` |
| Prompt injection | Stored text (titles, descriptions, names) reaches the agent and may contain instructions aimed at it. Tool descriptions and results say it is data. Writes are direct (a decision of the owner), so the protection is the client's confirmation prompts (the tools carry `destructiveHint` and `readOnlyHint`), the audit trail, Event Revisions that can be restored, and the switches. | design, ADR-0037 |
| Shared client secret | One secret serves every Organization; it is shown only to Owners and Admins (reveals audited), kept in configuration, and never logged or returned elsewhere. It does not separate customers; isolation is the person's sign-in, membership, and the explicit Organization argument. | `tests/test_mcp.py::test_owners_and_admins_see_the_connection_details_and_members_do_not` |
| Revocation | Access tokens are verified locally, so a token revoked in Authentik works until it expires. Keep the access-token lifetime short. | accepted |

## Open items

- MCP traffic is not rate limited beyond the host (see the next item); a limit on `/api/mcp` belongs with the edge rate limiting decision.

- No application-level rate limiting (a decision is ticket 05 of `.scratch/tech-beta-launch/`). Sign-in brute force is Authentik's
  concern, but API request floods are limited only by the host. Consider Caddy
  rate limiting or an upstream WAF before launch.
- The CSP allows inline styles (`style-src 'unsafe-inline'`), which React style
  attributes need.
- An external penetration test and a dependency audit
  (`pip-audit`, `npm audit`) should run before launch.
