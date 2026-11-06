---
status: accepted
---

# Use synchronous SQLAlchemy and Alembic

Yearclock uses SQLAlchemy 2 with synchronous Psycopg 3 access and Alembic migrations. Each request owns one database session and transaction, establishes trusted PostgreSQL row-level-security context at transaction start, and keeps API schemas separate from ORM models. This favors explicit transaction behavior and simpler RLS reasoning over introducing asynchronous database sessions before the workload requires them.
