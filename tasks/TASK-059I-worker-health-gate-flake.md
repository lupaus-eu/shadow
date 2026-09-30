# TASK-059I Worker Health Gate Flake

## Source Plan

Developer-approved fix after the CI `production-runtime` job passed on the last
TASK-059H3 commit but failed on `main` after the merge (same tree, 66a51a8):
the standard release of the second build in
`.github/scripts/verify-production-runtime.sh` stopped with
`prediction-worker did not become healthy (state running/unhealthy)` about six
seconds after the deployment started.

## Goal

Make the release health gate tolerate a transient, load-induced unhealthy
worker status without weakening the gate for a service that really stays
unhealthy or exits, and make the next such failure self-explaining.

Cause:

- `build-release` is reproducible (`SOURCE_DATE_EPOCH`), so a second build of
  the same source has the same image IDs. `compose up` keeps the unchanged
  worker container and the gate inspects the old container.
- The worker probe is a cold Python start plus a database connection with a
  3 s timeout. While the second build loaded the runner, probes timed out and
  the unchanged container was already `unhealthy` when the deploy began.
- `wait_for_healthy` failed on the first `unhealthy` sample, although Docker
  health returns to `healthy` on the next passing probe.

## Requirements

- Production worker healthcheck: `timeout: 10s`, `start_period: 30s`; the probe
  command, interval and retries stay unchanged.
- `deploy/lib/common.sh` `wait_for_healthy`: fail at once when the container
  exits; fail on `unhealthy` only after it persists for longer than Docker's
  worst-case recovery (interval + timeout, 20 s for the worker): 15 consecutive
  samples of at least 2 s; a non-unhealthy sample resets it.
- On failure, log the recorded probe exit codes and times only, never probe
  output, because it could echo configuration.
- `.github/scripts/verify-wait-for-healthy.sh` runs `wait_for_healthy` with
  stubbed `docker`, `compose_release` and `sleep` in CI `production-runtime`;
  `verify-production-compose.sh` pins the worker healthcheck timings.

## Acceptance Criteria

- [x] A transient unhealthy status that recovers passes the gate.
- [x] Persistent unhealthy and exited containers still fail the gate and log
  the probe exit codes (`-1` is a Docker probe timeout).
- [x] `verify-production-compose.sh` and `verify-wait-for-healthy.sh` pass.
- [ ] CI `production-runtime` passes, including the forced-unhealthy frontend
  "may be partly running" check.

## Out Of Scope

- Worker health semantics (`worker_is_healthy`) and the development
  `docker-compose.yml`.
- Force-recreating unchanged containers on deploy.

## Testing

Not applicable: backend/frontend tests (no application code change).

Commands:

```bash
bash -n deploy/lib/common.sh
bash .github/scripts/verify-production-compose.sh
bash .github/scripts/verify-wait-for-healthy.sh
bash .github/scripts/verify-production-runtime.sh   # CI production-runtime
```

## Documentation

No runbook or deployment document describes the probe timings or the gate's
abort timing; no documentation change.
