---
status: accepted
---

# Use an additive authorization hierarchy

Organization Owners inherit all Organization Admin powers and additionally control ownership, billing, and Organization deletion. Organization Admins manage memberships and every Yearclock but cannot manage Owners, billing, or deletion. Yearclock Editor and Viewer roles are assigned independently per Yearclock, and the strongest applicable permission wins when a user has several roles. The first release has no explicit deny overrides, keeping authorization predictable and auditable.

## Role model review (2026-09-23)

The owner of the product reviewed and confirmed the role model:

- Every membership has exactly one Organization role: Owner, Admin, or
  Member. Each membership occupies one Organization Seat, whatever its role.
- Separating Owner from Admin keeps spending, ownership, and irreversible
  deletion with fewer people than day-to-day user administration. This
  supports a consultant who sets up an Organization and later hands ownership
  to the customer.
- Admins manage every non-Owner membership, including other Admins. Owners
  are the safety net, and every change is audited.
- Owners and Admins see and manage every Yearclock without a grant. An Admin
  controls access and could grant it to themselves, so hiding a Yearclock from
  Admins would be illusory. The Admin role is therefore the confidentiality
  boundary; a plan that must stay hidden from Admins belongs in a separate
  Organization.
- Only Owners and Admins create Yearclocks and grant or revoke Editor and
  Viewer access. Editors maintain Events, Lanes, and Categories in their
  granted Yearclocks but cannot share them.
- A Member sees only the Yearclocks they are granted, and not the membership
  list, seats, audit activity, or Support Access requests.
- An Invitation proposes one Organization role. Yearclock grants are given
  after acceptance; V1 Invitations carry no Yearclock grants.

## Groups and Organization-wide Access (Yearclock V2, 2026-09-25)

Groups and Organization-wide Access add two Access Sources and keep this
decision:
- They only add access.
- They take no seats.
- They never change an Organization role.

A member's role on a Yearclock is the strongest of their Organization role,
their direct grant, their Groups' grants, and the Yearclock's
Organization-wide Access. There is still no deny. Only Owners and Admins
manage Groups and sharing. One function (`app/access.py`) computes the
rule for every check.

