# Testing

Tämä dokumentti kuvaa projektin testauskäytännön ihmisille ja AI-agenteille.

Status: frontend and backend test tooling configured

Testityökalut on päätetty ADR-001:ssä:

- frontend: Vitest
- frontend linting: ESLint
- frontend formatting: Prettier
- backend: pytest
- backend type checking: pyright
- backend linting: Ruff

---

# Principle

Jokaisessa sovelluskoodin muutoksessa pitää tehdä jompikumpi:

1. lisää tai päivitä relevantit testit
2. perustele miksi testejä ei lisätty

AI-agentti ei saa jättää testausta hiljaisesti tekemättä.

---

# What To Test

## Documentation-only Change

Required:

- tarkista Markdown ja linkit kohtuullisesti
- aja saatavilla oleva dokumentti- tai baseline-tarkistus, jos sellainen on olemassa

Tests may be marked not applicable.

## Small UI Or API Change

Expected:

- unit tests for changed logic
- manual verification for visible behavior
- update snapshots or component tests if project uses them

## Domain Logic Change

Expected:

- unit tests for domain rules
- edge cases for validation and lifecycle rules
- tests for failure paths

Also check:

- relevant domain document
- relevant concept document

## Database Or Migration Change

Expected:

- paired up and down scripts in `db/migrations/`
- test or documented verification that migration applies cleanly
- PostgreSQL verification that the down migration reverts cleanly
- data model documentation update when logical model changes
- database documentation update when physical schema changes

Also update when relevant:

- `docs/data/DATA-MODEL.md`
- `docs/data/DATABASE.md`
- `docs/diagrams/db-physical-schema.puml`
- `docs/diagrams/generated/db-physical-schema.svg`

## Migration Runner

Migration runner unit tests cover discovery, filename and pair validation,
ordering, CLI parsing, history prefixes, checksums and latest-only rollback.
PostgreSQL integration tests cover the actual up/down lifecycle, baselining,
transaction failures, concurrency locking and migration-specific rollback
constraints.

Run the integration suite only against a disposable database. The tests create
and remove uniquely named schemas inside that database:

```bash
cd backend
MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten uv run pytest tests/test_migrations_integration.py -v
```

When `MIGRATION_TEST_DATABASE_URL` is absent, the integration module is skipped;
unit tests still run. CI supplies PostgreSQL 18 and always runs the integration
suite.

## Production Image And Release Migration

TASK-038 packages the existing runner into the production backend image and
gates backend startup with a one-shot Compose service. Verify both the portable
artifact and deployment wiring:

```bash
docker build --target production -t schatten-backend:local -f backend/Dockerfile .

.github/scripts/verify-production-compose.sh

docker run --rm \
  --workdir /tmp \
  --entrypoint python \
  schatten-backend:local \
  -c "import os; from app.core.migrations import discover_migrations; assert discover_migrations(); assert os.getuid() == 10001"
```

Against disposable PostgreSQL, verify fresh `up`, repeated no-op `up`, failure
blocking and concurrent-runner serialization before backend startup. Never use
a developer's normal schema or production for destructive tests.

CI runs `.github/scripts/verify-release-compose-failure.sh` in a disposable
Compose project using the production file's own PostgreSQL service. The script
corrupts disposable migration history, starts the real production Compose model
and requires a nonzero migration-container exit plus no started backend,
prediction worker or frontend service. It removes only its own project volume. It reads
the migration service exit directly because Compose CLI exit behavior can vary
after a dependency fails.

TASK-057E additionally runs `.github/scripts/verify-production-worker.sh`
against a migrated disposable PostgreSQL database and the production backend
image. It verifies numeric non-root execution, database-only configuration, no
published port, the worker-specific health command, duplicate-worker exclusion,
automatic restart, shutdown grace/init configuration and credential/snapshot-
safe lifecycle logs. Queue ordering, blocked-child cancellation, atomic
publication and interrupted-request recovery remain covered by the PostgreSQL
pytest harness below; both evidence sets are required.

## Production Reference-Data Seed

TASK-059C tests the database-only reference seed against disposable PostgreSQL
schemas. The suite runs the production Python path and the real stdin-driven
development `psql` wrapper, then compares every mapped metamodel/type/attribute/
connection field while confirming that only development receives its two Users.
It also covers no-op/idempotent behavior, concurrent callers, an existing active
default, atomic rollback and failure before migrations:

```bash
cd backend
MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten \
  uv run pytest tests/test_seed_reference_data_postgresql_integration.py -v
```

The production image check confirms that only the shared SQL/JSON resources are
packaged, the command runs as numeric user `10001` from `/tmp` with only
`DATABASE_URL`, and a repeated invocation succeeds as a no-op. Never point this
suite or the image command at production.

## First Production Administrator Bootstrap

TASK-059D covers CLI input validation, cancellation, generic output and redaction
without a database. Its disposable PostgreSQL suite covers the successful
fixed-role insert, active and soft-deleted User refusal, writer serialization,
rollback, missing migrations and the reference-seed -> bootstrap -> guarded
first-link sequence:

```bash
cd backend
uv run pytest tests/test_bootstrap_admin.py -v
MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten \
  uv run pytest tests/test_bootstrap_admin_postgresql_integration.py -v
```

Build the production image and exercise `python -m app.bootstrap_admin` only
against a migrated disposable database whose entire `users` table is empty. Run
it as numeric user `10001` from `/tmp` with only `DATABASE_URL`, an interactive
stdin and no OIDC/public-origin/session settings. Verify one active admin with
null audit actors and no identity/session, then verify a repeat invocation
refuses without mutation. Never enter a real production administrator during
implementation QA and never point this suite at production.

## Production Frontend And Authentication Deployment

TASK-039G added the immutable frontend/Caddy artifact; TASK-059G makes it the
direct TLS edge. Run the production Compose and live ingress regression:

