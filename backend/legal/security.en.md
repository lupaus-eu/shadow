---
title: Security measures
version: 1
effective_from: 2026-12-01
status: draft
acceptance: none
---
> **Draft for legal review.** Prepared by the product team from the repository's documentation. It is not legal advice and has not been reviewed by a lawyer. `TODO(lawyer)` marks what is unknown or needs legal wording. Nothing here is in force.

This is a summary of the technical and organisational measures that protect Yearclock. It is also the security annex of the data processing agreement. `TODO(lawyer)` decide how to describe items that are still open (marked "not yet done" below).

## Sign-in and sessions
- Sign-in uses an external identity provider with the OpenID Connect authorization-code flow, PKCE, `state`, and `nonce`. Password sign-in needs a second factor; passkeys are supported. Yearclock stores no passwords, passkeys, or MFA secrets.
- A session is a random token stored only as a hash. The cookie is `HttpOnly`, `SameSite=Lax`, and `Secure` in production, lasts at most 8 hours by default, and is revoked on the server at sign-out.
- State-changing requests from an untrusted origin are refused.

## Separation of customers
- Each Organization's data is separated in the database by forced row-level security under a restricted database role; routes also check membership and role. Automated tests cover this across Organizations.
- Members cannot raise their own role or access; Admins cannot create or become Owners.

## Access by Yearclock's staff
- Platform staff reach an Organization only through Support Access: the Owners approve a request with a scope and a duration, access is enforced in the database and expires by itself, and every use is audited. `TODO(lawyer)` confidentiality undertakings of staff.

## Application and infrastructure
- Secrets are held only in environment variables on the host and are never in the repository. Production refuses to start without them.
- Stripe webhooks are signature-checked and idempotent. The service calls only its configured Stripe, identity, and email endpoints.
- The edge sets HSTS, a content security policy that forbids framing, `nosniff`, and referrer and permissions policies, and marks API and console responses `no-store`.
- Customer planning content is purged after deletion as described in the privacy notice and the switching page.

## Backups and recovery
- Both databases are dumped on a schedule, encrypted on the host before upload, and kept off the host in a separate storage project; the key is held only by the operator. Retention is 24 hourly, 30 daily, and 6 monthly snapshots. Restores are rehearsed on a schedule (`TODO(lawyer)` state the recovery point and time you will commit to; the beta documentation names a recovery point of one hour and a recovery time of half a day, with no uptime guarantee).

## Not yet done
- An external penetration test and a dependency audit are planned before launch and have not been done.
- API request rate limiting at the edge is undecided.
