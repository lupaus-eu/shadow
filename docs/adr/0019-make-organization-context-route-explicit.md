---
status: accepted
---

# Make Organization context route-explicit

Tenant browser and API routes include the Organization identifier explicitly. FastAPI verifies the authenticated User Account's membership before establishing PostgreSQL RLS context and never relies on one mutable active-Organization session value. This keeps tenant selection auditable and allows a consultant to use different Organizations in separate browser tabs without cross-tab context changes.