```bash
.github/scripts/verify-production-compose.sh

docker build --target production -t schatten-frontend:local \
  -f frontend/Dockerfile frontend
FRONTEND_IMAGE=schatten-frontend:local \
  .github/scripts/verify-production-frontend.sh
```

The Compose check renders all profiles and verifies required settings, no build
sections, frozen image IDs and digest-pinned operational images, hardening on
every service, only Caddy's TCP 80/443 published, internal `data` network,
database-only migration/worker configuration, the database -> migration ->
API/worker -> frontend gates, the fixed Caddy peer `/32`, confined socket,
secret and backup mounts, and the absence of Coolify/Traefik/Authentik. The live
Caddy check runs the image with production hardening and the internal issuer,
and covers configuration adaptation for both TLS modes, unsupported TLS mode and
non-canonical, port-bearing, malformed or wildcard origin rejection, loopback
health, HTTP -> HTTPS redirect, SPA fallback, wrong-Host rejection on 80 and
443, forwarded-header replacement with the actual peer address, no HTTP/3
advertisement, HSTS, Referrer-Policy, nosniff, frame denial, enforced CSP and
selective callback query redaction plus CSRF-header redaction while retaining
ordinary request metadata.

Automated checks do not replace provider/browser verification. Run simulated
direct-Entra OIDC and local Caddy checks from
`docs/qa/AUTHENTICATION-QA-CHECKLIST.md`. Authorized browser verification uses
the designated Entra account and is recorded separately; it does not prove the
direct production client or authorize production activity.

There is no staging rehearsal. After each human-approved production
deployment, operators run only the limited direct Entra smoke defined in
`docs/DEPLOYMENT.md`; destructive, load, failure injection and broad automated
testing are prohibited against production.

## Production Runtime, Backups And Scheduler

TASK-059G's `.github/scripts/verify-production-runtime.sh` exercises every
`deploy/bin` command end to end on an **isolated Docker-in-Docker daemon**
reached only through a Unix socket in a temporary directory. It never uses the
developer's or production Docker resources, volumes or storage, generates a
throwaway GPG key and synthetic secrets, and removes everything on exit:

```bash
.github/scripts/verify-production-runtime.sh
# or, for uncommitted work, point it at a scratch clone with a WIP commit:
QA_SOURCE_REPO=/path/to/scratch-clone .github/scripts/verify-production-runtime.sh
# QA_LOG_FILE=/path/qa.log keeps the detailed, secret-free log as evidence.
```

Do not edit the harness while it runs; bash reads scripts incrementally, so run
it from a frozen checkout or clone.

It covers `check-host`/`init-state`; the Git-free source path (below);
`build-release --source` with matching recorded image IDs; first-install deployment with baseline backup;
published ports, internal-issuer TLS, redirect, headers, SPA, sanitized
forwarding and exact Caddy-peer trust; the explicit seed/bootstrap interfaces;
encrypted backup file mode and ownership, isolated restore with schema/data
evidence; missing/secret key, missing/wrong credential, permission-denied,
disk-full and overlapping-backup failures without published files; 7-day
retention with fixture timestamps that preserves unrelated files; certificate
and database persistence across replacement; daemon-restart (reboot)
recovery without rerunning migration or runners; Ofelia scheduling of both
jobs, label-job isolation, visible failure without socket group access and
`verify-runtime-hardening` against effective container settings; cleanup
dry-run, lock skip, failure reporting and protection of volumes, backups,
current/previous/frozen release images and retained containers; the
restore-evidence gate; failed-migration isolation; schema-compatible rollback
without migrations and refusal on divergent history; and a secret scan of logs
and image history. CI also runs shellcheck on the operator scripts.

TASK-059H1 replaced the harness's `build-release <commit>` with the delivered
source path. On the runner side only, `create-source-manifest.sh` exports the
commit into an upload-style folder; the harness checks that a second export
gives a byte-identical manifest, that it lists every tracked file with its Git
mode and SHA-256, and that scratch repositories with a symlink or a submodule
are refused. It then adds a stale file and wrong modes to the upload, **drops
Git from `PATH`** (a symlink farm of every other tool; `command -v git` must
fail) and runs every remaining step without Git. `schatten-receive` must
reject a wrong or unknown digest, a changed, missing, symlinked or non-regular
(FIFO) file, a symlinked parent or upload folder, `..` and absolute paths, a
duplicate entry, a non-`main` ref and a commit that is not the upload folder
name, each leaving the sources folder empty. The accepted copy must omit the
stale files, carry manifest modes read-only, keep verifying after the upload
is changed, and must not be replaced by a second receive. `build-release`
refuses the old commit argument, a self-consistent read-only folder outside the
sources directory and an unverified folder inside it, and its
`release.env` must carry the manifest digest, ref, run ID and commit time with
no `GIT_VERSION`; the frozen release source re-verifies against its manifest.

TASK-059H3 drives the operator steps through `deploy/Makefile` from the
verified read-only copy, still with Git absent from `PATH`: `make build`,
`make first-install`, `make deploy`, `make backup`, `make restore`,
`make status` and `make cleanup-dry-run` replace the direct calls (receive stays
a direct receiver call, as on the host). A static check requires exactly the
documented targets, that every wrapped command exists in `deploy/bin` and that
no recipe runs `down`, prune, volume removal, `--apply`, rollback,
initialization or the receiver. `deploy`/`first-install` must fail with a usage
message without `RELEASE` or `APPROVAL` and refuse a release of another commit;
`restore` must require `BACKUP` and `KEY` and refuse relative `KEY` or
`PASSPHRASE` paths; `logs` must refuse an unknown
service and shell syntax in `SERVICE`; `make check` may fail only at the OS
check off Ubuntu 26.04. After the first install, `make ps` and `make logs`
must show the current release without environment variables; `make stop` must
stop every long-running service while keeping the same containers and volumes,
record them and refuse a second stop; while stopped, `make deploy` and a
direct rollback must be refused without starting services, moving `current` or
writing a deployment record, and `make status` must list the stopped services;
`make start` must start the same containers healthy without rerunning the
migration job, and refuse without a record. With the scheduler active, `stop`/`start` must include Ofelia (retrying
while a scheduled QA backup holds the backup lock).

