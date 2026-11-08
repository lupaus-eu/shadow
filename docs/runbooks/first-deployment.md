# First deployment checklist (Hetzner host, GHCR images)

Follows ADR-0035. Use it for the first start of the production stack; later
releases only need section 6. Items marked **human** need an account, a console, or
a secret; the rest are commands. The full production checklist is
[`production-readiness.md`](production-readiness.md); this file is the order of work
for getting the first containers running.

## 1. GitHub: produce the first images

- [ ] **human** Check that Actions may publish packages: repository *Settings →
  Actions → General → Workflow permissions* (the workflow requests `packages: write`
  itself; an organization policy can still block it).
- [ ] Merge to `main` and wait for CI to pass.
- [ ] Tag a release from that commit and push the tag:

  ```bash
  git tag v0.1.0 && git push origin v0.1.0
  ```

- [ ] Open the *Actions* tab and check that the **Images** workflow is green for both
  `backend` and `frontend`.
- [ ] **human** Find the packages: `https://github.com/orgs/lupaus-eu/packages`
  (also in the repository's right-hand sidebar under *Packages*). Both
  `shadow-backend` and `shadow-frontend` must list the tag `v0.1.0`. They link
  to the repository through the image labels and stay private.

## 2. GitHub: a token for the host

The host downloads the private images, so it needs a credential.

- [ ] **human** In GitHub, *Settings → Developer settings → Personal access tokens →
  Tokens (classic)* of the account that will pull: create a token with only the
  `read:packages` scope and no expiry beyond what you accept. Fine-grained tokens
  cannot read packages. If the organization enforces SSO, authorize the token for it.
  A dedicated machine account with read access to the packages is better than a
  personal account.
- [ ] **human** Store the token in the password manager. It is not a GitHub secret
  and never goes into the repository.

## 3. Hetzner host

- [ ] **human** Create the server in the Hetzner Cloud Console: Ubuntu LTS on an Intel/AMD
  (x86-64) type (the images are `linux/amd64`, ADR-0053), at least 2 GB / 2 CPU (4 GB /
  2 CPU recommended), with your SSH key. Do not allow password login.
- [ ] **human** Firewall (a Hetzner Cloud Firewall in front of the host; ufw on the host is the second layer): allow inbound 22 (preferably only your address), 80, and
  443; nothing else.
- [ ] **human** DNS: A (and AAAA) records for the application domain and the
  identity domain point at the host.
- [ ] **Preferred:** paste [`scripts/ops/cloud-init.yml`](../../scripts/ops/cloud-init.yml)
  into the *Cloud config* (user data) field when creating the server. On first boot it updates
  Ubuntu and installs Docker with the Compose plugin, restic, git, make, fail2ban, and
  automatic security updates; adds 2 GB of swap; enables a ufw firewall for 22, 80,
  and 443; and creates `/opt/shadow`. Wait until `/var/lib/shadow-init.done`
  exists (`tail -f /var/log/cloud-init-output.log` shows progress), then skip the
  manual commands below, apart from the checks. It installs tools only: it holds no
  secret and does not start the stack.
- [ ] **Without cloud-init** (an existing host): update the system and install Docker
  with the Compose plugin and restic (the backups need it):

  ```bash
  sudo apt-get update && sudo apt-get -y upgrade
  curl -fsSL https://get.docker.com | sudo sh
  sudo apt-get install -y restic git make
  sudo usermod -aG docker "$USER"   # log out and in again
  ```

- [ ] On a 2 GB host add 2 GB of swap (cloud-init already did):

  ```bash
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```

- [ ] Check: `docker compose version`, `restic version`, `make --version`, `free -h` (swap shows 2 GB), `df -h /`, `sudo ufw status`.

## 4. Files and secrets on the host

- [ ] Put the repository files on the host (the host builds nothing, but Compose
  mounts `caddy/` and `authentik/`, and the backup scripts live in `scripts/ops/`):

  ```bash
  sudo mkdir -p /opt/shadow && sudo chown "$USER" /opt/shadow
  git clone https://github.com/lupaus-eu/shadow.git /opt/shadow
  cd /opt/shadow && git checkout v0.1.0
  ```

  (A private repository needs a read-only deploy key or a token for the clone.)
- [ ] Log in to GHCR with the token from section 2:

  ```bash
  echo "<token>" | docker login ghcr.io -u <github-user> --password-stdin
  ```

- [ ] Create `.env.production` from `.env.production.example` and fill every required value
  (`docs/runbooks/production-readiness.md` section 1). Generate secrets with
  `openssl rand -hex 32` (letters and digits only, since the database password is part of a URL), a different value for each. Then:

  ```bash
  chmod 600 .env.production
  ```

- [ ] Set in it: `SHADOW_TAG=v0.1.0`, `SHADOW_EDGE_BIND_ADDRESS=0.0.0.0`,
  `SHADOW_HTTP_PORT=80`, `SHADOW_HTTPS_PORT=443`, the two site addresses,
  `FRONTEND_URL`, `PUBLIC_API_BASE_URL`, and `OIDC_ISSUER`.
- [ ] Check that the file resolves, without starting anything:

  ```bash
  docker compose -f docker-compose.prod.yml --env-file .env.production config > /dev/null && echo ok
  ```

## 5. First start

The host can use short commands from [`Makefile.prod`](../../Makefile.prod): copy it
as `Makefile` (`rsync -av Makefile.prod <host>:/opt/shadow/Makefile`), then
`make config`, `make deploy` (pull, start, status), `make ps`, `make logs SERVICE=backend`,
`make tag TAG=<tag>`, and `make help` for the rest (all described in
[`production-commands.md`](production-commands.md)). The commands below are what they run.

- [ ] Pull the images:

  ```bash
  docker compose -f docker-compose.prod.yml --env-file .env.production pull
  ```

- [ ] Start the stack:

  ```bash
  docker compose -f docker-compose.prod.yml --env-file .env.production up -d
  ```

- [ ] Watch it settle (`migrate` ends as `exited (0)`, the rest `running` or
  `healthy`; Authentik takes a few minutes the first time):

  ```bash
  docker compose -f docker-compose.prod.yml --env-file .env.production ps
  docker stats --no-stream
  ```

- [ ] If memory is near the limit, check `free -h` and the swap use before going on.
- [ ] Open both domains in a browser: Caddy must obtain certificates, the app must
  load, and the identity domain must show Authentik.
- [ ] Continue with `production-readiness.md` section 2 (Authentik bootstrap and an
  operator), section 3 (Stripe), and the email sender checks.

## 6. Backups before real data

- [ ] Set up the off-host backup (`docs/runbooks/backup.md`): bucket, key, restic
  password outside the host, `BACKUP_*` settings, the systemd timers, and the first
  run with its email.
- [ ] Rehearse a restore (`scripts/ops/restore-drill.sh`) before inviting anyone.

## 7. Later releases and rollback

### Copy the host's files first

The images come from GHCR, but the host's Compose file, Caddyfile, Authentik blueprints, and scripts do not.
They go stale unless you copy them, and then a new feature that needs them (a Caddy route, an Authentik
blueprint) silently does nothing. Run this from a checkout of the commit you are releasing, whenever any of
`docker-compose.prod.yml`, `caddy/`, `authentik/`, `docker/postgres/init/`, `scripts/ops/`, or `Makefile.prod`
changed (when unsure, run it; add `-n` to see what would change). It never touches `.env.production`:

```bash
rsync -av --relative docker-compose.prod.yml caddy authentik docker/postgres/init scripts/ops <host>:/opt/shadow/ && rsync -av Makefile.prod <host>:/opt/shadow/Makefile
```

Then on the host, in `/opt/shadow`:

```bash
make deploy
```

```bash
make authentik-apply
```

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --force-recreate caddy
```

`make deploy` pulls the images, starts the stack, and reloads Caddy. `make authentik-apply` applies new or
changed Authentik blueprints even when the fingerprint says nothing changed. Recreating Caddy is needed once
after the Caddyfile is first mounted as a directory (`make deploy` reloads it from then on). Check the
result as the feature says, for example the MCP metadata in `docs/runbooks/mcp-interface.md`.

- [ ] Tag a release from a green `main`, wait for the Images workflow, then on the
  host set `SHADOW_TAG`, copy the host's files with the `rsync` command above
  (the host has no source tree), and run `make deploy` (or `pull` and `up -d` as in section 5).
- [ ] Roll back by setting the previous `SHADOW_TAG` and running the same two
  commands, only if that release is compatible with the current database schema;
  otherwise restore from backup.
