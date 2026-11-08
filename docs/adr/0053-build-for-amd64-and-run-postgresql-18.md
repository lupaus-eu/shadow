---
status: accepted
---

# Build for amd64 and run PostgreSQL 18

## Context

ADR-0035 delivers images from GHCR to a single host, and `images.yml` builds `linux/amd64`. For a short time the first production host was a Hetzner Ampere (arm64) server, and the workflow was switched to `linux/arm64`; before anything was deployed the host was replaced by a Hetzner Intel (x86-64) server, so the platform went back to amd64. The development machine is arm64, which is fine: it builds and runs its own images locally. The stack ran PostgreSQL 17; PostgreSQL 18 is current and the earlier Shadow code was already verified against it, including Authentik. The official `postgres:18` image changed where it keeps data: the volume is `/var/lib/postgresql` and the data directory is `/var/lib/postgresql/18/docker`, so a volume mounted at `.../data` no longer holds the data.

## Decision

- The images stay built for `linux/amd64` (the host is x86-64). `images.yml` needs no QEMU and the frontend Dockerfile is unchanged. arm64 is added later, with QEMU or a native arm64 runner, only if a host needs it; every base image used is multi-architecture and Prophet ships both `manylinux` wheels, which was checked while the switch was tried.
- PostgreSQL moves to `postgres:18-alpine` in the base, production and CI definitions. The data volume is mounted at `/var/lib/postgresql` and renamed `postgres18_data`, so the old PostgreSQL 17 volume is left untouched as the source and as a fallback.
- A major version is never upgraded in place. The move is a dump and restore with the existing scripts: `scripts/ops/backup-databases.sh` on the old version, a fresh cluster on the new one, then `pg_restore --clean --if-exists --no-owner` into each database. The steps are in `docs/runbooks/postgres-major-upgrade.md`. Production holds no data yet, so it starts on 18.
- Dumps written by the script go to `backups/`, which is ignored by Git.

## Consequences

- Production, CI and development run the same PostgreSQL major version. Backups made with `pg_dump` in the container match the server.
- Existing local data needs the dump and restore once; a developer who skips it starts on an empty database and the old volume still has the data.
- The images built for the development machine (arm64) and the ones built in CI (amd64) are different artefacts of the same Dockerfiles; nothing in the Dockerfiles depends on the architecture.

Refines ADR-0035 (the first host is a Hetzner Intel server) and ADR-0011 (separate backups per database).
