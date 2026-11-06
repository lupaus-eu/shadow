# Access and confidentiality rules for the operator's staff

Owner: Platform Operator (the named person is `TODO(operator)`)  
Review by: 2027-05-05, then every six months and after any change to the data the product keeps  
Status: draft for counsel. An engineering record, not legal advice. It holds no personal data and no incident details.

- Staff reach a customer Organization only through **Support Access**: the Organization's Owners approve a request
  with a case reference, a scope, and a duration; access is enforced in PostgreSQL, expires by itself, can be revoked,
  and every use is recorded in the Audit Log. Staff never use a customer's own session.
- A request from a person for their own data uses a read-only database session as described in
  [`docs/runbooks/personal-data-request.md`](../runbooks/personal-data-request.md), not Support Access.
- Production access (host, database, Stripe, email, backup storage) is limited to the named staff `TODO(operator)`,
  uses individual accounts with a second factor, and is removed when a person leaves.
- Every person with such access signs a confidentiality undertaking before access starts. The signed copies are kept in
  the private registers folder, not in git. `TODO(lawyer)` the wording.
- Customer content is read only to solve a customer's problem within a Support Access grant, and is not copied out of the
  service.
