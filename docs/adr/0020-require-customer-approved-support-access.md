---
status: accepted
---

# Require customer-approved Support Access

A Support Agent may access customer content only through a request tied to a specific support case, Organization, scope, and expiry. An Organization Owner or Admin must approve the request and may revoke it at any time; Platform roles cannot self-approve or bypass this boundary. All request, approval, use, expiry, and revocation activity is audited, and the first release provides no emergency break-glass path.

A grant covers every Yearclock of the Organization, read-only unless write
access is explicitly requested and approved. It therefore bypasses
per-Yearclock grants for its duration; the approving Owner or Admin accepts
this, and already has the same access (ADR-0007). The role model review of
2026-09-23 confirmed this scope and kept Owner or Admin as approvers.

Refines ADR-0002.
