---
status: accepted
---

# Deliver beta images from GHCR to a single UpCloud host

## Context

The alpha and beta run on one Docker Compose host (ADR-0034) with a handful of
users (fewer than five in the test phase). The host is an UpCloud cloud server.
The production stack builds its images on the host, which needs the source, a
build toolchain, spare memory, and disk, and ties a deployment to whatever the
host happens to compile. Authentik (server and worker) is the heaviest part of the
stack; the application database and Authentik's share one PostgreSQL container.

## Decision

- **Build off the host, pull on the host.** GitHub Actions builds the `backend` and
  `frontend` (target `production`) images for `linux/amd64` and pushes them to the
  GitHub Container Registry (`ghcr.io/lupaus-eu/yearclock-backend` and
  `-frontend`). The `migrate`, `backend`, and `worker` services use the same backend
  image. `docker-compose.prod.yml` references images only, by an explicit tag
  (`YEARCLOCK_TAG`), never `latest`, and the host runs `docker compose pull` and
  `up -d`. A rollback is starting the previous tag. The host holds no source other
  than the Compose file, the Caddyfile, the Authentik configuration, and the
  operations scripts.
- **GHCR is the registry.** Private images are free within the account's package
  quota, and the repository already pulls Authentik from `ghcr.io`. The host signs in
  with a read-only token (`read:packages`). UpCloud's container registry is not used
  because it is paid for no benefit at this size. Old tags are pruned from time to time.
- **Host size.** The test phase runs on **2 GB RAM and 2 CPU cores or more, with 2 GB
  of swap**. 4 GB / 2 CPU (EUR 12 a month on 2026-11-03) is recommended; the 2 GB / 2 CPU
  plan (EUR 8) is the minimum and can be resized upward. The 1 GB plans do not fit:
  Authentik alone needs about 1 to 1.5 GB. Prices are the plans' list prices and are
  rechecked when ordering.
- **PostgreSQL stays in its container for the test phase.** At fewer than five users
  it uses 150 to 400 MB, so a managed database frees little and adds roughly EUR 15 a
  month (to be confirmed). The compensating controls of ADR-0034 apply: hourly encrypted off-host
  backups and a rehearsed restore. Both databases keep separate owners, so a move
  later is a connection-string change plus a restore.
- **Trigger for managed PostgreSQL.** Moving is decided by ticket 08 of
  `tech-beta-launch` and happens when the user count, an availability commitment, or
  the value of the data outgrows a single host. It needs SSL on every connection,
  an allow-list for the host's address, `authentik-db-init` rewritten for a managed
  admin role, the pools sized under the managed `max_connections`, and the backup
  scripts pointed at the remote host.

## Consequences

- CI gains an image workflow that needs only `GITHUB_TOKEN`; nothing is deployed
  from CI, so no deploy secret leaves the host.
- Releases are named by Git tag or commit SHA, and an image is the same bytes on
  every host.
- The Compose file can no longer build; building locally uses
  `docker-compose.yml` (`make up`).
- The single host remains a single point of failure, as ADR-0034 states.
- Refines ADR-0034 (the database and host for the beta). Does not change ADR-0010,
  ADR-0011, or ADR-0024.
