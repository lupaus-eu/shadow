---
status: accepted
---

# Use an append-only application Audit Log

Yearclock records all customer-content mutations and sensitive administrative, support, billing-projection, and deletion actions in an append-only PostgreSQL Audit Log. Each event captures the actor, Organization, action, target, timestamp, request correlation identifier, and a minimal change summary without credentials, payment data, or unnecessary content copies. Ordinary customer reads are excluded, while Support Access reads are audited.

Yearclock V2 (2026-09-25) adds Event Revisions for Event history and restore. They are customer content in their own table (`event_revisions`), readable by everyone who may read the Yearclock and purged with it. They are not part of the Audit Log, which keeps its minimal change summaries and reader restrictions.
