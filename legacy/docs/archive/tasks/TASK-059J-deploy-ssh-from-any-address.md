# TASK-059J Deploy SSH From Any Address

## Source Plan

Developer-requested amendment (2026-10-01) before TASK-059F applies runbook
section 2.1. The operators who use `deploy` (the developer and the product
owner, each with an own key on the shared `deploy` account) connect from
dynamic addresses and changing networks, and one operator's addresses are not
known. `AllowUsers deploy@<operator-cidr>` would lock them out whenever an
address changes.

Decisions recorded with the plan:

- **Allow `deploy` from any address.** The hardening drop-in sets
  `AllowUsers deploy root shadow-upload`. SSH stays public-key only:
  `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, locked
  passwords for all allowed accounts, fail2ban's `sshd` jail unchanged.
- **Keep direct root SSH, key only.** The product owner keeps their direct root
  login. The drop-in sets `PermitRootLogin prohibit-password` (never `yes`),
  which supersedes ADR-013's `PermitRootLogin no`. Root's password stays
  locked.
- **Accepted risk:** a stolen `deploy` or root private key can be used from
  anywhere and grants full control of the host. The amendment relies on
  operators keeping their private keys safe. The exposure of sshd itself is
  unchanged: TCP 22 is already open to anywhere for `shadow-upload`. Direct
  root sessions are less accountable than `deploy` with `sudo`, which logs each
  command; this is accepted.
- **Recovery access:** initially it is sufficient that the product owner has
  access to the UpCloud account and has set up its authentication; the
  developer may be granted access later. Recovery uses UpCloud's procedures
  below, not a pre-set console password; ADR-013's locked passwords stay.
- Hardware-backed (FIDO2) keys or a VPN overlay remain possible later
  hardening and are not part of this task.

Observed during the read-only host inspection (2026-10-01, before F): the main
`/etc/ssh/sshd_config` sets `PermitRootLogin yes`; password and
keyboard-interactive authentication are effectively `no`; root and `deploy`
passwords are locked; root has one authorized key without cloud-init's
`disable_root` prefix; root password/keyboard-interactive SSH is refused
(`Permission denied (publickey)`); the product owner logged in successfully as
root with their key, so the single root key is theirs. These are inputs for F,
not F evidence.

The product owner does not take part in the rollout, so a root key login is
**not required F evidence**. F verifies root access without the root key: the
effective `sshd -T -C user=root,...` settings (`permitrootlogin
prohibit-password`, root admitted by `AllowUsers`, password and
keyboard-interactive off), the unchanged root key count without the
`disable_root` prefix, and a refused root password/keyboard-interactive login.
A root key login by the product owner after 2.1 is optional and recorded only
if it happens. If 2.1 ever breaks root SSH, it is repaired as `deploy` with
`sudo`, without downtime.

| Task | Deliverable | Dependency |
| --- | --- | --- |
| TASK-059J | ADR-013 amendment, `audit-host` change, runbook/docs, F record template | `main` (H1-H3, I merged) |
| [TASK-059F](TASK-059F-first-production-rollout.md) | Authorized setup and first rollout, applying 2.1 as amended | J merged and explicit operational approval |

## Goal

Replace the source restriction of `deploy` with public-key-only access from
any address, keep direct root SSH with keys only, record the accepted risk and
the recovery path, and keep `audit-host`, the runbook and the F record
consistent with it, before F changes SSH on the real host.

## Requirements

- Amend [ADR-013](../../adr/0013-shared-entra-local-https-deployment.md)
  with a dated amendment to *Source Delivery Without Git On The Server* /
  **SSH exposure**:
  - `AllowUsers deploy root shadow-upload`; `deploy` and root are reachable
    from any address with public-key authentication only; the previous
    `deploy@<operator-cidr>` restriction is superseded (a CIDR pattern remains
    an allowed, stricter operator choice for `deploy` or `root`);
  - `PermitRootLogin prohibit-password` supersedes `PermitRootLogin no`; root
    SSH exists for the product owner's direct login, not for tooling: the
    runbook, `deploy/bin` and the Makefile keep running as `deploy`; root's
    password stays locked;
  - the accepted risk, the reduced accountability of root sessions and why
    sshd exposure is unchanged;
  - operator key rules: one key per person with a role comment, never a shared
    key, on `deploy` and on root; passphrase-protected keys used through an
    agent; on a lost or suspected key, remove it from the affected
    `authorized_keys` (`deploy`'s or `/root/.ssh/authorized_keys`) immediately
    from another session or the recovery path; F records the key **counts** of
    `deploy` and root and the role holding each root key; a root key login
    is not required F evidence (the root key holder need not take part);
  - recovery access held through the UpCloud account (initially the product
    owner, authentication set up by them), recorded by role in F;
  - FIDO2 keys and a VPN overlay as possible later hardening;
  - update the ADR's status line and task table with J.
- Recovery path (ADR summary; full steps in the runbook):
  - **Regain any login without a password** with UpCloud's
    [disk-move password reset](https://upcloud.com/docs/guides/reset-root-password-cloud-server/):
    temporary server in the same zone, production server shut down, system
    disk detached, attached to the temporary server, password set via
    `chroot`, disk reattached, temporary resources deleted. It causes
    downtime: the site and scheduled backups stop. Take an UpCloud storage
    backup or snapshot of the disk first, because the application backups live
    on the same disk.
  - **Locked out by `AllowUsers`:** after the reset, log in on the UpCloud web
    console and correct the `AllowUsers` line in
    `/etc/ssh/sshd_config.d/10-shadow-hardening.conf` (a short edit that can
    be typed, since the console does not paste); validate with `sshd -t` and
    `sshd -T`, then reload.
  - **Lost `deploy` or root key:** while the disk is attached to the
    temporary server, add the new public key to
    `/home/deploy/.ssh/authorized_keys` or `/root/.ssh/authorized_keys` there,
    where pasting and `scp` work. No password SSH is enabled. While another
    allowed key still works, add the new key from that session instead; no
    downtime is needed.
  - **Afterwards** lock any password set by the reset again
    (`passwd -l <account>`) and rerun `audit-host`.
  - **Never** follow the step of UpCloud's
    [regaining-access guide](https://upcloud.com/docs/guides/regaining-access-to-a-server-that-was-deployed-using-ssh-keys/)
    that comments out `Include /etc/ssh/sshd_config.d/*.conf` and sets
    `PasswordAuthentication yes`: it disables the cloud-init and Shadow
    drop-ins, re-enables the main file's `PermitRootLogin yes` and allows root
    password login from anywhere while port 22 is public.
- `deploy/bin/audit-host` `[ssh]` section:
  - effective `permitrootlogin` `prohibit-password` (or its alias
    `without-password`) is `ok` ("root SSH key-only (ADR-013 059J)"); `yes`
    and `forced-commands-only` are attention; `no` is a fact (stricter than
    required);
  - SSH from `Anywhere` is the accepted exposure when password and
    keyboard-interactive login are off and root login is `prohibit-password`
    or `no`; `permitrootlogin yes` keeps it attention;
  - bare `deploy` and bare `root` in `AllowUsers` are `ok` ("admitted from any
    address, public-key only (ADR-013 059J)"); `deploy@<pattern>` and
    `root@<pattern>` entries are reported as a stricter fact, not attention;
    no `deploy` entry at all is attention; no `root` entry is a fact (root SSH
    shut out);
  - report root's authorized-key **count** and whether any root key carries
    cloud-init's `disable_root` prefix (counts only, no fingerprints or
    comments);
  - unchanged: missing `AllowUsers`, any account other than `deploy`, `root`
    and `shadow-upload`, missing `shadow-upload`, password and
    keyboard-interactive login, `Match` blocks;
  - when the main `sshd_config` sets `PermitRootLogin yes` but the effective
    value is `prohibit-password`, report it as a fact (overridden by the
    drop-in);
  - the `manual` provider-firewall line says TCP 22 from anywhere (IPv4, IPv6
    only if intended), TCP 80/443 public, nothing else, matching runbook 2.1.
- Update to the amendment:
  - `docs/runbooks/production.md`: introduction (`AllowUsers` line), 1.1
    (root: key login accepted, password and keyboard-interactive refused), 1.2
    findings table, 2.1 (drop-in with `PermitRootLogin prohibit-password` and
    `AllowUsers deploy root shadow-upload`, `sshd -T` expectations,
    a new-session check from any network for `deploy`, root verified by
    `sshd -T -C user=root,...`, its key count and a refused password login
    (a root key login is optional), recovery text with the steps above and the warning, the main
    file's `PermitRootLogin yes` being overridden by the `10-` drop-in), the
    statement that root SSH is not used for runbook commands, 13 verification
    status;
  - `docs/architecture/deployment.md`: cloud-init baseline checks and the `audit-host`
    tooling row;
  - `docs/architecture/overview.md` deployment section, `AGENTS.md` status lines;
  - `docs/operations/testing.md` `audit-host` expectations;
  - [TASK-059F](TASK-059F-first-production-rollout.md) requirements ("from an
    operator network" wording, recovery-access acknowledgement);
  - `docs/operations/qa/FIRST-PRODUCTION-ROLLOUT.md` template: 2.1 expectations
    (`permitrootlogin prohibit-password` and root admitted in
    `sshd -T -C user=root,...`, root password login refused, an optional root
    key login row that may stay "not performed"), a recovery row (UpCloud account access holder role and its
    authentication set up, acknowledged by role/date), the `deploy` and root
    key counts and the role holding each root key (the product owner, as
    reported before F; no participation needed to record it). The template
    exists only on the unmerged F branch, so J records these expectations as a
    TASK-059F requirement to apply after F rebases onto J (review F-001).
- Keep `docs/operations/qa/UPCLOUD-RUNBOOK-QA.md`, `docs/operations/qa/SOURCE-DELIVERY-QA.md`, the
  TASK-059H/H1-H3 specs and their review records unchanged as history; add the
  J results to `docs/operations/qa/SOURCE-DELIVERY-QA.md` as a new dated section only.

## Acceptance Criteria

- [ ] ADR-013 records `AllowUsers deploy root shadow-upload`,
      `PermitRootLogin prohibit-password`, the accepted stolen-key risk and
      root accountability, the operator key rules, the UpCloud recovery path
      and the warning against disabling the `Include`.
- [ ] `audit-host` reports `prohibit-password`, bare `deploy` and bare `root`
      as `ok`, `@<cidr>` patterns and `permitrootlogin no` as facts,
      `permitrootlogin yes` as attention, root key counts without key
      material, and keeps every other listed attention case, tested in the
      disposable Ubuntu 26.04 baseline container.
- [ ] Runbook 1.1/2.1, DEPLOYMENT, ARCHITECTURE, AGENTS, TESTING, TASK-059F
      and the F record template agree; no current document still requires
      `deploy` to be source-restricted or `PermitRootLogin no`.
- [ ] No host, GitHub, UpCloud or firewall change.

## Out Of Scope

- Applying 2.1, any change on the real host, UpCloud account setup or access
  grants (F and the product owner).
- FIDO2 keys, VPN overlays, bastion hosts, per-person operator accounts.
- Changes to the upload account, `upload-gate`, the workflow or UFW rules.

## Implementation Notes

Branch: `feature/TASK-059J-deploy-ssh-any-address` from `main`. Merging it is
the human approval of the amendment. Keep the amendment additive; all other
ADR-013 SSH settings, the upload boundary and GitHub-side controls are
unchanged. Expected size well under 500 reviewable lines.

## Testing

Required:

- [ ] Manual verification: `audit-host` in the disposable Ubuntu 26.04
      baseline container (TESTING.md) with the amended 2.1 drop-in: SSH lines
      `ok`; `deploy` and root accepted with a key from an address outside any
      former CIDR; password and keyboard-interactive refused for both;
      negative variants (another account in `AllowUsers`, no `deploy` entry,
      `PermitRootLogin yes` effective, password login re-enabled) are
      attention; no key material in the output.
- [ ] Manual verification: `sshd -T` shows the drop-in's `prohibit-password`
      overriding a main-file `PermitRootLogin yes`.
- [ ] Lint: shellcheck (CI).
- [ ] Manual verification: links and anchors in changed documents resolve.

Not applicable:

- [x] Frontend/backend tests, typecheck, build: no application code changes.

## Documentation

As listed in Requirements. Record eventual Step 13 reviews under
`docs/ai-reviews/TASK-059J/`.
