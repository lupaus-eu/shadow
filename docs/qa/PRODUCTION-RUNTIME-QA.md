# Production Runtime QA (TASK-059G)

This record holds TASK-059G implementation evidence for the UpCloud Docker
runtime, build/release, backup and scheduler tooling. All checks used
disposable local infrastructure, synthetic secrets, a throwaway GPG key and a
simulated Entra discovery endpoint. **No production host, DNS, tenant,
certificate, backup directory or database was touched.** Host verification,
real certificate issuance, backup activation and rollout remain F evidence
under [TASK-059F](../../tasks/TASK-059F-first-production-rollout.md). The
TASK-059E integrated rerun, including the first-initialization sequence and an
Ubuntu 26.04 / Docker Engine 29 run, is recorded separately in
[UPCLOUD-RUNBOOK-QA.md](UPCLOUD-RUNBOOK-QA.md); results below are G's.

## Environment

| Item | Value |
| --- | --- |
| Date | 2026-09-25 |
| Workstation daemon | Docker Engine 28.1.1, Compose 5.1.0, Buildx 0.31.1 on Ubuntu 24.04 (not the target OS) |
| Isolated daemon | `docker:28.5.2-dind@sha256:2a232a42…` reached only through a Unix socket in a temporary directory |
| Source | Scratch clone of the TASK-059G working tree committed as `4822bd2e947d` (not a repository commit) |
| Pinned images | `postgres:18.6@sha256:4ef4dbc9…`, `mcuadros/ofelia:0.3.22@sha256:efcbe2c5…`, `docker:28.5.2-cli@sha256:625d9431…`, `caddy:2.11.4-alpine@sha256:5f5c8640…`, `python:3.12-slim@sha256:2c941e86…`, `node:22-bookworm-slim@sha256:43ac6c60…`, `uv:0.11.24@sha256:99ea34ac…` |

## Disposable End-To-End Runtime

Command: `QA_SOURCE_REPO=<scratch clone> QA_LOG_FILE=<file> .github/scripts/verify-production-runtime.sh`

Result: **pass** (`EXIT=0`, 34 `PASS` assertion groups; 38 after the AI review round 3 fixes, rerun on 2026-09-28 at `da7caee` plus the embedded
`check-host` and `verify-runtime-hardening` passes). Build from a cold cache took
276 s inside the isolated daemon; the second build of the same commit reused the cache.

