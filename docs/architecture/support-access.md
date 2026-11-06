# Support Access

## Request and approval

- A Support Agent requests access for a specific support case and Organization.
- The request declares its scope and expiry.
- Requests are read-only by default; write access must be explicitly requested and approved.
- A grant may last no longer than 24 hours.
- An Organization Owner or Admin must approve the request.
- Platform roles cannot approve their own request or bypass customer approval.
- Approval creates a Support Access grant; it does not change the Support Agent's normal roles.

## Use and revocation

- Every support request establishes database context for the specific active grant.
- PostgreSQL RLS and application authorization constrain access to the approved Organization and scope.
- The Organization's Owners and Admins may revoke a grant at any time.
- Expired and revoked grants fail closed.
- Requests, approvals, reads, mutations, expiry, and revocation are audited.

## First-release boundary

Emergency break-glass access is not implemented in the first release.
