# TASK-059H3 Server Makefile, Service Command And Runbook

## Source Plan

[TASK-059H](TASK-059H-github-source-delivery-architecture.md) and its approved
ADR-013 amendment; depends on
[H1](TASK-059H1-source-manifest-git-free-build.md) and
[H2](TASK-059H2-upload-account-deploy-action.md). The product owner asked for
`make` commands on the server for building, stopping, logs and similar tasks.

## Goal

Give operators short `make` commands over the existing `deploy/bin` tooling
and bring the runbook and deployment documentation in line with the git-free,
Action-delivered source path, so TASK-059F can follow it end to end.

## Requirements

- `deploy/Makefile`, run from the verified source copy
  (`make -C /opt/apps/schatten-sources/<commit>/deploy <target>`), never from
  the upload folder. Receiving runs the installed
  `/usr/local/bin/schatten-receive <digest>` directly, because the verified
  copy does not exist before it; the Makefile has no receive target. Thin
  wrappers only: `help`, `check`,
  `audit`, `build`, `deploy RELEASE= APPROVAL=`, `first-install RELEASE=
  APPROVAL=`, `status`, `ps`, `logs [SERVICE=]`, `stop`, `start`, `backup`,
  `restore BACKUP= KEY= [PASSPHRASE=]`, `cleanup-dry-run`. Required variables
  fail with a usage message. No target runs `down -v`, prunes, deletes volumes,
  runs down migrations, restores production or bootstraps implicitly.
- `deploy/bin/service ps|logs [service]|stop|start` for the current release
  through `compose_release`; `stop`/`start` keep containers and volumes;
  logs never include `docker compose config` or environment output.
- Root `Makefile`: keep its rule that production commands are not in it; point
  its help text to `deploy/Makefile`.
- Update from the TASK-059E versions:
  - `docs/PRODUCTION-RUNBOOK.md`: 0 (tooling runs from the verified source
    copy); 1.2 findings table (remove "install Git"; "SSH from Anywhere" is
    accepted; attention if `deploy` is not source-restricted or SSH is not
    public-key only); 2.1 (the hardening file sets `PasswordAuthentication no`,
    `KbdInteractiveAuthentication no`, `PermitRootLogin no` and
    `AllowUsers deploy@<operator-cidr> schatten-upload`, validated with
    `sshd -t` and `sshd -T` in a kept-open session and confirmed before UFW
    opens 22 to anywhere); 2.2 (upload account and folder,
    `/opt/apps/schatten-sources`, installing `upload-gate` and
    `schatten-receive` from the approved commit via an operator workstation
    before the first upload and confirming by `sha256sum` after the first
    receive that they equal the manifest entries, GitHub `production` environment and five secrets,
    host fingerprint from `ssh-keygen -lf`), including the first-install order
    of `upload-gate`/`schatten-receive` from an operator workstation and the
    reinstall step when a manifest changes them; 3 (run the Action, confirm the
    run's workflow, event, branch and commit, copy the digest, run the installed
    receiver, `build`); 4-5 with `make` equivalents; 13 verification status;
  - `deploy/bin/audit-host`: upload account (locked, no sudo/docker/adm, keys
    with `restrict` and the gate as forced command, counts only),
    `AllowUsers`, upload folder, `/usr/local/bin/upload-gate` ownership;
    flag SSH from Anywhere only if password, keyboard-interactive or root
    login is still enabled, otherwise stop flagging it;
  - `docs/DEPLOYMENT.md` (commands, storage, remaining setup, source path),
    `docs/TESTING.md` (Makefile/service tests, `audit-host` expected findings,
    the Ubuntu 26.04 operator image without git), `AGENTS.md`,
    `ARCHITECTURE.md` and `README.md` status lines,
    `.github/workflows/ci.yml` (shellcheck and required files).
- Keep `docs/qa/UPCLOUD-RUNBOOK-QA.md` and `docs/qa/PRODUCTION-RUNTIME-QA.md`
  unchanged as historical evidence; add a TASK-059H QA record for H1-H3 results.

## Acceptance Criteria

- [ ] Every Makefile target maps to an existing `deploy/bin` command or
      `service`, fails clearly on missing variables and contains no
      destructive operation.
- [ ] `service` stop/start/ps/logs work on the disposable runtime without
      removing containers or volumes or printing secrets.
- [ ] The runbook covers tool bootstrap -> Action -> run check -> digest ->
      receive -> build -> deploy with no
      git, deploy key or checkout on the server, and 059F can follow it.
- [ ] `audit-host` reports the upload account, gate, `AllowUsers`, public-key-
      only SSH settings and upload folder as specified, tested in the disposable Ubuntu 26.04 baseline
      container.
- [ ] Links and anchors resolve; historical QA records are unchanged.

## Out Of Scope

- Any host, GitHub or provider change and the first real run (F).
- Building on GitHub, GHCR or automatic deployment.

## Implementation Notes

- The harness (`.github/scripts/verify-production-runtime.sh`) should drive
  `receive`, `build`, `deploy`, `ps`, `logs`, `stop` and `start` through the
  Makefile for one release, with git absent from the server-side `PATH`.

## Testing

Required:

- [ ] Integration tests: disposable runtime harness through the Makefile.
- [ ] Manual verification: `audit-host` in the Ubuntu 26.04 baseline container;
      link check.
- [ ] Lint: shellcheck.

Not applicable:

- [x] Frontend/backend tests, typecheck, build: no application code changes.

## Documentation

As listed in Requirements. Record eventual Step 13 reviews under
`docs/ai-reviews/TASK-059H3/`.
