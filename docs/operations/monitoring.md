# Monitoring

## Health endpoints

| Endpoint | Auth | Use |
| --- | --- | --- |
| `GET /health` | none | Liveness of the API process (Compose healthcheck). |
| `GET /api/v1/monitoring/health` | `Authorization: Bearer $MONITORING_TOKEN` | Service checks for an uptime monitor. Disabled (`404`) when `MONITORING_TOKEN` is empty. |
| `https://<identity domain>/-/health/live/` | none | Authentik liveness. |
| Operator console `/platform` (health), `/platform/jobs` | Platform User | Queue counts, failed jobs, replay. |

`/api/v1/monitoring/health` returns `200` with `"status": "ok"` when every
check passes and `503` with `"status": "degraded"` otherwise. It contains
counts and ages only.

| Check | Fails when |
| --- | --- |
| `database` | The database or its schema revision cannot be read. |
| `database_capacity` | The database is larger than `MONITORING_DATABASE_MAX_BYTES` (0 disables). |
| `background_jobs` | Any recurrence, purge, or other job is `failed`. |
| `email_delivery` | Any outbox email is `failed`, or the oldest pending one is older than `MONITORING_EMAIL_MAX_AGE_MINUTES` (default 15). |
| `stripe_webhooks` | Never; reports the last processed webhook. A failed webhook is rolled back and Stripe redelivers it for up to three days; watch failed deliveries in the Stripe dashboard (ADR-0009). |
| `authentik` | Authentik's live endpoint does not answer from the backend network. |

## Host checks (production)

| Check | How it alerts |
| --- | --- |
| Backup | `scripts/ops/backup-offsite.sh` emails `BACKUP_ALERT_EMAIL` on failure (and on success with `BACKUP_SUCCESS_EMAIL=true`, so a missing email is the alarm); an optional heartbeat pings on success and `/fail` on failure (`docs/runbooks/backup.md`). |
| Disk | `scripts/ops/check-disk.sh` runs every 15 minutes from a systemd timer, emails `BACKUP_ALERT_EMAIL` (at most every six hours) when usage reaches `DISK_MAX_PERCENT`, and, if configured, pings its own heartbeat only while usage is below `DISK_MAX_PERCENT` (default 80; both scripts read their settings from `.env.production`), so a full or dead host also alerts. |
| Logs | Every production container keeps at most `LOG_MAX_FILE` (5) files of `LOG_MAX_SIZE` (10 MB), so logs stay below about 50 MB per service. |

Failed items stay failed until an operator replays them in the console, so
the alert clears only after the cause is handled.
