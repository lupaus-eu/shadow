---
status: accepted
---

# Use PostgreSQL with service-level isolation

PostgreSQL stores all persistent Yearclock application data and also backs Authentik. In the first release, both services share one PostgreSQL instance but use separate logical databases, owners, credentials, connection pools, migration histories, and restore procedures. This provides one operational database technology without coupling application persistence to identity-provider internals, while preserving the option to move Authentik to a dedicated instance later.
