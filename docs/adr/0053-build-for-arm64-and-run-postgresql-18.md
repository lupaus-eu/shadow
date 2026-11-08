---
status: accepted
---

# Build for arm64 and run PostgreSQL 18

## Context

ADR-0035 delivers images from GHCR to a single host. The first production host is a Hetzner Cloud server on Ampere arm64, and the development machine is arm64 too, while the image workflow built only `linux/amd64` (a pull on the arm64 host fails: no matching manifest). The stack ran PostgreSQL 17; PostgreSQL 18 is current and the earlier Shadow code was already verified against it, including Authentik. The official `postgres:18` image changed where it keeps data: the volume is `/var/lib/postgresql` and the data directory is `/var/lib/postgresql/18/docker`, so a volume mounted at `.../data` no longer holds the data.

## Decision

- The images are built for `linux/arm64` only. `images.yml` adds QEMU and sets `platforms: linux/arm64`; the frontend Dockerfile runs its Node build stages on the build platform (`FROM --platform=$BUILDPLATFORM`) and only the final Caddy stage on the target platform, so `npm ci` does not run under emulation. amd64 is added later only if a host needs it. Every base image used is multi-architecture, and Prophet ships a `manylinux aarch64` wheel.
- PostgreSQL moves to `postgres:18-alpine` in the base, production and CI definitions. The data volume is mounted at `/var/lib/postgresql` and renamed `postgres18_data`, so the old PostgreSQL 17 volume is left untouched as the source and as a fallback.
- A major version is never upgraded in place. The move is a dump and restore with the existing scripts: `scripts/ops/backup-databases.sh` on the old version, a fresh cluster on the new one, then `pg_restore --clean --if-exists --no-owner` into each database. The steps are in `docs/runbooks/postgres-major-upgrade.md`. Production holds no data yet, so it starts on 18.
- Dumps written by the script go to `backups/`, which is ignored by Git.

## Consequences

- Production, CI and development run the same PostgreSQL major version. Backups made with `pg_dump` in the container match the server.
- The first build of arm64 images under QEMU is slower than a native build; a native arm64 runner can replace QEMU later without changing the images.
- Existing local data needs the dump and restore once; a developer who skips it starts on an empty database and the old volume still has the data.

Refines ADR-0035 (the image platform and the first host) and ADR-0011 (separate backups per database).
