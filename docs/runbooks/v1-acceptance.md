# V1 acceptance checklist

Status: automated parts executed on 2026-09-23 (ticket 23); manual parts open.
The PRD-to-evidence trace is `docs/runbooks/v1-acceptance-trace.md`, the
security review is `docs/architecture/security-review.md`, and launch
decisions are in `docs/runbooks/launch-checklist.md`. Record manual results
as described at the end of the end-user tutorial.

Run the end-user tutorial end to end in English and Finnish. Cover signup and
payment, multiple Organizations, seats/Invitations, roles, Event planning,
recurrence, cancellation, Support Access, and deletion.

For Owner, Admin, Editor, Viewer, Platform Admin, and Support Agent, run the
authorization matrix at UI and API boundaries. Confirm direct API calls cannot
cross Organizations and Platform authority alone never reaches Event content.

Review keyboard operation, visible focus, SVG semantic summaries, small screens,
and non-color state indicators. Exercise dense valid Yearclocks at operational
limits and confirm explicit errors rather than silent loss.

Review OIDC/session/CSRF handling, safe HTTP(S) links, tenant isolation, support
expiry/scope, secrets, and Stripe webhook signatures. Record final production
domain, retention policy, tax configuration, and credential owners outside git.
