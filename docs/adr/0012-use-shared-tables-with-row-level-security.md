---
status: accepted
---

# Use shared tables with row-level security

Tenant-owned Yearclock data uses shared PostgreSQL tables with a required `organization_id`. FastAPI performs membership and role authorization, while PostgreSQL row-level security independently limits each request transaction to its trusted active Organization and optional Support Access context. This avoids per-tenant schema operations while defending against application queries that accidentally omit tenant filters.