| Area | Evidence |
| --- | --- |
| Host prerequisites | `check-host --allow-os-mismatch` reported missing lock files before `init-state`, rejected a group-readable env file and then passed |
| Frozen build | `build-release` recorded the exact commit, `SOURCE_DATE_EPOCH`, tool versions, duration, memory and image IDs matching the tags; release source is read-only |
| First install | Refused without approval; pre-migration baseline backup completed; all 15 migrations ran in the one-shot job; API, worker and frontend healthy; `verify-runtime-hardening` passed; a second `--first-install` was refused |
| Edge | Only the frontend published `0.0.0.0:80` and `0.0.0.0:443`; HTTPS health, HSTS/CSP/frame headers, `308` HTTP redirect, SPA fallback and internal-issuer certificate verified; `/api/v1/auth/session` through Caddy returned `401` despite spoofed forwarding headers (a `400` would mean an untrusted peer); a direct request from another container on the edge network with `X-Schatten-Client-IP` got `400` |
| Initialization | `initialize reference-seed` completed, then skipped as idempotent; `initialize bootstrap-admin` refused a non-interactive session |
| Backup and restore | On-demand backup files are `0600`, owned by `10002`, and not a plaintext `PGDMP` archive; `restore-rehearsal` passed checksum, decrypt/restore, schema version 15, 27 tables and constraint checks, wrote evidence and removed its disposable target; `ops-status` listed the backup and evidence |
| Backup failures | Missing public key, secret key material in the key file, missing and wrong database credential, unwritable directory, full disk (4 KiB tmpfs) and an overlapping run all failed with nonzero status and published nothing |
| Retention | Fixture files named 10 and 6 days old plus an orphan dump: the 10-day pair and the orphan were removed; the 6-day pair, newer backups, `notes.txt`, `other-tool-backup.sql.gz` and a non-matching `schatten-foreign.manifest` were kept |
| Persistence | Certificate fingerprint and schema history survived forced replacement of the frontend and database containers |
| Reboot | After a clean daemon restart, database, API, worker and frontend recovered healthy; the migration job was not rerun and runners stayed stopped |
| Scheduler | With a QA job file (`@every 20s`), Ofelia ran both jobs with `failed: false`, produced `scheduled` backups and ignored a label-defined decoy job; the production job file passed `ofelia validate`; Ofelia without the socket group logged `permission denied` and the socket stayed `660` |
| Cleanup | Dry run listed candidates and removed nothing; a held maintenance lock produced exit `75`; no socket access produced `status=failed`; a reachable API whose `docker ps`, `docker images` or `docker builder prune` call failed produced `status=failed` with exit `1` (AI review F-001); apply removed an aged exited container, an unprotected `schatten-backend` fixture image and dangling fixture images, and kept retained/running containers, current and fixture "previous" release images, all volumes and all backup files |
| Release gates | Missing restore evidence blocked a release; a normal release set `current`/`previous`; the current release could not be retired; corrupted migration history made the migration job fail while API and worker containers kept running unchanged, with a `failed` deployment record and `SERVICES_REPLACED=false`; a forced-unhealthy frontend after a successful migration failed with a "may be partly running" message, `SERVICES_REPLACED=true` and unchanged pointers, and the same release then fixed forward (AI review F-002) |
| Rollback | Refused without schema confirmation and refused on divergent history; after repair, rollback passed `rollback-compatibility image_migrations=15 applied=15`, swapped the pointers and did not run migrations or change schema history |
| Secrets | Synthetic database password and client secret absent from the QA log, all container logs and image history |

Limitation: both QA releases were built from the same commit, so their image
IDs are identical. The rollback check proves the gates, prefix check and
coordinated service path, not an actual image change.

## Standard CI Checks Run Locally

| Check | Result |
| --- | --- |
| `.github/scripts/verify-production-compose.sh` | Pass |
| `.github/scripts/verify-release-compose-failure.sh` (disposable project) | Pass |
| `.github/scripts/verify-production-frontend.sh` (production hardening, internal issuer) | Pass |
| `.github/scripts/verify-production-worker.sh` (disposable PostgreSQL) | Pass |
| shellcheck `--severity=warning` on operator and runtime scripts | Pass |
| `make local-verify` | Pass |
| `make backend-lint backend-typecheck` | Pass |
| `make frontend-check` | Not run: local pnpm refused to purge `node_modules` without a TTY; no frontend source or dependency changed, and the production image build (`pnpm install --frozen-lockfile`, `pnpm build`) passed |

## One-Off ACME Check (Not In CI)

The production Caddyfile, with only `acme_ca`/`acme_ca_root` added and one
challenge disabled at a time, obtained certificates from a local Pebble test CA
(`ghcr.io/letsencrypt/pebble@sha256:ddf23064…`) in the production-hardened
frontend container: HTTP-01 (`challenge_type":"http-01`) and TLS-ALPN-01
(`challenge_type":"tls-alpn-01`) both succeeded and HTTPS health returned
`200`. With no reachable CA, the frontend still became healthy while logging
`could not get certificate from issuer`, so certificate issuance cannot block
readiness. Pebble is not a project dependency and is not in CI.

## Not Verified Here (F)

- Ubuntu 26.04 host facts, SSH/UFW/provider rules and effective IPv6 client
  addresses through Docker's userland proxy.
- Real Let's Encrypt issuance for `schatten.lupaus.eu` and DNS.
- Direct Entra login with the production client secret.
- `/opt/postgres-backups` ownership, the production key pair and its recovery
  access, schedule activation and the first production backup/restore evidence.
