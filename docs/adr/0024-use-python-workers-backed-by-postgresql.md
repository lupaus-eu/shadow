---
status: accepted
---

# Use Python workers backed by PostgreSQL

Background work runs in separate Python containers built from the FastAPI backend image and reuses the backend's services, SQLAlchemy models, and transaction rules. PostgreSQL stores outbox and job records with atomic claims, idempotency keys, retries, and failed-job inspection. The first release does not add Redis, Celery, or another message broker, keeping operations simple until throughput requires them.