TASK-059E extends the same harness with the runbook's first-installation
sequence: `initialize status` counts prove nothing is seeded at startup, the
reference seed is explicit and idempotent, and `initialize bootstrap-admin` is
driven through a pseudo-terminal with synthetic input. It must create exactly
one active admin with no identity, session or development data, print its input
only through the terminal echo, and refuse a repeat without change. The QA backup
key is passphrase-protected; a wrong passphrase must produce failed restore
evidence that blocks the next release, and the successful rehearsal of the
initialized database must show the admin and reference-data row counts.

`QA_DIND_IMAGE` selects another digest-pinned daemon. To approximate the target
host, run the harness from an Ubuntu 26.04 container (uutils coreutils, Docker
CLI/Compose/Buildx from Docker's APT repository, a non-root user in the host
socket's group, `/tmp` shared at the same path) against a Docker Engine 29
daemon; `docs/qa/UPCLOUD-RUNBOOK-QA.md` records the exact commands. That image
needs Git for the harness's runner-side manifest, so the server-side commands
are also checked in an Ubuntu 26.04 container **without Git installed**
(`init-state`, `check-host`, root-installed `schatten-receive`,
`build-release --source`), as recorded in `docs/qa/SOURCE-DELIVERY-QA.md`.

## Source Delivery Workflow And Upload Gate

TASK-059H2 adds a disposable sshd test for the "Deploy to production" workflow
and `deploy/bin/upload-gate`. Run it from the repository on an x86_64
workstation with Docker, Git, curl, Python 3 and the OpenSSH client (it needs
APT and GitHub access; it changes nothing outside a container and a temporary
folder and uses synthetic keys only):

```bash
.github/scripts/verify-upload-gate.sh
# QA_UBUNTU_IMAGE=<digest-pinned ubuntu:26.04> selects another base image.
```

It reads the pinned `appleboy/scp-action` SHA, the `drone-scp` version and
hash, and the upload step's `with:` inputs from the workflow, so it always
tests what the workflow uses. `prepare-production-upload.sh` writes the job
summary for `HEAD` (and refuses a non-`main` ref). An Ubuntu 26.04 container
runs sshd with the upload account set up as in
[DEPLOYMENT.md](DEPLOYMENT.md#source-delivery-workflow-and-upload-account-task-059h2).
The action's `entrypoint.sh` at the pinned commit then runs with the same
inputs as on the runner, first through a recording forced command: the captured
`SSH_ORIGINAL_COMMAND` sequence must be exactly `ver`, `scp -tr`, `mkdir -p`,
`tar -zxf ... --overwrite` and `rm -rf` in the forms the gate allows. The same
upload must then succeed through `upload-gate`, a repeat must overwrite, a wrong
host fingerprint must stop it, the action must take the pre-verified
`drone-scp` through `DRONE_SCP_RELEASE_URL=file://...` as in the workflow and
that binary must have the
recorded hash, and `schatten-receive` must accept the upload as `deploy` with
the digest taken from the summary. The key must be refused for a shell (with
and without a pty), other commands, reads, other paths, command injection,
extra spaces, removal of anything but the action's archive, sftp, scp in both
protocols and `-W`/`-R` forwarding. While one gate command is held open (an `scp`
sink waiting for data), a parallel `rm -rf`, `scp -tr` and `mkdir -p` must be
refused as busy. The held `scp` must run under the gate's
`timeout --kill-after=10s 10m`; its expiry, triggered with `SIGALRM` (which
coreutils `timeout` handles like its own timer), must end the session with exit
124 and release the lock. Crafted archives sent through the allowed
commands must not write outside the upload area: `..` and absolute members stay
inside, while symlink and hardlink members and a folder holding a planted
symlink are refused. No file owned by the upload account may exist outside the
upload area.

Lint the workflow with the actionlint Docker image (not a project dependency)
and the scripts with shellcheck; CI runs both:

```bash
docker run --rm -v "$PWD:/repo:ro" -w /repo \
  rhysd/actionlint:1.7.9@sha256:a0383f60d92601e2694e24b24d37df7b6a40bed7cedbc447611c50009bf02d94 \
  .github/workflows/deploy-production.yml
```

GitHub offers the manual run only once the workflow is on `main`; the first
real run is F work.

## Operator Runbook And Host Audit

`deploy/bin/audit-host` is read-only and cannot be exercised against the real
host before F. Test changes to it in a disposable `ubuntu:26.04` container
**without Git** set up like the reported baseline (locked `deploy`/default
users with authorized keys, NOPASSWD sudo, `sshd` with the cloud-init drop-in,
UFW with the OpenSSH/80/443 rules, a fail2ban `sshd` jail, the `/opt`
directories and no `make`). Run it as `deploy` both directly and through
`bash -s` on stdin, and confirm the expected baseline attention items: `make`
missing, root SSH not key-only (add `PermitRootLogin yes` to the main
`sshd_config`, as observed on the real host), `AllowUsers` not set, SSH open to
`Anywhere` while root login is not key-only, a root-owned `/opt/apps` and
backup directory ownership; the upload account, upload folder and both tools
are reported as absent facts, root's key count with `0` `disable_root`-prefixed
keys as a fact. Then apply runbook 2.1 and 2.2 (hardening drop-in with
`PermitRootLogin prohibit-password` and `AllowUsers deploy root schatten-upload`,
`make`, the upload account with its root-owned `restrict,command=` key, the
upload folder and both tools) and run `make audit` from a read-only copy named
after a commit: the SSH (`root SSH is key-only`), `AllowUsers` (`deploy` and
`root` from any address, `schatten-upload`), upload and tool lines must be
`ok`, the overridden main-file `PermitRootLogin yes` and SSH from `Anywhere`
facts. `deploy@<cidr>`/`root@<cidr>` patterns and `PermitRootLogin no` must be
stricter facts. Negative variants must be attention: another account in
`AllowUsers`, no `deploy` entry, an effective `PermitRootLogin yes` (also making
SSH from `Anywhere` attention), an upload account in an extra group, a key
without the forced command, a group-writable gate, a `0770` upload folder, and
SSH from `Anywhere` once password login is re-enabled. Check that `ssh` as
`deploy` and as root is accepted with a key from an arbitrary address, that
password logins for both and logins as other accounts are refused, that the
upload key reaches only `upload-gate`, and that no key material appears in the
output. Run shellcheck on it, and do not run it with
elevated privileges on shared machines beyond its read-only `sudo -n` probes.
`docs/PRODUCTION-RUNBOOK.md` commands that cannot be exercised without the real
host or provider (for example `systemctl reload ssh`, DNS, Entra, UpCloud
firewall) are labelled untested there and remain F verification.

Real ACME issuance is not part of CI. `docs/qa/PRODUCTION-RUNTIME-QA.md`
records a one-off local Pebble check of HTTP-01 and TLS-ALPN-01 with the
production Caddyfile and the recorded runtime QA results. Production backup
activation, host verification and real certificate issuance remain F evidence.

## Integration Change

Expected:

- unit tests around adapter boundaries
- integration tests when a local or test service is available
- mocked failure cases
- documented manual verification if full integration testing is not possible

## Forecasting Snapshot And Detached Calculation Harness

Forecasting snapshot tests use the existing prediction API fixtures for
representative normal and derived targets. Prepare with
`prepare_prediction_snapshot`, close the preparation Session, round-trip with
`PredictionInputSnapshot.model_dump_json` and `model_validate_json`, then call
`calculate_prediction` without a Session. Source rows may be changed or soft-
deleted between preparation and calculation to prove the frozen observation,
formula, short-name and provenance boundary. Publish separately with
`publish_prediction` when transaction-wide persistence behavior is under test.

The PostgreSQL integration test creates and drops a unique schema in the same
disposable database used by migration integration tests. It commits a source
edit between preparation queries and proves that PostgreSQL `REPEATABLE READ`
keeps the full prepared input on one database snapshot:

```bash
cd backend
MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten \
  uv run pytest tests/test_predictions_postgresql_integration.py -v
```

When `MIGRATION_TEST_DATABASE_URL` is absent, this module is skipped. A skipped
run is not evidence for TASK-057B's consistent-preparation acceptance criterion;
run it against a disposable PostgreSQL database before review.

## Durable Prediction Request And Worker Harness

SQLite API tests cover request summaries, organisation scoping, authorization,
CSRF/Origin enforcement, audit actors, idempotent queued cancellation and
saved-version regressions. PostgreSQL is required for queue/name locks, FIFO
claiming, worker exclusivity, recovery and publication/cancellation behavior.
The worker integration harness uses a real spawned child process; prompt
cancellation uses a deliberately blocked child and verifies termination and
reaping within five seconds.

Run the disposable PostgreSQL suites together:

```bash
cd backend
MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten \
  uv run pytest tests/test_migrations_integration.py \
    tests/test_predictions_postgresql_integration.py -v
```

The tests create and drop unique schemas. They cover migration preservation and
down scope, lifecycle constraints, frozen submission inputs, global lock/FIFO,
blocked-child cancellation, crash/publication rollback and abandoned-request
recovery. An absent `MIGRATION_TEST_DATABASE_URL` skips this evidence and does
not satisfy TASK-057C integration acceptance.

## Prophet And Model Selection

TASK-061B's SQLite API tests cover the default six-kind selection, subsets
(including baseline-only and no-baseline subsets, with unselected fitted models
patched to fail if called), `422` for empty, duplicate and unknown `modelKinds`,
derived metrics with a subset, legacy snapshots without `modelKinds`, the
110,000-point limit, recorded Prophet configuration, deterministic Prophet
points and bounds, zero-variance regressor dropping, and fixed Prophet failure
reasons. The CmdStan failure test makes `cmdstanpy` raise its own optimisation
`RuntimeError` by skipping the CmdStan run; any other `RuntimeError` must fail
the calculation.

`tests/test_prediction_worker.py` needs no database. It starts real spawned
children through the supervisor and uses Linux `/proc` to verify the child's
own process group, its private `/tmp` directory, stopping before `os.setsid()`,
stopping a child with a running grandchild, a crashed child whose grandchild is
still running, and stopping during a real Prophet MCMC fit with no CmdStan
process or temporary directory left within five seconds. The Prophet stop test
waits for a member of the child's group running the CmdStan model binary,
`prophet_model.bin`, before it checks the private temporary directory, because
matplotlib's font cache rebuild runs `fc-list` in the same group first. It
stops the child in `finally`, so a failed assertion does not leave CmdStan
sampling and pytest waiting for the child at exit. The PostgreSQL suites above
add six-kind and subset publication, a legacy queued snapshot, migration 016
up/down and per-child directory removal in the worker cycle.

TASK-061C's frontend tests cover the six-kind default request, a canonical-order
subset that keeps preflight, blocked submission with no model, a create-time
validation message, the predictions client's safe error text for `detail` and
error-envelope payloads, a Prophet line style and interval band (none without
an available interval), label mapping, recorded and legacy-fallback version
models, and the chart's missing-results and not-run notes for versions that ran
a subset. Run `pnpm lint`, `pnpm test` and
`pnpm build` from `frontend/`.

TASK-062's frontend tests cover two consecutive preflight-and-queue cycles that
send the same manual seasonal period when the second preflight reports a
manual source, a period dropped when preflight no longer lists the metric or
returned to automatic detection after the input is cleared, the editable
manual input (not the automatic label) for a manual-source metric, blocked
creation for a missing or below-2 manual period, and rounded prediction hover
values with unchanged point, line and band geometry and unrounded Reality hover
values. `predictionChart.test.ts` covers
the display formatter for integers, one and two decimals, rounding, grouping,
negatives, integers ending in zero, exponent notation and `-0`.

TASK-063B's SQLite API tests in `tests/test_predictions_api.py` use a
12-observation monthly history whose automatic seasonality is inconclusive.
They cover preflight for a selection without seasonal-naive or SARIMA, which
is `eligible` with a null period and source and
`requiresManualSeasonalPeriod: false`, with and without a sent manual period.
A manual period that such a selection ignores is still validated: a blank
metric key or a period below 2 returns `422` for preflight and creation, and no
request is stored. They cover `requires_manual_seasonal_period` with the existing reason for
`seasonal_naive` alone and `sarima` alone. A created non-seasonal version gets
`available` results for every selected kind, and the response, the persisted
target and the frozen snapshot all record a null period although a manual
period was sent. The no-observations reason is checked for both selection
classes. The existing inconclusive-target test now includes SARIMA in its
selection, so it still covers target-level ineligibility for every selected
kind.

TASK-063C's frontend tests in `PredictionsTab.test.tsx` cover a non-seasonal
selection that shows no manual period input and no automatic period text while
every row keeps its status and reason, including the no-observations
ineligibility reason; the manual input and automatic period for seasonal-naive
alone and SARIMA alone; preflight kept by a same-class model change (including
an empty selection after a non-seasonal preflight) and cleared by a change
between classes; `manualSeasonalPeriods: {}` in preflight and creation without
a seasonal-period kind, with creation not blocked by a hidden missing period;
an entered period kept while hidden and sent again after SARIMA is reselected
and preflight is re-run; and invalid periods (`1`, `2.5`) dropped while valid
ones are kept when a request-field or class change clears preflight, so the
next preflight succeeds. The TASK-062 creation-block test also blocks a shown
`2.5` period with the form's whole-number message. They also cover every queue
form field, including the manual period input, disabled while preflight or
queueing runs and enabled again after either succeeds or fails. A same-class
subset test sends Naive and SARIMA with their manual period. `predictions.test.ts` covers
`selectionUsesSeasonalPeriod`.

TASK-064's frontend tests in `PredictionsTab.test.tsx` cover legend line
samples that carry each series' colour and dash pattern (dashed and solid) and
the thicker Current Reality style; y-axis range labels rounded like prediction
hover values when interval bounds or Current Reality set the range; hover text
rows for a point with an interval, without one, for Current Reality and for a
dense line sharing its first point with a sparse line; and a point listing an
identical series without an interval and a series closer than the dot radius
with its own value, but not a series on the same date far enough away to hover
separately. `predictionChart.test.ts` covers `predictionPointTitles`: line
order, differing value and interval notes, unrounded Reality values, and a dot
exactly the radius away or on another date being excluded.

Run assembled local browser and container QA separately with
`docs/qa/PREDICTION-WORKER-RUNTIME-QA.md`. Record unavailable Docker, browser,
Coolify-provider or production checks as unavailable, never as passing.

## Security-Sensitive Change

Expected:

- tests for authorization checks
- tests for invalid input
- tests for forbidden access
- regression tests for the security boundary

Examples:

- authentication
- authorization
- permissions
- tenant or organization boundaries
- file upload
- SQL or query construction
- secrets handling

## Authentication Harness

Backend authentication tests run entirely in process. `tests/test_auth_api.py`
uses a fake discovery/token boundary with SQLite persistence to cover browser
binding, one-time callback consumption, identity linking, opaque sessions,
timeouts, CSRF/Origin, Host/proxy trust and rate limits.
`tests/test_auth_provider.py` generates an ephemeral RSA key and signs ID tokens
for Authlib validation tests; it does not use real provider credentials or the
network. Pytest sets `APP_ENV=test` in `tests/conftest.py`; non-test application
startup still requires complete OIDC configuration.

Business API tests use `tests/auth_helpers.py` to create real test-only User and
AuthSession rows and configure the TestClient cookie, Origin and CSRF headers.
Production dependencies remain enabled. `tests/test_api_authorization.py`
covers the anonymous route matrix, Users role matrix, unsafe-request matrix,
session revocation, inactive-session rejection, broad cross-organisation access
and audit actors for every mutation family.

Frontend authentication tests mock Schatten's application-session endpoints:
`GET /api/v1/auth/session` and `POST /api/v1/auth/logout`. They do not mock or
expose Entra, Authentik, OIDC codes, provider tokens or provider claims. The
shared request-helper tests cover same-origin credentials, memory-only CSRF
headers, global `401` invalidation and non-invalidating `403` responses. UI
tests cover restoration loading, protected routes, role-aware Users navigation,
logout and user-session revocation. They also cover where the session controls
appear: on workspace routes the user name, role and the single Sign out button
are in the workspace header and the separate session bar is not rendered; the
home and 404 pages keep the session bar; and logout from the workspace header
shows the signing-out state and sends the CSRF header.
`src/App.workspace-fallback.test.tsx` replaces the Workspace module with a
stand-in that stays suspended or fails, and checks that the session bar and
Sign out stay available while the workspace route is loading or has failed.

Run the focused suite with:

```bash
cd backend
uv run pytest tests/test_auth_api.py tests/test_auth_provider.py -v
```

## MCP OAuth Authorization Harness (TASK-069E)

`tests/test_mcp_oauth_authorize.py` builds the app with `MCP_ENABLED=true`
over SQLite and covers the discovery documents, registration (redirect URI
allowlist, `client_name` ASCII allowlist, metadata bounds, public clients
only, cleanup before the client cap), authorize validation and its shown or
redirected errors, pending request caps, consent lookup, approve and deny
with CSRF/Origin, single decision, expiry, the separate `oauth_rate_limiter`,
the `MCP_ENABLED=false` 404s and `features.mcp`, and log redaction.
`tests/test_api_authorization.py` builds the app with default settings and
with `MCP_ENABLED=true`, so the sweep covers the MCP-gated `/api/v1/ai/*`
routes.

Row locks need PostgreSQL. `tests/test_mcp_oauth_postgresql_integration.py`
pauses a real authorize after its `FOR NO KEY UPDATE` client lock and checks
that `SKIP LOCKED` cleanup skips the client without waiting, that a grant
insert for the same client does not wait, and that authorize waiting behind a
cleanup soft delete fails as an invalid client and stores nothing. It also
pauses an authorize after its pending caps to check that the total cap's
advisory lock makes another client's authorize wait and then refuse, and that
a NUL `client_id` or `state` is rejected before it reaches PostgreSQL. It is
skipped without `MIGRATION_TEST_DATABASE_URL` and always runs in CI:

```bash
cd backend
uv run pytest tests/test_mcp_oauth_authorize.py -v
MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten \
  uv run pytest tests/test_mcp_oauth_postgresql_integration.py -v
```

## Local Direct-Entra Integration

Use the local Caddy/direct-Entra configuration rather than the historical
Authentik commands below. The automated boundary is simulated OIDC plus the
disposable local configuration check, so it requires no tenant credentials:

```bash
scripts/verify-local-direct-entra-config.sh /path/to/base.env /path/to/private-entra.env
cd backend
uv run pytest tests/test_auth_api.py tests/test_auth_provider.py \
  tests/test_config.py tests/test_provision_local_admin.py -v
```

The configuration check covers loopback ingress, no Authentik services, exact
HTTPS origin, secure cookie setting, direct Entra claim policy, fixed Caddy peer
and leaf-only certificate mount. The backend suite covers exact issuer, missing
email, no `email_verified` dependency, guarded first linking, existing identity,
sessions, CSRF, logout, spoofed forwarded headers and callback-log redaction.
The local provisioning tests cover seeded/populated database preservation,
validation, conflicts and deleted users without identities, sessions or role
changes.

An authorized browser run against the designated tenant account is separate
evidence. Record it as pending until setup exists; mock tests do not pass it.

## Historical Local Authentik Integration

The commands and results in this retained historical section are superseded and
must not be run against the current Compose runtime.

TASK-039E:n Authentik-tarkistukset käyttävät `.env.authentik.local`-tiedostoa,
joka sisältää vain paikallisia salaisuuksia ja salted password hasheja. Luo se
ensin ja validoi renderöity Compose. Tarkistusskripti käyttää samaa kerrostusta
kuin runtime: `.env` ensin ja `.env.authentik.local` sen jälkeen.

```bash
scripts/setup-local-authentik.sh
scripts/verify-local-authentik-config.sh
docker compose --env-file .env --env-file .env.authentik.local config --quiet
```

Fresh-volume bootstrap pitää ajaa eksplisiittisellä disposable project namella.
Pysäytä mahdollinen normaali identity stack ensin, jotta loopback-portti 9443
vapautuu. Seuraava teardown poistaa vain
`schatten-authentik-bootstrap-test`-projektin kontit, networkin ja nimetyt
volumet; se ei kohdista normaaleihin `schatten_*`-volumeihin:

```bash
docker compose --env-file .env --env-file .env.authentik.local stop authentik-tls authentik-worker authentik-server authentik-database
scripts/setup-local-authentik.sh /tmp/schatten-authentik-bootstrap-test.env
docker compose \
  --project-name schatten-authentik-bootstrap-test \
  --env-file .env \
  --env-file /tmp/schatten-authentik-bootstrap-test.env \
  up -d --wait authentik-database authentik-server authentik-worker authentik-tls
scripts/smoke-local-authentik.sh
docker compose \
  --project-name schatten-authentik-bootstrap-test \
  --env-file .env \
  --env-file /tmp/schatten-authentik-bootstrap-test.env \
  down --volumes
rm /tmp/schatten-authentik-bootstrap-test.env
```

Käynnistä tämän jälkeen normaali full stack, aja migraatiot ja dev seed
`docs/LOCAL-DEVELOPMENT.md`:n komennoilla. Manual browser QA:

- avaa `http://app.localhost:5173/api/v1/auth/login` ja kirjaudu
  `schatten-consultant`-tunnuksella
- varmista `/api/v1/auth/session`-vastauksesta consultant-käyttäjä ja
  Schattenin tietokantarooli
- kirjaudu ulos `POST /api/v1/auth/logout` -flow'n kautta ja varmista sekä
  local sessionin että selainevästeen poistuminen
- toista `schatten-admin`-tunnuksella ja varmista admin-rooli
- yritä kirjautua `schatten-unmatched`-tunnuksella; odota geneeristä virhettä ja
  varmista, ettei `users`- tai `user_identities`-riviä luotu
- tarkista selaimen storage/cookie-näkymästä, että `app.localhost` ei lähetä
  Schatten-cookieita `auth.localhost`-hostille eikä päinvastoin

Token-claimien tarkistus tehdään Authentikin provider previewlla tai rajatulla
kertakäyttöisellä testiclientillä: vaadi `sub`, `name`, `email` ja
`email_verified=true`; varmista ettei tokenissa ole `groups`, `roles`, `oid` tai
`tid`. Älä lokita tai tallenna oikean browser-flow'n authorization codea,
tokeneita, cookieita tai salasanoja.

Optional local Entra federation tarkistetaan lisäksi näin:

```bash
scripts/setup-local-entra.sh
scripts/verify-local-entra-config.sh
docker compose \
  --env-file .env \
  --env-file .env.authentik.local \
  --env-file .env.entra.local \
  -f docker-compose.yml \
  -f docker-compose.entra.yml \
  up -d --wait database authentik-database authentik-server authentik-worker authentik-tls
uv run --env-file .env --project backend python backend/migrate.py up
scripts/provision-local-entra-user.sh
docker compose \
  --env-file .env \
  --env-file .env.authentik.local \
  --env-file .env.entra.local \
  -f docker-compose.yml \
  -f docker-compose.entra.yml \
  up -d --wait
scripts/smoke-local-authentik.sh
```

Browser QA:ssa vaadi matching-email login, Schattenin tietokantarooli, logout
ja unmatched Entra emailin geneerinen failure. Tarkista DevToolsista ettei
provider tokenia ole URL-fragmentissa, web storagessa, cookieissa tai Schattenin
API-vastauksissa. Tarkista Caddy-, Authentik- ja backend-lokeista, etteivät
client secret, code, token, cookie, CSRF-arvo tai henkilökohtainen email näy.
Tuloksiin kirjataan vain päivä, commit, testaaja ja pass/fail.

Lopuksi aja backendin auth-harness ja normaalit baseline-tarkistukset. Local
provider tai local federation ei korvaa human-approved limited direct-Entra
production smokea:

```bash
cd backend
uv run pytest tests/test_auth_api.py tests/test_auth_provider.py -v
uv run ruff check .
uv run pytest
uv run pyright
```

---

# Testing Structure Feature

Structure feature changes may touch both backend graph APIs and frontend graph
editing UI. Choose checks based on the changed layer.

Backend Structure API checks:

```bash
cd backend
uv run ruff check .
uv run pytest tests/test_org_twin_structure_api.py -v
uv run pyright
```

Run the full backend pytest suite when shared service behavior, database models
or scenario/org-state interactions change:

```bash
cd backend
uv run pytest
```

Frontend Structure UI checks:

```bash
cd frontend
pnpm lint
pnpm test -- StructureTab GraphViewer
pnpm build
```

Run the full frontend test suite when shared API client, workspace selection or
tab rendering behavior changes:

```bash
cd frontend
pnpm test
```

Manual QA:

- Use `docs/qa/STRUCTURE-QA-CHECKLIST.md` for end-to-end graph, node, edge,
  filtering, zoom and position update verification.
- Record manual QA results in the PR when visual graph behavior or drag
  interactions are changed.

Authorization note:

- Structure authorization and permission enforcement are out of scope for the
  TASK-025A/TASK-025B baseline and should be tested with the dedicated
  authorization follow-up task.

---

# Testing Summary Feature

Summary changes combine graph history, events and timeseries on a shared date
axis, so test the pure timeline model separately from component interactions.

Backend Summary and temporal graph checks:

```bash
cd backend
uv run ruff check .
uv run pytest tests/test_org_twin_structure_api.py -v
uv run pyright
```

Cover organisation/scenario ownership, stable ids, persistence soft-delete
exclusion, inclusive logical lifetime projection, connected-edge end dates and
invalid lifetime rejection.

Frontend Summary checks:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Pure helper tests cover malformed dates, bounds, ordering, filtering, row and
month label formatting, adaptive year-only headers, chart scales and zoom limits. Component tests cover concurrent cancellable loading,
stale response prevention, states and retry, row rendering, hover details,
filters, mutually exclusive popovers, row visibility and collapsing, zoom scale
feedback, zoom-to-fit, scrolling and shared timeseries row resizing.

Manual QA:

- Use `docs/qa/SUMMARY-QA-CHECKLIST.md` for the scenario-scoped timeline,
  Structure lifetime behavior and visual interaction checks.

---

# Predictions Chart Comparison (TASK-055)

Prediction charts retain every displayed point while thinning date labels to
at most 22, at least 36 SVG units apart, including both endpoints. Year guides
remain independent of date labels; colliding year captions are omitted. Each
line hides visible dots at 100 filtered points but retains hover details.
Units appear inside the white graph area above the plot.

Each metric defaults to the earliest start and latest end of its selected
versions in selected scenarios. Plot start/end inputs independently override
these inclusive bounds for both predictions and live Reality. Reality empty
messages appear only after a successful fetch; a matching numeric series with
no displayed observations has a different message from a missing series.

Manual/visual QA at desktop and narrow viewport widths:

- Compare 23, 100 and 365 dates across a year boundary; check date/year labels,
  endpoints, unit placement, complete lines and interval bands.
- Compare sparse and dense prediction/Reality lines together; filter a dense
  line below 100 points and confirm dots return. Hover to inspect dated values,
  units, provenance and available interval bounds.
- Enable Reality with dates before, within and after the forecast period.
  Confirm overlapping values render and outside values do not stretch the
  default range. Expand either plot bound, then toggle Reality off.
- Select overlapping versions, change scenario/metric selections, and verify
  per-metric ranges. Check missing-series, no-observation, loading and failed
  request states without mistaking an empty result for a fetch failure.

Run `pnpm lint`, `pnpm test` and `pnpm build` from `frontend/`.

---

# Prediction Request UI (TASK-057D / TASK-058)

Frontend client and component tests cover the `202 Accepted` request summary,
state labels, active/history separation, queue ordering, cancellation outcomes,
safe failure reasons, idle polling and non-overlapping polling. Use controllable
responses and fake timers for polling, cancellation/completion races and stale
organisation responses. Preserve the saved-version comparison selections when a
request completes; only work submitted from the current tab is auto-selected.

TASK-058 component/helper coverage adds zero-to-three history records without a
disclosure, expansion through the returned 50 records, collapse, poll stability,
organisation reset, and preservation of every active action. With a fixed clock,
verify all six lifecycle states, semantic `time` source values, explicit missing
stages, completed elapsed minutes, sub-minute and negative-clock cases, and
hour/day and daylight-saving boundaries. Derive local timestamp expectations
with explicit year/month/day/hour/minute `Intl.DateTimeFormat` options so tests
do not depend on the runner's timezone.

Exercise several newest-first local notices, terminal updates from list, detail
and cancellation responses, safe failure text, status/alert roles, individual
dismissal, and organisation/unmount clearing. Observe live-region DOM mutations
to ensure unchanged polls and running/stopping states do not re-announce queued
notices. Discovered requests must not create notices. Resolve a locally submitted
request omitted from the capped list through detail, including after dismissal,
and verify saved-version refresh/selection and retry after a refresh failure.
Use deferred responses to cover non-overlapping detail fetches, cancellation
races, stale organisation results, visibility abortion and unmount cleanup.

Manual browser QA:

- Queue two uniquely named predictions and verify the form is immediately
  available for the second request.
- Verify queued removal, running Stop, the Stopping state and a completion that
  wins a cancellation race. Confirm Stop explains that calculated output is
  discarded.
- Reload, leave and return to the tab, and switch organisation; accepted work
  must remain server-side and request summaries must refresh without stale rows.
- Verify another user's requests appear while this tab is idle, polling errors
  retain the last-known state, and completed saved versions do not reset an
  existing comparison. A current-tab completion should be selected.
- With four or more finished requests, use keyboard activation of Show more /
  Show less and check `aria-expanded` and its controlled history list. Polling
  must preserve expansion; switching organisation must collapse it.
- Check request cards at narrow widths, including long names, lifecycle labels
  and cancellation actions. Compare queued/start/finish times to the browser's
  local timezone and confirm ongoing elapsed minutes advance on polling.
- Submit several requests, verify separate notices and terminal transitions,
  then dismiss them individually using their named keyboard-accessible controls.
  Check informational status versus failed alert announcements with a screen
  reader. Dismissed notices must stay dismissed; navigation/reload and an
  organisation change clear all notices.

Run `pnpm lint`, `pnpm test` and `pnpm build` from `frontend/`. Full worker and
container browser QA is owned by TASK-057E.

---

# Frontend Async Component Tests (TASK-065)

A `findBy*` query returns as soon as its element is in the DOM, and `waitFor`
as soon as its callback passes. React may still run effects and follow-up
renders afterwards, in an order that varies under load. In frontend component
tests:

- After a `findBy*` query, wait with `findBy*` or `waitFor` for the specific
  element, text or request that the next assertion depends on, for example the
  first row instead of its list container.
- After waiting for a mutation call, such as a delete or cancel request, wait
  for the UI that its response updates instead of checking it synchronously.
- Do not count or check requests made by child effects right after waiting for
  a parent element; wait for the requests themselves. An empty state can render
  before its load effect has started.
- Keep deliberate synchronous checks, such as a control being disabled while a
  request is pending, but make them only after the prerequisite UI is present.
- Restore spies, such as a silenced `console.error`, in `afterEach` with
  `vi.restoreAllMocks()`, not at the end of the test, so a failing assertion
  does not leave them active.

TASK-065 applies this to the application-wide Customers route test, which waits
for the customer list, address and contact requests; to Customers, Summary,
Users and Metrics tab tests that query rows, edit forms, counts or timeline text
loaded after the awaited element; and to event deletion, user deletion, session
revocation, prediction cancellation and preflight tests that check the UI
updated by a response.

---

# Test Levels

Use the lightest useful test level.

## Unit Tests

Use for:

- pure logic
- validation
- domain rules
- formatting/parsing
- small service functions

Frontend unit tests use Vitest.

Backend unit tests use pytest.

Frontend linting uses ESLint.

Backend linting uses Ruff.

## Integration Tests

Use for:

- API endpoint behavior
- database reads/writes
- cross-module flows
- adapter boundaries

## End-to-End Tests

Use only for critical user flows.

Examples:

- registration
- login
- document upload
- payment or billing flow
- permission-sensitive workflow

Do not add broad E2E coverage by default. Keep E2E tests focused.

## Manual Verification

Manual verification is acceptable when:

- the project has no test stack yet
- the behavior is visual
- external systems are not available locally
- the change is documentation-only

Manual verification must be described in the PR.

---

# Task Testing Section

Every task should include a `Testing` section.

Use this shape:

````markdown
## Testing

Required:

- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Build
- [ ] Lint

Not applicable:

- [ ] Reason:

Commands:

```bash
# Frontend, if applicable
cd frontend
pnpm format:check
pnpm lint
pnpm test
pnpm build

# Backend, if applicable
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```
````

If tests are not added, explain why.

---

# AI Agent Instructions

When implementing a task, the AI-agent must:

1. identify what behavior changed
2. decide what test level is appropriate
3. add or update tests when the change touches application code
4. run available test commands
5. report the exact commands and result
6. explain if tests were not added or could not be run

Use this prompt addition:

```text
Lisää tai päivitä testit muutoksen riskin mukaan.
Jos et lisää testejä, perustele miksi.
Aja saatavilla olevat testikomennot ja raportoi tulokset.
```

---

# When Scaffolding Is Missing

ADR-001 has selected the stack, but the repository may not yet have runnable `frontend/` or `backend/` scaffolds.

In that case:

- do not invent scripts outside the task scope
- do not add dependencies without approval
- document what should be tested later
- perform available static or manual checks
- report that automated tests are not yet configured in the affected package

---

# CI Expectations

Current baseline CI checks repository documentation structure.

CI runs the repository baseline checks and backend checks. The backend job also
starts PostgreSQL 18 and supplies `MIGRATION_TEST_DATABASE_URL`, so migration
integration tests cannot be silently skipped. As application coverage grows, CI
should run:

```text
Install
Format check
Lint
Tests
Typecheck
Build
```

The exact commands must be documented in:

- `README.md`
- `docs/LOCAL-DEVELOPMENT.md`
- this file
- `.github/workflows/ci.yml`

---

# PR Expectations

Every PR must state:

- what tests were added or updated
- what commands were run
- whether manual verification was done
- why tests were not added, if not applicable

PRs that change application behavior without tests or a clear reason should not be approved.
